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


# TODO, in rough order of value:
#   - wrong password -> 401 {"error": "Wrong password"}
#   - non-string password (e.g. true) -> 401, since checkPassword() has an
#     explicit `typeof password === 'string'` guard
#   - GET /api/session before login -> {"loggedIn": false}
#   - GET /api/session after login  -> {"loggedIn": true}
#   - GET /api/students with `client` -> 401 {"error": "Not authenticated"}
#   - POST /api/logout -> {"ok": true}, then /api/session reports logged out
#     and /api/students is 401 again
#   - the Set-Cookie header carries HttpOnly
