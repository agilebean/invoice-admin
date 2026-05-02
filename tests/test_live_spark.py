"""Touch the real Spark app (macOS) and optionally HTML you exported from Spark.

Skipped unless ``RUN_LIVE_SPARK=1`` on macOS outside CI — see ``conftest.py``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from googleads_invoice.billing_url import BillingUrlNotFoundError, extract_billing_url


@pytest.mark.live_spark
def test_live_spark_app_scriptable() -> None:
    """Prove Spark is installed and returns a version via AppleScript."""
    proc = subprocess.run(
        ["osascript", "-e", 'tell application "Spark" to get version'],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert proc.stdout.strip(), "Spark returned empty version"


@pytest.mark.live_spark
def test_live_spark_exported_mail_contains_billing_url() -> None:
    """If ``GOOGLEADS_SPARK_MAIL_HTML`` points to a file you saved from Spark, extract billing URL."""
    raw = (os.environ.get("GOOGLEADS_SPARK_MAIL_HTML") or "").strip()
    if not raw:
        pytest.skip("Set GOOGLEADS_SPARK_MAIL_HTML to the path of HTML exported from Spark")
    path = Path(raw).expanduser()
    assert path.is_file(), f"Not a file: {path}"
    html = path.read_text(encoding="utf-8", errors="replace")
    assert "<html" in html.lower() or "<body" in html.lower() or "href=" in html.lower(), (
        "Does not look like HTML mail export"
    )
    try:
        url = extract_billing_url(html)
    except BillingUrlNotFoundError as e:
        pytest.fail(f"Spark export had no billing URL extractable like fixtures: {e}")
    assert "payments.google.com" in url or "pay.google.com" in url, url
