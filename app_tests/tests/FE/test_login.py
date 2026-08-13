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

import json

import pytest
from playwright.async_api import Page, Route, expect

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

# Matches the shape the real API uses for errors ({"error": "..."}), so the
# assertion exercises the same parsing path a genuine 5xx would.
SERVICE_UNAVAILABLE_COPY = "Service temporarily unavailable"


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


async def test_login_shows_the_server_message_when_the_api_returns_503(
    page: Page, teacher_password: str
) -> None:
    """A 5xx must surface the server's own message, not the 401 copy.

    app.js:38 is ``err.status === 401 ? 'Wrong password' : err.message``. The
    other three tests in this file only ever reach the left branch, so without
    this one nothing proves the right branch renders at all.

    The password is the *correct* one on purpose: the only reason an error can
    appear is the injected fault, which is what makes this a test of the 5xx
    path rather than of the password check.

    Faults are injected with page.route rather than a mock server. The real
    server has no code path that returns 503, so it has to be simulated
    somewhere -- and route intercepts inside this BrowserContext's own network
    stack, so exactly one endpoint breaks, the rest still hit the real Node
    process, and there is no second port for xdist workers to fight over.
    """
    await page.goto("/")

    # Registered after goto, so the page itself loaded against the real server.
    # Only the login call this test is about gets intercepted; the boot-time
    # GET /api/session in app.js is untouched.
    async def respond_503(route: Route) -> None:
        await route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"error": SERVICE_UNAVAILABLE_COPY}),
        )

    await page.route("**/api/login", respond_503)

    await page.get_by_placeholder("Password").fill(teacher_password)
    await page.get_by_role("button", name="Start").click()

    # Goes through api.js req(): `(data && data.error) || res.statusText` picks
    # the body's error string, so this assertion is on a value the server
    # contract owns -- not on a browser-generated string.
    await expect(page.locator("#login-error")).to_have_text(SERVICE_UNAVAILABLE_COPY)
    await expect(page.locator("#view-dashboard")).to_be_hidden()
    await expect(page.locator("#view-login")).to_be_visible()


async def test_login_reports_a_failure_when_the_api_is_unreachable(
    page: Page, teacher_password: str
) -> None:
    """Network down: the form must fail visibly instead of hanging or silently
    dropping the click.

    Weaker assertions than the 503 test, deliberately. abort() makes fetch()
    itself reject, so the error never reaches api.js's error construction --
    `err` is a raw Chromium TypeError and `err.status` is undefined. Its message
    is a browser implementation detail, so pinning the exact text would make
    this test a hostage to a Chromium upgrade. What matters is that *an* error
    shows and that it is not the 401 copy, i.e. the app did not misreport a
    dead network as a bad password.
    """
    await page.goto("/")
    await page.route("**/api/login", lambda route: route.abort())

    await page.get_by_placeholder("Password").fill(teacher_password)
    await page.get_by_role("button", name="Start").click()

    error = page.locator("#login-error")
    await expect(error).to_be_visible()
    await expect(error).not_to_be_empty()
    await expect(error).not_to_have_text("Wrong password")
    await expect(page.locator("#view-dashboard")).to_be_hidden()


# TODO, in rough order of value:
#   - log out -> back on #view-login with the field cleared, and a reload does
#     not land on the dashboard (the cookie really is gone)
#   - reload while logged in -> app.js does not restore the dashboard today;
#     decide whether that is a bug before writing the test for it
