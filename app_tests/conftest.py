"""Shared fixtures for the Points Counter API tests.

The suite runs against an already-running server (``npm start``, or the
"Start API" step in .github/workflows/api-tests.yml). It does not spawn one:
under ``pytest -n auto`` every xdist worker would race to bind the same port.

Parallel safety comes from two rules, enforced by the fixtures below:

1. **One client per test.** Each ``client`` has its own cookie jar, so each test
   has its own express-session. A logout in one test cannot log out another.
2. **One student per test.** ``student`` creates a uniquely-named student and
   deletes it afterwards, so no test depends on globally stored contents.

Data safety: the suite is meant to run against a server started with
``POINTS_DATA_FILE`` pointing at ``app_tests/data/students.test.json``
(``npm run start:test``), not against the teacher's real
``server/data/students.json``. Nothing in pytest can *configure* the already
running server, so ``real_data_file_is_untouched`` below verifies it instead.
Read RISKS.md before relying on that guard.
"""

from __future__ import annotations

import asyncio
import os
import uuid
import warnings
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
import pytest_asyncio

from app_tests.exponential_backoff import retry_async

DEFAULT_BASE_URL = "http://127.0.0.1:3000"
# Matches the fallback in server/auth.js. The server does not read .env, so a
# plain `npm start` really does use this.
DEFAULT_PASSWORD = "teacher"

REQUEST_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

REPO_ROOT = Path(__file__).resolve().parent.parent
# The file the guard defends. Matches DEFAULT_DATA_FILE in server/store.js; if
# that default ever moves, this goes stale and the guard quietly passes.
REAL_DATA_FILE = REPO_ROOT / "server" / "data" / "students.json"
# Hosts where the server shares this filesystem, so reading the file above says
# something about the server we are testing.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("POINTS_API_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session")
def teacher_password() -> str:
    return os.environ.get("TEACHER_PASSWORD", DEFAULT_PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def server_is_up(base_url: str) -> None:
    """Block until the API answers, so a slow boot is not a test failure.

    Still synchronous, but not for the original reason: pytest.ini now pins
    ``asyncio_default_fixture_loop_scope = session`` (the Playwright plugin
    requires it), so an async version would no longer need loop_scope plumbing.
    ``asyncio.run`` is kept because it gives this probe a loop of its own --
    a wedged probe cannot leave a half-cancelled task on the session loop that
    every subsequent test now shares.
    """

    async def probe() -> httpx.Response:
        async with httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT) as client:
            # /api/session is unguarded, so it answers 200 before login.
            return await client.get("/api/session")

    try:
        response = asyncio.run(retry_async(probe, attempts=12, base_delay=0.25, max_delay=4.0))
    except httpx.TransportError as exc:
        pytest.fail(
            f"no API at {base_url} ({exc.__class__.__name__}). "
            f"Start it with: TEACHER_PASSWORD=... npm start"
        )

    if response.status_code != 200:
        pytest.fail(f"API at {base_url} answered {response.status_code} on /api/session")


@pytest.fixture(scope="session", autouse=True)
def real_data_file_is_untouched(
    server_is_up: None, base_url: str, teacher_password: str
) -> None:
    """Fail the whole session if the server writes to the real student store.

    Setting ``POINTS_DATA_FILE`` for *pytest* proves nothing: the server is a
    separate process that read its own environment at boot, and the suite
    deliberately does not start it. So this asks the server instead of trusting
    configuration -- create one canary student through the API, then look for
    its name in ``server/data/students.json``. If it landed there, the running
    server is the real one and every later test would append to the teacher's
    data.

    Cost of being wrong is one create + one delete on the real file, which is
    why this runs before anything else rather than as a post-hoc check.

    Deliberately not a proof of safety, only of this one file:

    * Downgraded to a warning when the API is not local -- the path would be a
      different machine's. A ``pytest.skip`` here would skip the entire suite,
      turning "cannot check" into "nothing ran", so it warns and continues.
    * A server pointed at some *third* file (a stale test file, a typo'd path)
      passes. What is asserted is "not the real store", not "the intended one".
    * Under ``-n auto`` every xdist worker runs this, so a plain `npm start`
      leaves one canary row per worker before failing. They are deleted on the
      way out; a crash mid-guard can leak one.
    """
    if not REAL_DATA_FILE.exists():
        return

    host = urlsplit(base_url).hostname
    if host not in LOCAL_HOSTS:
        warnings.warn(
            f"API at {base_url} is not local, so the data-file guard cannot run. "
            f"This suite writes real students; make sure that server is expendable.",
            stacklevel=1,
        )
        return

    canary = f"pytest-canary-{uuid.uuid4().hex}"

    async def probe() -> None:
        async with httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT) as client:
            login = await retry_async(
                lambda: client.post("/api/login", json={"password": teacher_password})
            )
            assert login.status_code == 200, (
                f"login failed: {login.status_code} {login.text}. "
                f"Does TEACHER_PASSWORD match the running server?"
            )
            created = await client.post("/api/students", json={"name": canary})
            assert created.status_code == 201, f"{created.status_code} {created.text}"
            try:
                # Read *after* the create returned, so the write has already
                # been renamed into place.
                landed = canary in REAL_DATA_FILE.read_text(encoding="utf8")
            finally:
                await client.delete(f"/api/students/{created.json()['id']}")

        if landed:
            pytest.fail(
                f"the server at {base_url} is writing to {REAL_DATA_FILE}, which holds "
                "real student data. Restart it against the test store:\n"
                "    npm run start:test\n"
                "(or set POINTS_DATA_FILE yourself), then re-run pytest."
            )

    asyncio.run(probe())


@pytest_asyncio.fixture
async def client(base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    """An anonymous client with its own cookie jar.

    Use this for anything asserting 401 -- it has never logged in.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=REQUEST_TIMEOUT) as client:
        yield client


@pytest_asyncio.fixture
async def auth_client(
    client: httpx.AsyncClient, teacher_password: str
) -> AsyncIterator[httpx.AsyncClient]:
    """A client that has logged in; the connect.sid cookie rides along."""
    response = await retry_async(
        lambda: client.post("/api/login", json={"password": teacher_password})
    )
    assert response.status_code == 200, (
        f"login failed: {response.status_code} {response.text}. "
        f"Does TEACHER_PASSWORD match the running server?"
    )
    yield client


@pytest.fixture
def unique_name(request: pytest.FixtureRequest) -> str:
    """A student name no concurrent worker will also pick."""
    return f"pytest-{request.node.name[:30]}-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def student(auth_client: httpx.AsyncClient, unique_name: str) -> AsyncIterator[dict]:
    """A freshly created student, removed again at teardown.

    Careful: deleting it can free its id for reuse, because
    ``store.nextId()`` is ``max(remaining) + 1``. Never assert that a deleted
    id 404s -- a concurrent create may already hold it.
    """
    response = await auth_client.post("/api/students", json={"name": unique_name})
    assert response.status_code == 201, f"setup failed: {response.status_code} {response.text}"
    created = response.json()

    try:
        yield created
    finally:
        await auth_client.delete(f"/api/students/{created['id']}")