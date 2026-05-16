"""Headed Chromium/Chrome (or Brave) helpers for saving invoice PDFs to disk."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

_BRAVE_PATH_MACOS = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"


def _brave_cdp_ready(address: str, timeout_s: float = 2.0) -> bool:
    """Return True if Brave's CDP endpoint answers at *address* (host:port)."""
    try:
        req = urllib.request.Request(f"http://{address}/json/version")
        urllib.request.urlopen(req, timeout=timeout_s)
        return True
    except Exception:
        return False


def ensure_brave_running(
    address: str = "127.0.0.1:9222",
    *,
    launch_timeout_s: float = 30.0,
) -> None:
    """Launch Brave with ``--remote-debugging-port`` if it is not already listening.

    Raises ``RuntimeError`` when Brave does not become ready within
    *launch_timeout_s* seconds.
    """
    if _brave_cdp_ready(address):
        return

    binary = _BRAVE_PATH_MACOS
    if not Path(binary).exists():
        # Not on macOS or Brave not in standard location — trust the caller
        # to have the browser running already.
        raise RuntimeError(
            f"Brave not found at {binary!r} and is not listening on {address}. "
            "Start Brave manually with --remote-debugging-port first."
        )

    host, _, port_str = address.partition(":")
    port = int(port_str)

    with open(os.devnull, "w") as devnull:
        subprocess.Popen(
            [binary, f"--remote-debugging-port={port}", "--no-first-run", "--disable-extensions"],
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,
        )

    print(f"Launched Brave (port {port}), waiting up to {launch_timeout_s:.0f}s...", file=sys.stderr)
    deadline = time.monotonic() + launch_timeout_s
    while time.monotonic() < deadline:
        if _brave_cdp_ready(address):
            print("Brave ready.", file=sys.stderr)
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"Brave did not become ready on {address} within {launch_timeout_s:.0f}s."
    )


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


def build_chrome_options_for_remote_debugging(
    *,
    debugger_address: str,
    download_dir: Path | None = None,
) -> Options:
    """Attach WebDriver to an **already-running** Chrome-family browser (e.g. **Brave**).

    Start Brave first with a debug port, e.g. on macOS::

        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \\
            --remote-debugging-port=9222

    Then use ``debugger_address="127.0.0.1:9222"``. Do **not** use Cursor's in-IDE browser for
    Google Ads / billing flows — it does not share your Brave profile.
    """
    opts = Options()
    opts.add_experimental_option("debuggerAddress", debugger_address.strip())
    if download_dir is not None:
        dl = str(download_dir.resolve())
        prefs: dict[str, object] = {
            "download.default_directory": dl,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
        }
        opts.add_experimental_option("prefs", prefs)
    return opts


def chrome_driver_attach(
    *,
    debugger_address: str,
    download_dir: Path | None = None,
) -> webdriver.Chrome:
    """Return a WebDriver session attached to the browser listening on ``debugger_address``."""
    opts = build_chrome_options_for_remote_debugging(
        debugger_address=debugger_address,
        download_dir=download_dir,
    )
    return webdriver.Chrome(options=opts)


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
