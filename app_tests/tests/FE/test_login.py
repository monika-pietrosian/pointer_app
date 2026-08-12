"""Login through the browser: public/index.html + public/js/app.js.

Scope note: the API suite already proves POST /api/login answers 200 and puts
connect.sid in the jar (test_auth.py). Repeating that here through a browser
buys nothing and costs a browser launch. What only a browser can prove is the
wiring around it -- that the form sends what was typed, and that a resolved
login swaps the login view for the dashboard -- so this asserts on rendered
views, never on a response body.

Parallel-safety rules for this file:

* Every test gets its own BrowserContext via the plugin's ``page`` fixture, so
  its cookie jar is its own. Same rule as the httpx ``client`` fixture: no
  shared session, no ordering between xdist workers.
* Assert on ``expect(...)``, not on ``await page.locator(...).is_visible()``.
  Only the former retries, and the view swap happens a fetch round-trip after
  the click.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

# Async on purpose. The sync Playwright API keeps an event loop running for the
# duration of the test, which pytest-asyncio's Runner.run() refuses to nest
# inside -- so a single sync-Playwright test in the session made every async API
# test error out with "Runner.run() cannot be called from a running event loop",
# depending on collection order. One event loop for the whole suite, no mixing.
#
# pytest-playwright-asyncio declares page/context with loop_scope="session"
# (they hang off a session-scoped browser), so tests touching `page` must run on
# that same loop. pytest.ini already defaults to session, which makes this
# marker redundant today -- it stays as a guard, because these tests *require*
# a session loop while the API tests merely tolerate one. Flipping the default
# back should break here, loudly, not there.
pytestmark = pytest.mark.asyncio(loop_scope="session")

WRONG_PASSWORD = "wrong_password"


async def test_login_with_correct_password_shows_the_dashboard(
    page: Page, teacher_password: str
) -> None:
    # Relative URL: the context's base_url comes from the session-scoped
    # base_url fixture in app_tests/conftest.py, so POINTS_API_URL steers the
    # browser and httpx at the same server.
    await page.goto("/")

    login_view = page.locator("#view-login")
    await expect(login_view).to_be_visible()

    await page.get_by_placeholder("Password").fill(teacher_password)
    await page.get_by_role("button", name="Start").click()

    # app.js only calls showDashboard() once api.login() resolves, so the view
    # swap is the frontend's own statement that the request succeeded. On a 401
    # it would instead unhide #login-error and stay put.
    await expect(page.locator("#view-dashboard")).to_be_visible()
    await expect(login_view).to_be_hidden()
    await expect(page.locator("#login-error")).to_be_hidden()

    # The handler clears the field after a successful login; a password left
    # sitting in the DOM would survive into the next screenshot or trace.
    await expect(page.get_by_placeholder("Password")).to_have_value("")


async def test_login_with_incorrect_password_hides_the_dashboard(page: Page) -> None:
    await page.goto("/")

    login_view = page.locator("#view-login")
    await expect(login_view).to_be_visible()

    await page.get_by_placeholder("Password").fill(WRONG_PASSWORD)
    await page.get_by_role("button", name="Start").click()

    await expect(page.locator("#view-dashboard")).to_be_hidden()
    await expect(login_view).to_be_visible()
    await expect(page.locator("#login-error")).to_have_text("Wrong password")

    # Asserting the current behaviour, not an endorsement of it: the failure
    # branch leaves the typed password in the input. Contrast with the success
    # path above, which clears it.
    await expect(page.get_by_placeholder("Password")).to_have_value(WRONG_PASSWORD)


async def test_login_with_empty_password_hides_the_dashboard(page: Page) -> None:
    await page.goto("/")

    login_view = page.locator("#view-login")
    await expect(login_view).to_be_visible()

    await page.get_by_placeholder("Password").fill("")
    await page.get_by_role("button", name="Start").click()

    await expect(page.locator("#view-dashboard")).to_be_hidden()
    await expect(login_view).to_be_visible()
    await expect(page.locator("#login-error")).to_have_text("Wrong password")

    # Still empty, because the failure branch does not touch the field -- the
    # input has no `required`, so the empty string is submitted and comes back
    # 401 like any other wrong password.
    await expect(page.get_by_placeholder("Password")).to_have_value("")


# TODO, in rough order of value:
#   - server unreachable / 500 -> #login-error shows err.message, not the 401
#     copy; route.abort() on **/api/login is the cheap way to force it
#   - log out -> back on #view-login with the field cleared, and a reload does
#     not land on the dashboard (the cookie really is gone)
#   - reload while logged in -> app.js does not restore the dashboard today;
#     decide whether that is a bug before writing the test for it
