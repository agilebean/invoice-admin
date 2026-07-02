"""Attach to a running Brave instance, navigate the billing deeplink, and download the invoice PDF.

Step 4 of the monthly flow: identify the billing Documents page UI and download the
most recent invoice. Also saves an HTML+PNG trace for DOM identification when the
download button can't be located automatically.

Usage
-----
1. Start Brave with remote debugging::

       "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \\
           --remote-debugging-port=9222

2. Run::

       GOOGLEADS_CONFIRM_LIVE_BRAVE=1 \\
           GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \\
           GOOGLEADS_BILLING_DEEPLINK="https://c.gle/..." \\
           googleads-invoice live-brave-download
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from invoice_admin.googleads.browser_download import chrome_driver_attach
from invoice_admin.googleads.live_brave_trace import save_live_brave_trace
from invoice_admin.googleads.billing_period import billing_month_label_for_previous_calendar_month
from invoice_admin.googleads.invoice_pdf import parse_invoice_pdf
from invoice_admin.googleads.invoice_artifacts import InvoiceOutputFields


class LiveBraveDownloadError(RuntimeError):
    """Raised when the Brave download flow fails (navigation, click, or timeout)."""


def _build_download_filename(fields: InvoiceOutputFields) -> str:
    """Build filename like '2026-06-30 Glugglejug GoogleAds Invoice June €6,789.06.pdf'."""
    d = fields.issue_date.isoformat()
    q = fields.amount_eur.quantize(Decimal("0.01"))
    s = format(q, "f")
    if "." in s:
        int_part, frac_part = s.rsplit(".", 1)
        frac_part = frac_part.rstrip("0") or "0"
        amt = f"{int(int_part):,}" if frac_part == "0" else f"{int(int_part):,}.{frac_part}"
    else:
        amt = f"{int(s):,}"
    prefix = f"{fields.client_prefix} " if fields.client_prefix else ""
    month_name = fields.month_label.split()[0]
    return f"{d} {prefix}GoogleAds Invoice {month_name} €{amt}.pdf"


def _find_download_on_documents_page(driver: WebDriver) -> WebDriver:
    """Try strategies to find a download element on the billing Documents page."""
    selectors: list[str] = [
        '//a[text()="Download"]',
        '//*[starts-with(@aria-label, "Download")]',
        '//a[contains(text(), "Download")]',
        '//button[contains(text(), "Download")]',
        '//span[contains(text(), "Download")]',
        '//div[contains(text(), "Download")]',
        '//td[contains(text(), "Download")]',
        '//*[@role="button" and contains(@aria-label, "Download")]',
        '//*[contains(@aria-label, "Download file")]',
        '//*[contains(@aria-label, "download")]',
    ]
    for xpath in selectors:
        elements = driver.find_elements(By.XPATH, xpath)
        visible = [el for el in elements if el.is_displayed()]
        if visible:
            return visible[0]
    js_code = r"""
    let els = document.querySelectorAll('a, button, span, div, td, [role="button"]');
    for (let el of els) {
        if (el.textContent.trim() === 'Download') {
            return el;
        }
    }
    let all = document.querySelectorAll('*');
    for (let el of all) {
        if (el.textContent.trim() === 'Download' && !el.querySelector('*')) {
            return el;
        }
    }
    return null;
    """
    result = driver.execute_script(js_code)
    if result is not None:
        return result
    raise LiveBraveDownloadError(
        "No download button found on billing Documents page."
    )


def live_brave_download_pdf(
    *,
    debugger_address: str,
    deeplink_url: str,
    download_dir: Path,
    navigation_timeout_s: float = 45,
    download_timeout_s: float = 120,
    verbose: bool = True,
    client_prefix: str = "",
) -> Path:
    """Attach to Brave, navigate the billing deeplink, click Download, return local PDF path."""

    _t0 = time.monotonic()
    _last_t = [_t0]
    _STEP = 6

    def _step(n: int, msg: str) -> None:
        if not verbose:
            return
        now = time.monotonic()
        step_dur = now - _last_t[0]
        total = now - _t0
        _last_t[0] = now
        print(f"  [{n}/{_STEP}] +{step_dur:.1f}s/{total:.1f}s {msg}", flush=True)

    _step(1, "Attaching to Brave...")
    download_dir = download_dir.expanduser().resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    driver = chrome_driver_attach(
        debugger_address=debugger_address,
        download_dir=download_dir,
    )

    # CDP: auto-download files without showing the confirmation dialog (confirmed working)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(download_dir),
        })
    except Exception:
        pass

    _step(2, "Navigating to billing documents...")

    try:
        driver.get(deeplink_url)
        try:
            handles = driver.window_handles
            if len(handles) > 1:
                driver.switch_to.window(handles[-1])
        except Exception:
            pass

        try:
            WebDriverWait(driver, navigation_timeout_s).until(
                lambda d: "billing/documents" in (d.current_url or "").lower(),
            )
        except Exception as exc:
            all_urls = []
            try:
                for h in driver.window_handles:
                    driver.switch_to.window(h)
                    all_urls.append(driver.current_url)
            except Exception:
                pass
            trace_paths = save_live_brave_trace(driver, label="billing_nav_failed")
            raise LiveBraveDownloadError(
                f"Navigation timed out after {navigation_timeout_s}s.\n"
                f"Trace saved: {trace_paths[0]}, {trace_paths[1]}\n"
                f"Tab URLs: {all_urls}"
            ) from exc

        _step(3, "Switching to document iframe and locating Download...")

        try:
            doc_iframe = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "iframe[src*='documentcenter']")
            )
            driver.switch_to.frame(doc_iframe)
        except Exception:
            pass

        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script(
                    "return document.documentElement.innerText.includes('Download')"
                )
            )
        except Exception:
            pass

        try:
            download_el = _find_download_on_documents_page(driver)
        except LiveBraveDownloadError:
            trace_paths = save_live_brave_trace(driver, label="billing_no_download_btn")
            raise LiveBraveDownloadError(
                f"Reached billing/documents but couldn't locate the Download element.\n"
                f"Trace saved: {trace_paths[0]}, {trace_paths[1]}"
            )

        _step(4, "Clicking Download...")
        download_el.click()
        driver.switch_to.default_content()
        time.sleep(1)

        _step(5, "Waiting for PDF download...")
        deadline = time.monotonic() + download_timeout_s
        start_mtime = time.monotonic() - 5

        pdf_path: Path | None = None
        while time.monotonic() < deadline:
            for p in download_dir.iterdir():
                if p.suffix.lower() == ".pdf" and p.stat().st_size > 0:
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        continue
                    if mtime > start_mtime:
                        pdf_path = p.resolve()
                        break
            if pdf_path:
                break
            time.sleep(0.3)

        if pdf_path is None:
            recent = sorted(
                [p for p in download_dir.iterdir() if p.suffix.lower() == ".pdf"],
                key=lambda p: p.stat().st_mtime, reverse=True
            )[:5]
            recent_info = "\n  ".join(
                f"{p.name} (modified {p.stat().st_mtime:.0f}, {p.stat().st_size} bytes)"
                for p in recent
            )
            trace_paths = save_live_brave_trace(driver, label="billing_download_timeout")
            raise LiveBraveDownloadError(
                f"No new PDF in {download_dir} within {download_timeout_s}s.\n"
                f"Existing PDFs:\n  {recent_info}\n"
                f"Trace saved: {trace_paths[0]}, {trace_paths[1]}"
            )

        _step(5, f"Parsing {pdf_path.name} ({pdf_path.stat().st_size} bytes)...")
        issue_date, amount_eur = parse_invoice_pdf(pdf_path)
        month_label = billing_month_label_for_previous_calendar_month()
        fields = InvoiceOutputFields(
            issue_date=issue_date,
            amount_eur=amount_eur,
            month_label=month_label,
            client_prefix=client_prefix,
        )

        _step(6, "Renaming...")
        final_name = _build_download_filename(fields)
        out_path = (download_dir / final_name).resolve()
        if out_path.is_file():
            stem = out_path.stem
            ext = out_path.suffix
            for i in range(1, 100):
                alt = download_dir / f"{stem} ({i}){ext}"
                if not alt.is_file():
                    out_path = alt
                    break
        pdf_path.rename(out_path)
        return out_path

    finally:
        driver.quit()
