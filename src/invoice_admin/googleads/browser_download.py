"""Browser helpers — re-exports from agentkit.browser, keeps invoice-admin-specific functions."""
from __future__ import annotations

from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from agentkit.browser import (
    ensure_brave_running,
    chrome_driver_attach,
    chrome_options_for_debugger as build_chrome_options_for_remote_debugging,
    build_chrome_options,
)


def click_and_wait_for_pdf(
    driver: webdriver.Chrome,
    *,
    page_url: str,
    link_id: str,
    download_dir: Path,
    timeout_s: float = 60,
) -> Path:
    """Open ``page_url``, click ``#link_id``, return path to a new ``.pdf`` under ``download_dir``."""
    import time
    download_dir.mkdir(parents=True, exist_ok=True)
    before = {p.resolve() for p in download_dir.glob("*.pdf")}
    driver.get(page_url)
    locator = (By.ID, link_id)
    WebDriverWait(driver, timeout_s).until(EC.element_to_be_clickable(locator))
    driver.find_element(*locator).click()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        after = {p.resolve() for p in download_dir.glob("*.pdf")}
        new = after - before
        if new:
            return max(new, key=lambda p: p.stat().st_mtime)
        time.sleep(0.2)
    msg = f"No new PDF in {download_dir} within {timeout_s}s"
    raise TimeoutError(msg)
