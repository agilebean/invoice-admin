"""Headed Chromium/Chrome (or Brave) helpers for saving invoice PDFs to disk."""

from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def build_chrome_options(
    *,
    download_dir: Path,
    user_data_dir: Path | None = None,
    binary_location: str | None = None,
    headless: bool = False,
) -> Options:
    """Chrome-family options: fixed download directory, optional profile + binary (e.g. Brave)."""
    opts = Options()
    dl = str(download_dir.resolve())
    prefs: dict[str, object] = {
        "download.default_directory": dl,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,
    }
    opts.add_experimental_option("prefs", prefs)
    if user_data_dir is not None:
        opts.add_argument(f"--user-data-dir={user_data_dir.resolve()}")
    if binary_location:
        opts.binary_location = binary_location
    if headless:
        opts.add_argument("--headless=new")
    return opts


def click_and_wait_for_pdf(
    driver: webdriver.Chrome,
    *,
    page_url: str,
    link_id: str,
    download_dir: Path,
    timeout_s: float = 60,
) -> Path:
    """Open ``page_url``, click ``#link_id``, return path to a new ``.pdf`` under ``download_dir``."""
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
