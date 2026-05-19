"""Pytest fixtures.

pytest-playwright provides `page`, `browser`, `context` (and honors --tracing /
--video / --screenshot CLI flags). We override `browser_context_args` to allow
self-signed certs, and add a `snap` fixture for step-by-step screenshots.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page

PROJECT_ROOT = Path(__file__).resolve().parent
SCREENSHOT_DIR = PROJECT_ROOT / "reports" / "screenshots"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture
def snap(page: Page, request):
    """Capture a labeled screenshot. Usage: `snap("after clicking login")`."""
    out_dir = SCREENSHOT_DIR / request.node.name
    out_dir.mkdir(parents=True, exist_ok=True)
    counter = {"n": 0}

    def _snap(label: str = "") -> str:
        counter["n"] += 1
        safe = "".join(c if c.isalnum() else "_" for c in (label or "step"))[:60]
        out = out_dir / f"{counter['n']:02d}_{safe}.png"
        try:
            page.screenshot(path=str(out), full_page=False)
        except Exception:
            return ""
        return str(out)

    return _snap
