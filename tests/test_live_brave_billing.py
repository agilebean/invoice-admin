"""Attach to *your* running Brave (--remote-debugging-port) and open the real billing deeplink.

Skipped everywhere unless ``RUN_LIVE_BRAVE=1`` and required env vars are set — see ``conftest.py``.
"""

from __future__ import annotations

import os

import pytest
from selenium.webdriver.support.ui import WebDriverWait

from googleads_invoice.browser_download import chrome_driver_attach
from googleads_invoice.live_brave_trace import maybe_save_live_brave_trace


@pytest.mark.live_brave
def test_live_brave_billing_deeplink_reaches_documents_page() -> None:
    """Open the monthly ``c.gle`` URL in the **current** Brave tab; land on **billing/documents**.

    Requires Brave already logged into the Google Ads account that owns billing.
    """
    addr = os.environ["GOOGLEADS_BROWSER_DEBUGGER_ADDRESS"].strip()
    link = os.environ["GOOGLEADS_BILLING_DEEPLINK"].strip()
    driver = chrome_driver_attach(debugger_address=addr, download_dir=None)
    try:
        driver.get(link)
        WebDriverWait(driver, 45).until(
            lambda d: "billing/documents" in d.current_url.lower(),
        )
        assert "ads.google.com" in driver.current_url.lower(), driver.current_url
        maybe_save_live_brave_trace(driver, label="billing_documents")
    except BaseException:
        maybe_save_live_brave_trace(driver, label="billing_documents_failed")
        raise
    finally:
        driver.quit()
