from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest
import pytest_asyncio

from app_tests.exponential_backoff import retry_async


DEFAULT_BASE_URL = "http://127.0.0.1:3000"

DEFAULT_PASSWORD = "teacher"

REQUEST_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("POINTS_API_URL", DEFAULT_BASE_URL)


