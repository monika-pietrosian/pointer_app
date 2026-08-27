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

import json

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


async def test_starting_a_session_shows_the_students_name_and_points(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """session.start() sets active.basePoints from the student object passed
    in (session.js: ``active = { id, name, basePoints: student.points }``)
    and renderScore() writes ``${name}: ${basePoints + sessionPoints}`` into
    #score-display. Points are set to a non-zero value through the API before
    the session starts, so a passing assertion proves basePoints really came
    from the student's stored total -- a hardcoded 0 in session.js would also
    pass against a freshly created, zero-point student.
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await auth_client.put(f"/api/students/{created['id']}", json={"points": 7})

    # dashboard_page's own login already refreshed the store before this
    # student (and its points) existed -- reload to pick both up.
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    await dashboard_page.locator("#active-student").select_option(value=str(created["id"]))
    await dashboard_page.get_by_role("button", name="Start session").click()

    await expect(dashboard_page.locator("#view-session")).to_be_visible()
    await expect(dashboard_page.locator("#score-display")).to_have_text(f"{unique_name}: 7")

    await auth_client.delete(f"/api/students/{created['id']}")


async def test_score_increases_and_stacks_when_pressing_z_x_c(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """award() adds each press onto a running ``sessionPoints`` that is never
    sent to the server until stop() -- so z/x/c should each bump the on-screen
    total by 1/5/10 immediately, and repeated presses should keep adding
    rather than resetting or overwriting.
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    await dashboard_page.locator("#active-student").select_option(value=str(created["id"]))
    await dashboard_page.get_by_role("button", name="Start session").click()
    await expect(dashboard_page.locator("#view-session")).to_be_visible()

    score = dashboard_page.locator("#score-display")
    await expect(score).to_have_text(f"{unique_name}: 0")

    await dashboard_page.keyboard.press("z")
    await expect(score).to_have_text(f"{unique_name}: 1")
    await dashboard_page.keyboard.press("x")
    await expect(score).to_have_text(f"{unique_name}: 6")
    await dashboard_page.keyboard.press("c")
    await expect(score).to_have_text(f"{unique_name}: 16")
    await dashboard_page.keyboard.press("z")
    await expect(score).to_have_text(f"{unique_name}: 17")

    await auth_client.delete(f"/api/students/{created['id']}")


async def test_stopping_a_session_posts_the_earned_points_and_updates_the_dashboard(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """stop() POSTs the summed session delta to /api/students/:id/points and
    then returns to the dashboard via a fresh refresh() -- so both the
    request body and the re-rendered totals should reflect the 16 points
    earned (1 + 5 + 10). The request is observed via page.route rather than
    faked, so the final ".s-points" text still depends on the real server
    doing the addition -- test_points_delta_coercion covers that
    independently; this test is only about the wiring around it.
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    await dashboard_page.locator("#active-student").select_option(value=str(created["id"]))
    await dashboard_page.get_by_role("button", name="Start session").click()
    await expect(dashboard_page.locator("#view-session")).to_be_visible()

    await dashboard_page.keyboard.press("z")  # +1
    await dashboard_page.keyboard.press("x")  # +5
    await dashboard_page.keyboard.press("c")  # +10

    seen_bodies: list[dict] = []

    async def capture(route: Route) -> None:
        seen_bodies.append(route.request.post_data_json)
        await route.continue_()

    await dashboard_page.route(f"**/api/students/{created['id']}/points", capture)

    await dashboard_page.get_by_role("button", name="Stop session").click()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    assert seen_bodies == [{"delta": 16}]

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    await expect(row.locator(".s-points")).to_have_text("16 pts")

    await auth_client.delete(f"/api/students/{created['id']}")


async def test_stopping_a_session_with_zero_points_does_not_post(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """session.js: ``if (id !== null && earned !== 0)`` guards the POST, and
    that branch (skipped or not) fully resolves before stop() calls onEnd() /
    showView -- so by the time the dashboard is visible again, the request
    was never going to fire. No sleep needed to "give it a chance".
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    await dashboard_page.locator("#active-student").select_option(value=str(created["id"]))
    await dashboard_page.get_by_role("button", name="Start session").click()
    await expect(dashboard_page.locator("#view-session")).to_be_visible()

    posted = False

    async def watch(route: Route) -> None:
        nonlocal posted
        posted = True
        await route.continue_()

    await dashboard_page.route(f"**/api/students/{created['id']}/points", watch)

    await dashboard_page.get_by_role("button", name="Stop session").click()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    assert not posted

    await auth_client.delete(f"/api/students/{created['id']}")


async def test_deleting_a_student_via_the_ui_delete_button(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """window.confirm() gates onDelete(): dismissing it (Cancel) must leave
    the row and the picker option untouched, accepting it must run the real
    DELETE + refresh() and remove both.
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    option = dashboard_page.locator("#active-student option", has_text=unique_name)
    await expect(row).to_be_visible()
    await expect(option).to_have_count(1)

    try:
        async def cancel(dialog: Dialog) -> None:
            await dialog.dismiss()

        dashboard_page.once("dialog", cancel)
        await row.locator(".del").click()
        await expect(row).to_be_visible()
        await expect(option).to_have_count(1)

        async def confirm_delete(dialog: Dialog) -> None:
            assert dialog.type == "confirm"
            assert dialog.message == f"Delete {unique_name}? This removes their points too."
            await dialog.accept()

        dashboard_page.once("dialog", confirm_delete)
        await row.locator(".del").click()
        await expect(row).to_be_hidden()
        await expect(option).to_have_count(0)
    finally:
        # Best-effort: a 404 here just means the UI's own delete already won.
        await auth_client.delete(f"/api/students/{created['id']}")


async def test_renaming_a_student_via_the_ui_edit_button(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """onRename() gates on window.prompt(): ``null`` (Cancel) returns before
    any request, a blank/whitespace-only answer is trimmed to '' and also
    bails, and only a real name reaches api.updateStudent() + refresh().
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    name_cell = row.locator(".s-name")
    await expect(row).to_be_visible()

    try:
        async def cancel(dialog: Dialog) -> None:
            await dialog.dismiss()

        dashboard_page.once("dialog", cancel)
        await row.locator(".edit").click()
        await expect(name_cell).to_have_text(unique_name)

        async def blank_answer(dialog: Dialog) -> None:
            await dialog.accept("   ")

        dashboard_page.once("dialog", blank_answer)
        await row.locator(".edit").click()
        await expect(name_cell).to_have_text(unique_name)

        new_name = f"{unique_name}-renamed"

        async def real_answer(dialog: Dialog) -> None:
            await dialog.accept(new_name)

        dashboard_page.once("dialog", real_answer)
        await row.locator(".edit").click()
        await expect(dashboard_page.locator(".student-row", has_text=new_name)).to_be_visible()
        await expect(row).to_be_hidden()
    finally:
        await auth_client.delete(f"/api/students/{created['id']}")


async def test_empty_student_list_shows_hints_in_the_list_and_the_picker(
    page: Page,
    teacher_password: str,
) -> None:
    """renderList()/renderSelect() both special-case an empty cache: the list
    gets one ".hint" <li>, the picker gets a single placeholder <option
    value="">. Faked via page.route the same way
    test_starting_session_without_adding_a_student fakes an empty store --
    the real store is shared across xdist workers and can't be emptied for
    real without breaking every other test that expects it populated.
    """

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

    await expect(page.locator("#student-list .hint")).to_have_text(
        "No students yet. Add one above."
    )
    await expect(page.locator("#active-student option")).to_have_count(1)
    await expect(page.locator("#active-student option")).to_have_text("— no students —")
    await expect(page.locator("#active-student")).to_have_value("")


async def test_a_students_name_with_html_renders_as_literal_text(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """renderList() builds .s-name via innerHTML, so escapeHtml() is the only
    thing standing between a student's name and a real, un-rendered <script>
    element landing in the DOM. Checking for a live ``script`` child (not
    just the rendered text) is what actually distinguishes "escaped" from
    "browser silently didn't run it anyway".
    """
    hostile_name = f"<script>alert(1)</script>{unique_name}"
    created = (await auth_client.post("/api/students", json={"name": hostile_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    row = dashboard_page.locator(".student-row", has_text=unique_name)
    await expect(row.locator(".s-name")).to_have_text(hostile_name)
    assert await row.locator(".s-name script").count() == 0

    option = dashboard_page.locator("#active-student option", has_text=unique_name)
    await expect(option).to_have_text(f"{hostile_name} (0)")

    await auth_client.delete(f"/api/students/{created['id']}")


async def test_submitting_the_create_form_with_a_blank_name_does_nothing(
    dashboard_page: Page,
) -> None:
    """app.js's submit handler trims the input and returns before calling
    students.onCreate() when the trimmed value is empty (``if (!name)
    return``) -- that ``return`` runs synchronously, before any network call
    could be scheduled, so there is no race to guard against here.
    """
    posted = False

    async def watch(route: Route) -> None:
        nonlocal posted
        if route.request.method == "POST":
            posted = True
        await route.continue_()

    await dashboard_page.route("**/api/students", watch)

    before_count = await dashboard_page.locator(".student-row").count()

    await dashboard_page.get_by_placeholder("New student name").fill("   ")
    await dashboard_page.get_by_role("button", name="Add").click()

    await expect(dashboard_page.get_by_placeholder("New student name")).to_have_value("   ")
    await expect(dashboard_page.locator(".student-row")).to_have_count(before_count)
    assert not posted


async def test_a_failed_create_alerts_and_keeps_the_typed_name(
    dashboard_page: Page,
    unique_name: str,
) -> None:
    """app.js only clears the input inside the try block, after ``await
    students.onCreate(name)`` resolves -- so a failed create should alert
    with the server's own error message and leave the typed name sitting in
    the field.
    """
    seen_dialogs: list[Dialog] = []

    async def capture_and_accept(dialog: Dialog) -> None:
        seen_dialogs.append(dialog)
        await dialog.accept()

    dashboard_page.on("dialog", capture_and_accept)

    async def fail_create(route: Route) -> None:
        if route.request.method != "POST":
            await route.continue_()
            return
        await route.fulfill(
            status=400,
            content_type="application/json",
            body=json.dumps({"error": "Name is required"}),
        )

    await dashboard_page.route("**/api/students", fail_create)

    await dashboard_page.get_by_placeholder("New student name").fill(unique_name)
    await dashboard_page.get_by_role("button", name="Add").click()

    await expect(dashboard_page.get_by_placeholder("New student name")).to_have_value(unique_name)
    assert len(seen_dialogs) == 1
    assert seen_dialogs[0].type == "alert"
    assert seen_dialogs[0].message == "Failed to add student: Name is required"


async def test_reloading_while_logged_in_keeps_the_dashboard_populated(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> None:
    """app.js's boot IIFE calls api.checkSession() and, on a valid cookie,
    showDashboard() instead of showLogin() -- so a reload with the session
    cookie still set should land straight back on the dashboard, freshly
    populated from the server, instead of bouncing through the login screen.
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()

    await dashboard_page.reload()

    await expect(dashboard_page.locator("#view-login")).to_be_hidden()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()
    await expect(dashboard_page.locator(".student-row", has_text=unique_name)).to_be_visible()

    await auth_client.delete(f"/api/students/{created['id']}")
