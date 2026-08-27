"""FE-only fixtures for the Playwright suite.

Fixtures shared with the BE suite (``base_url``, ``teacher_password``,
``server_is_up``, ...) live in app_tests/conftest.py. pytest resolves fixtures
by walking up the directory tree, so tests under tests/FE already see those
without redeclaring them here -- keep this file to fixtures that only make
sense for a browser page.
"""

from __future__ import annotations

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
