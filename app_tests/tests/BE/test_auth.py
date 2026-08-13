"""Auth routes: /api/login, /api/logout, /api/session.

Parallel-safety rules for this file:

* Assert 401 only with the ``client`` fixture (never logged in). Reaching for
  ``auth_client`` and logging out to "become anonymous" is what makes a suite
  order-dependent.
* Logging out is safe here: each test has its own cookie jar, so destroying
  this session cannot disturb a test running in another worker.
"""

from __future__ import annotations

import httpx

from app_tests.exponential_backoff import retry_async


WRONG_PASSWORD = "Wrong password"

async def test_login_with_correct_password_opens_a_session(
    client: httpx.AsyncClient, teacher_password: str
) -> None:
    # Login is idempotent, so wrapping it in retry_async is safe. A transient
    # 503 from a busy CI runner retries; a 401 comes straight back and fails
    # the assertion below, which is what we want.
    response = await retry_async(
        lambda: client.post("/api/login", json={"password": teacher_password})
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}

    # express-session only emits Set-Cookie once the session is touched
    # (saveUninitialized is false), so the cookie landing in the jar is what
    # proves the login took effect server-side.
    assert client.cookies.get("connect.sid") is not None

async def test_session_cookie_is_http_only(
    client: httpx.AsyncClient, teacher_password: str
) -> None:
    """The session cookie must be unreadable from JavaScript.

    connect.sid *is* the credential, and it lives for 12h. Without HttpOnly an
    XSS on the dashboard could read document.cookie and replay the teacher's
    session anywhere; with it, the cookie never enters JS reach.

    Read the raw header, not ``client.cookies``: httpx's jar keeps the name and
    value and drops the attributes, so the flag is invisible from there.
    """
    response = await retry_async(
        lambda: client.post("/api/login", json={"password": teacher_password})
    )
    assert response.status_code == 200, response.text

    # get_list, not get: Set-Cookie is the one header a server may legitimately
    # send more than once, and .get would collapse them into a single string.
    set_cookie = next(
        (
            header
            for header in response.headers.get_list("set-cookie")
            if header.startswith("connect.sid=")
        ),
        None,
    )
    assert set_cookie is not None, f"no connect.sid in {response.headers.get_list('set-cookie')}"

    # Everything after the first ";" is an attribute. Some carry a value
    # (Path=/, Expires=...), flags like HttpOnly do not, so compare on the name.
    attributes = {part.strip().split("=", 1)[0].lower() for part in set_cookie.split(";")[1:]}

    assert "httponly" in attributes, set_cookie

    # Not asserted, deliberately: `secure` and `samesite` are absent today
    # (server.js:19 sets only httpOnly and maxAge). Pinning their absence would
    # turn a future hardening fix into a red test, so they are a reported risk
    # rather than an assertion.
    #
    # Note this catches an explicit `httpOnly: false` but NOT a deleted line --
    # express-session defaults httpOnly to true, verified by mutating the config
    # both ways. That is still worth having: it pins the guarantee against an
    # explicit downgrade and against the framework default ever changing.


async def test_login_with_incorrect_password(
    client: httpx.AsyncClient
) -> None:
 
    response = await retry_async(
        lambda: client.post("/api/login", json={"password": WRONG_PASSWORD})
    )

    assert response.status_code == 401, response.text
    assert response.json() == {"error": WRONG_PASSWORD}

 
    assert client.cookies.get("connect.sid") is None


async def test_login_with_non_string_password(
    client: httpx.AsyncClient
) -> None:
    # Login is idempotent, so wrapping it in retry_async is safe. A transient
    # 503 from a busy CI runner retries; a 401 comes straight back and fails
    # the assertion below, which is what we want.
    response = await retry_async(
        lambda: client.post("/api/login", json={"password": 401})
    )

    assert response.status_code == 401, response.text
    assert response.json() == {"error": WRONG_PASSWORD}


    assert client.cookies.get("connect.sid") is None

async def test_no_login_no_session_access(
    client: httpx.AsyncClient, teacher_password: str
) -> None:
    # Login is idempotent, so wrapping it in retry_async is safe. A transient
    # 503 from a busy CI runner retries; a 401 comes straight back and fails
    # the assertion below, which is what we want.
    response = await retry_async(
        lambda: client.get("/api/session")
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"loggedIn": False}

    # express-session only emits Set-Cookie once the session is touched
    # (saveUninitialized is false), so the cookie landing in the jar is what
    # proves the login took effect server-side.
    assert client.cookies.get("connect.sid") is None


async def test_login_session_access(
    client: httpx.AsyncClient, teacher_password: str
) -> None:
    # Login is idempotent, so wrapping it in retry_async is safe. A transient
    # 503 from a busy CI runner retries; a 401 comes straight back and fails
    # the assertion below, which is what we want.

    response = await retry_async(
        lambda: client.post("/api/login", json={"password": teacher_password})
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}

    session_response = await retry_async(
        lambda: client.get("/api/session")
    )

    assert session_response.status_code == 200, response.text
    assert session_response.json() == {"loggedIn": True}

    # express-session only emits Set-Cookie once the session is touched
    # (saveUninitialized is false), so the cookie landing in the jar is what
    # proves the login took effect server-side.
    assert client.cookies.get("connect.sid") is not None


async def test_students_without_authorization(
    client: httpx.AsyncClient
) -> None:
 
    response = await retry_async(
        lambda: client.post("/api/students")
    )

    assert response.status_code == 401, response.text
    assert response.json() == {"error": "Not authenticated"}

 
    assert client.cookies.get("connect.sid") is None

# TODO, in rough order of value:
#   - POST /api/logout -> {"ok": true}, then /api/session reports logged out
#     and /api/students is 401 again
