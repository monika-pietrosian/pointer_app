"""Shared fixtures for the Points Counter API tests.

The suite runs against an already-running server (``npm start``, or the
"Start API" step in .github/workflows/api-tests.yml). It does not spawn one:
under ``pytest -n auto`` every xdist worker would race to bind the same port.

Parallel safety comes from two rules, enforced by the fixtures below:

1. **One client per test.** Each ``client`` has its own cookie jar, so each test
   holds its own express-session. A logout in one test cannot log out another.
2. **One student per test.** ``student`` creates a uniquely-named student and
   deletes it afterwards, so no test depends on global store contents.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app_tests.exponential_backoff import retry_async

DEFAULT_BASE_URL = "http://127.0.0.1:3000"
# Matches the fallback in server/auth.js. The server does not read .env, so a
# plain `npm start` really does use this.
DEFAULT_PASSWORD = "teacher"

REQUEST_TIMEOUT = httpx.Timeout(5.0, connect=2.0)


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("POINTS_API_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session")
def teacher_password() -> str:
    return os.environ.get("TEACHER_PASSWORD", DEFAULT_PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def server_is_up(base_url: str) -> None:
    """Block until the API answers, so a slow boot is not a test failure.

    Synchronous on purpose: a session-scoped *async* fixture has to share an
    event loop with every test that uses it, which means matching
    ``loop_scope`` everywhere. ``asyncio.run`` keeps that plumbing out of the
    way for a probe that runs once per worker.
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
