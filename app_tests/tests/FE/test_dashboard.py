"""Dashboard: student list, the "start a session" picker, and their CRUD wiring.

Scope note: the API suite (test_students_crud.py) already proves create/read
work end to end. What only a browser can prove is that the dashboard actually
wires the form to that API and re-renders from the response -- so these tests
assert on rendered DOM, never on a response body.

Parallel-safety rules for this file, same as test_login.py:

* Every test gets its own BrowserContext via ``page``/``dashboard_page``, so
  logging in on one worker never touches another worker's session.
* Every student created through the UI is deleted again through the API, not
  by clicking the dashboard's own delete button -- that button opens a
  ``window.confirm()`` this test has no reason to drive. Use ``unique_name``
  so concurrent workers never collide on names.
"""

from __future__ import annotations

import httpx
import pytest
from playwright.async_api import Dialog, Page, Route, expect

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_adding_a_student_shows_it_in_the_list_and_the_session_picker(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """create-form -> api.createStudent -> students.refresh() re-renders both
    #student-list and #active-student from the same response, so this checks
    both instead of just the list.
    """
    await dashboard_page.get_by_placeholder("New student name").fill(unique_name)
    await dashboard_page.get_by_role("button", name="Add").click()

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    await expect(row).to_be_visible()
    await expect(row.locator(".s-points")).to_have_text("0 pts")

    await expect(
        dashboard_page.locator("#active-student option", has_text=unique_name)
    ).to_have_count(1)


    await expect(dashboard_page.get_by_placeholder("New student name")).to_have_value("")

    students = await auth_client.get("/api/students")
    created = next(s for s in students.json() if s["name"] == unique_name)
    await auth_client.delete(f"/api/students/{created['id']}")


async def test_starting_session_without_adding_a_student(
    page: Page,
    teacher_password: str,
) -> None:
    """start-session-btn's handler checks ``students.selectedId()`` before
    doing anything else, and alerts instead of opening the session view when
    it's null (app.js: ``if (!student) { window.alert('Pick a student
    first.'); return; }``).

    ``selectedId()`` is only null when the picker has no real ``<option>``s,
    which only happens when the store is genuinely empty -- so this can't use
    ``dashboard_page`` (it logs in and refreshes against whatever students
    really exist) or rely on "this test didn't create one": the store is
    shared across xdist workers and other tests leave students in it. Instead
    it fakes an empty store the same way test_login.py fakes a 503, via
    page.route, so the result never depends on what else is running.

    Dialog handling: window.alert() blocks the page's JS thread until
    dismissed, and Playwright will not let a click that opened it finish
    until something calls dialog.accept() or dialog.dismiss() -- with no
    listener registered it auto-dismisses instead, silently, before there is
    any message to read. The listener has to be registered *before* the
    click, and it has to do the accept()/dismiss() itself: an
    expect_event("dialog") context manager that waits to inspect the dialog
    only after the click deadlocks, because the click it's waiting on is the
    very thing frozen on that dialog.
    """
    seen_dialogs: list[Dialog] = []

    async def capture_and_accept(dialog: Dialog) -> None:
        seen_dialogs.append(dialog)
        await dialog.accept()

    page.on("dialog", capture_and_accept)

    async def empty_student_list(route: Route) -> None:
        if route.request.method != "GET":
            await route.continue_()
            return
        await route.fulfill(content_type="application/json", body="[]")

    await page.route("**/api/students", empty_student_list)

    await page.goto("/")
    await page.get_by_placeholder("Password").fill(teacher_password)
    await page.get_by_role("button", name="Start").click()
    await expect(page.locator("#view-dashboard")).to_be_visible()

    # Confirms the fake actually landed, so a failure below is about the
    # alert and not about an empty list that never rendered.
    await expect(page.locator("#active-student")).to_have_value("")

    await page.get_by_role("button", name="Start session").click()

    assert len(seen_dialogs) == 1
    assert seen_dialogs[0].type == "alert"
    assert seen_dialogs[0].message == "Pick a student first."

    # The alert's `return` runs before showView('view-session'), so the
    # dashboard must still be the visible view.
    await expect(page.locator("#view-dashboard")).to_be_visible()
    await expect(page.locator("#view-session")).to_be_hidden()


async def test_starting_session_with_adding_a_student(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """create-form -> api.createStudent -> students.refresh() re-renders both
    #student-list and #active-student from the same response, so this checks
    both instead of just the list.
    """
    await dashboard_page.get_by_placeholder("New student name").fill(unique_name)
    await dashboard_page.get_by_role("button", name="Add").click()

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    await expect(row).to_be_visible()
    await expect(row.locator(".s-points")).to_have_text("0 pts")

    await expect(
        dashboard_page.locator("#active-student option", has_text=unique_name)
    ).to_have_count(1)

    await dashboard_page.get_by_role("button", name="Start session").click()


    # The alert's `return` runs before showView('view-session'), so the
    # dashboard must still be the visible view.
    await expect(dashboard_page.locator("#view-dashboard")).to_be_hidden()
    await expect(dashboard_page.locator("#view-session")).to_be_visible()
    students = await auth_client.get("/api/students")
    created = next(s for s in students.json() if s["name"] == unique_name)
    await auth_client.delete(f"/api/students/{created['id']}")


# TODO, in rough order of value:
#   - picking a student and starting a session -> #view-session becomes
#     visible, #score-display shows "{name}: {points}"

#   - pressing z/x/c during a session -> score display goes up by 1/5/10 and
#     stacks across multiple presses (session.js keeps a running total client
#     side, is never sent to the server until stop)

#   - stopping a session -> POST /api/students/:id/points fires with the
#     summed delta, dashboard is shown again, and the list/picker reflect the
#     new total (route via page.route to assert on the request body without
#     depending on server-side accumulation, which test_points_delta_coercion
#     already covers)

#   - stopping a session with zero points earned -> no POST fires at all
#     (session.js: `if (id !== null && earned !== 0)`)

#   - deleting a student via the UI's "x" button -> drive the
#     window.confirm() dialog both ways: accept (row disappears, picker
#     option disappears) and dismiss (row stays)

#   - renaming a student via the UI's "edit" button -> drive window.prompt(),
#     both a real name (row updates) and a blank/whitespace-only answer
#     (onRename bails, name unchanged) and Cancel (name unchanged)

#   - the empty-state list ("No students yet. Add one above.") when the
#     store has no students, and the picker's "— no students —" placeholder
#     option in the same state

#   - a name with HTML in it (e.g. "<script>alert(1)</script>") renders as
#     literal text in .s-name and the select option, proving escapeHtml is
#     actually wired in, not just present in students.js

#   - submitting the create-form with a blank/whitespace-only name -> no
#     request fires and the list is unchanged (app.js trims and returns early
#     before calling students.onCreate)

#   - a failed create (e.g. via page.route aborting POST /api/students) ->
#     window.alert("Failed to add student: ...") and the input keeps its text
#     (input.value is only cleared in the try block, after the await)


#   - reloading while logged in with students already listed -> the boot
#     path in app.js calls showDashboard() on a valid session cookie, so the
#     list should repopulate without a fresh login
