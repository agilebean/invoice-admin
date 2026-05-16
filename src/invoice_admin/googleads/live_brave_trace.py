"""Optional HTML + screenshot dumps when debugging `live_brave` against real Brave.

Writes under ``~/Downloads`` by default (see interview); override with
``GOOGLEADS_LIVE_BRAVE_TRACE_DIR``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from selenium.webdriver.remote.webdriver import WebDriver

_ENV_TRACE = "RUN_LIVE_BRAVE_TRACE"
_ENV_TRACE_DIR = "GOOGLEADS_LIVE_BRAVE_TRACE_DIR"


def live_brave_trace_enabled() -> bool:
    return os.environ.get(_ENV_TRACE, "").strip() == "1"


def live_brave_trace_dir() -> Path:
    raw = (os.environ.get(_ENV_TRACE_DIR) or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "Downloads"


def save_live_brave_trace(driver: WebDriver, *, label: str) -> tuple[Path, Path]:
    """Write page source + PNG to the trace directory; return ``(html_path, png_path)``."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80]
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = live_brave_trace_dir()
    base.mkdir(parents=True, exist_ok=True)
    stem = f"live_brave_{safe}_{ts}"
    html_path = base / f"{stem}.html"
    png_path = base / f"{stem}.png"
    html_path.write_text(driver.page_source or "", encoding="utf-8")
    driver.save_screenshot(str(png_path))
    return html_path, png_path


def maybe_save_live_brave_trace(driver: WebDriver, *, label: str) -> None:
    """If ``RUN_LIVE_BRAVE_TRACE=1``, save trace files; otherwise no-op."""
    if not live_brave_trace_enabled():
        return
    save_live_brave_trace(driver, label=label)
