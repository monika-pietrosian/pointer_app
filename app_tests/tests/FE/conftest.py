"""FE-only fixtures for the Playwright suite.

Fixtures shared with the BE suite (``base_url``, ``teacher_password``,
``server_is_up``, ...) live in app_tests/conftest.py. pytest resolves fixtures
by walking up the directory tree, so tests under tests/FE already see those
without redeclaring them here -- keep this file to fixtures that only make
sense for a browser page.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from playwright.async_api import Page, expect


@pytest_asyncio.fixture
async def dashboard_page(page: Page, teacher_password: str) -> Page:
    """A page that has logged in through the real form and shows the dashboard.

    Uses the real form, not connect.sid injection, because:
    1. The execution time for both implementations was pretty similar.
    2. This is the real path that users use.

    Drawback: once login itself breaks, every test built on this fixture
    breaks too.
    """
    await page.goto("/")
    await page.get_by_placeholder("Password").fill(teacher_password)
    await page.get_by_role("button", name="Start").click()
    await expect(page.locator("#view-dashboard")).to_be_visible()
    return page


@pytest_asyncio.fixture
async def session_page(
    dashboard_page: Page,
    auth_client: httpx.AsyncClient,
    unique_name: str,
) -> AsyncIterator[tuple[Page, dict]]:
    """``dashboard_page``, already inside an active session for a freshly
    created, zero-point student.

    The timer controls (#timer-form, #timer-wrap, #clear-timer-btn) only
    exist inside #view-session, so anything testing them needs a session
    already running -- this is what test_dashboard.py's own session tests do
    by hand, pulled out because the timer tests all need the same setup with
    nothing test-specific about it.
    """
    created = (await auth_client.post("/api/students", json={"name": unique_name})).json()
    await dashboard_page.reload()
    await expect(dashboard_page.locator("#view-dashboard")).to_be_visible()

    await dashboard_page.locator("#active-student").select_option(value=str(created["id"]))
    await dashboard_page.get_by_role("button", name="Start session").click()
    await expect(dashboard_page.locator("#view-session")).to_be_visible()

    try:
        yield dashboard_page, created
    finally:
        await auth_client.delete(f"/api/students/{created['id']}")
