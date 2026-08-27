"""Throwaway: compare cookie-injected login vs UI login for a dashboard fixture."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
import pytest
from playwright.async_api import BrowserContext, expect

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _inject(context: BrowserContext, base_url: str, password: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as api:
        res = await api.post("/api/login", json={"password": password})
        assert res.status_code == 200, res.text
        sid = res.cookies["connect.sid"]
    await context.add_cookies(
        [
            {
                "name": "connect.sid",
                "value": sid,
                "domain": urlsplit(base_url).hostname,
                "path": "/",
                "httpOnly": True,
            }
        ]
    )


@pytest.mark.parametrize("n", range(5))
async def test_cookie_login(
    context: BrowserContext, base_url: str, teacher_password: str, n: int
) -> None:
    await _inject(context, base_url, teacher_password)
    page = await context.new_page()
    await page.goto("/")
    await expect(page.locator("#view-dashboard")).to_be_visible()


@pytest.mark.parametrize("n", range(5))
async def test_ui_login(context: BrowserContext, teacher_password: str, n: int) -> None:
    page = await context.new_page()
    await page.goto("/")
    await page.get_by_placeholder("Password").fill(teacher_password)
    await page.get_by_role("button", name="Start").click()
    await expect(page.locator("#view-dashboard")).to_be_visible()
