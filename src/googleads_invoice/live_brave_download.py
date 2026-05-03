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
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from googleads_invoice.browser_download import chrome_driver_attach
from googleads_invoice.live_brave_trace import save_live_brave_trace


class LiveBraveDownloadError(RuntimeError):
    """Raised when the Brave download flow fails (navigation, click, or timeout)."""


def _find_download_on_documents_page(driver: WebDriver) -> WebDriver:
    """Try strategies to find a download element on the billing Documents page.

    Strategies (in order):
    1. ``aria-label`` containing "Download File" or "Download" on a row.
    2. Visible ``<a>`` or ``<button>`` with text containing "Download".
    3. ``[jsaction]`` or ``[role=button]`` with download-related attributes.

    Returns the element if found; raises :exc:`LiveBraveDownloadError` otherwise.
    """
    selectors: list[str] = [
        # Inside the documentcenter iframe: individual row Download links are <a>Download</a>
        '//a[text()="Download"]',
        # Google Ads often uses aria-labels on clickable rows
        '//*[starts-with(@aria-label, "Download")]',
        # Explicit link/button/span with Download text
        '//a[contains(text(), "Download")]',
        '//button[contains(text(), "Download")]',
        '//span[contains(text(), "Download")]',
        '//div[contains(text(), "Download")]',
        # Any element with Download text inside a table cell
        '//td[contains(text(), "Download")]',
        # Material Design icon buttons
        '//*[@role="button" and contains(@aria-label, "Download")]',
        # Elements with download-related aria-label anywhere
        '//*[contains(@aria-label, "Download file")]',
        '//*[contains(@aria-label, "download")]',
    ]
    for xpath in selectors:
        elements = driver.find_elements(By.XPATH, xpath)
        visible = [el for el in elements if el.is_displayed()]
        if visible:
            return visible[0]
    # Last resort: scan the rendered DOM for any element whose trimmed text content is "Download"
    js_code = r"""
    let els = document.querySelectorAll('a, button, span, div, td, [role="button"]');
    for (let el of els) {
        if (el.textContent.trim() === 'Download') {
            return el;
        }
    }
    // Broader search: any element containing only "Download" text (no children)
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
        "No download button found on billing Documents page. "
        "A full HTML + PNG trace has been saved — inspect it to identify the correct "
        "selector, then update _find_download_on_documents_page()."
    )


def live_brave_download_pdf(
    *,
    debugger_address: str,
    deeplink_url: str,
    download_dir: Path,
    navigation_timeout_s: float = 45,
    download_timeout_s: float = 60,
) -> Path:
    """Attach to Brave, navigate the billing deeplink, click Download, return local PDF path.

    Steps
    -----
    1. Attach WebDriver to the running Brave via ``debugger_address``.
    2. Navigate to ``deeplink_url`` (typically a ``c.gle`` short link that redirects
       to the Google Ads billing Documents page).
    3. Wait for ``billing/documents`` to appear in the URL.
    4. Save an HTML + PNG trace to ``download_dir`` (or ``~/Downloads``) for
       identification when the download button can't be located.
    5. Find and click the Download element on the top row.
    6. Wait for a new ``.pdf`` to appear in ``download_dir``.
    7. Return the path to the downloaded PDF.

    Raises
    ------
    LiveBraveDownloadError
        If navigation, element finding, or download times out.
    """
    download_dir = download_dir.expanduser().resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    before = {p.resolve() for p in download_dir.glob("*.pdf")}

    driver = chrome_driver_attach(
        debugger_address=debugger_address,
        download_dir=download_dir,
    )

    # Tell Chrome/Brave to auto-download files without showing the confirmation dialog
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(download_dir),
        })
    except Exception:
        pass  # CDP not available; downloads will show a dialog
    try:
        driver.get(deeplink_url)
        # Switch to the newest tab if one appeared (c.gle redirects may open new tab)
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
            # Check if a new tab opened and the original tab never navigated
            all_urls = []
            try:
                for h in driver.window_handles:
                    driver.switch_to.window(h)
                    all_urls.append(driver.current_url)
            except Exception:
                pass
            trace_paths = save_live_brave_trace(driver, label="billing_nav_failed")
            raise LiveBraveDownloadError(
                f"Navigation timed out waiting for billing/documents after "
                f"{navigation_timeout_s}s.\n"
                f"Trace saved: {trace_paths[0]}, {trace_paths[1]}\n"
                f"Tab URLs: {all_urls}"
            ) from exc

        # The billing documents table is inside an iframe from payments.google.com
        # Switch to it so we can find and click Download links
        try:
            doc_iframe = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "iframe[src*='documentcenter']")
            )
            driver.switch_to.frame(doc_iframe)
        except Exception:
            pass  # No iframe found; _find may still work on the top-level document

        # Wait for dynamically rendered content (React/SPA table)
        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script(
                    "return document.documentElement.innerText.includes('Download')"
                )
            )
        except Exception:
            pass  # proceed anyway, _find may still work

        try:
            download_el = _find_download_on_documents_page(driver)
        except LiveBraveDownloadError:
            # Diagnostic: get full body text + any elements containing 'Download' or 'Invoice'
            try:
                body_text = driver.execute_script("return document.body.innerText;")
            except Exception:
                body_text = "(could not get body text)"

            try:
                diag = driver.execute_script(
                    "let items = []; "
                    "document.querySelectorAll('*').forEach(el => {"
                    "  let t = (el.textContent || '').trim(); "
                    "  if (t && (t.includes('Download') || t.includes('Invoice'))) {"
                    "    items.push(el.tagName + '#' + (el.id || '') + '.' + (el.className || '').slice(0, 60) + ':' + t.slice(0, 160));"
                    "  }"
                    "}); return items;"
                )
                diag_text = "\n".join(f"  [{i}] {x}" for i, x in enumerate(diag or []))
                if not diag_text:
                    diag_text = "(no Download/Invoice elements)"
            except Exception as exc:
                diag_text = f"(diagnostic failed: {exc})"
            try:
                # Deep diagnostic: shadow DOMs, iframes, and all text content
                tabs_text = driver.execute_script(
                    "let items = [];\n"
                    "// Check shadow DOMs recursively\n"
                    "function findInShadow(root, depth) {\n"
                    "  if (depth > 5) return;\n"
                    "  let all = root.querySelectorAll('*');\n"
                    "  for (let el of all) {\n"
                    "    if (el.shadowRoot) {\n"
                    "      items.push('SHADOW in ' + el.tagName + ':' + (el.shadowRoot.textContent || '').trim().slice(0, 200));\n"
                    "      findInShadow(el.shadowRoot, depth + 1);\n"
                    "    }\n"
                    "  }\n"
                    "}\n"
                    "findInShadow(document, 0);\n"
                    "// Check iframes and their content\n"
                    "items.push('IFRAMES: ' + document.querySelectorAll('iframe').length);\n"
                    "for (let f of document.querySelectorAll('iframe')) {\n"
                    "  try { items.push('  iframe:' + (f.contentDocument.body.innerText || '').trim().slice(0, 300)); } catch(e) { items.push('  iframe: blocked'); }\n"
                    "}\n"
                    "// Get text of main content containers specifically\n"
                    "let selectors = ['.awsm-content', '.awsm-child-content', 'awsml-billing-documents', '[class*=billing]', '[class*=document]'];\n"
                    "for (let sel of selectors) {\n"
                    "  let el = document.querySelector(sel);\n"
                    "  if (el) items.push(sel + ': ' + (el.textContent || '').trim().slice(0, 500));\n"
                    "}\n"
                    "// Check for Angular-specific elements\n"
                    "items.push('Angular components: ' + document.querySelectorAll('[class*=ng], [class*=_nghost], [class*=_ngcontent], awsml-*, mat-*').length);\n"
                    "// Full body text with newlines preserved\n"
                    "items.push('BODY TEXT:\n' + (document.body.innerText || '').slice(0, 5000));\n"
                    "return items;"
                )
                tabs_line = "\n".join(f"  {x}" for x in (tabs_text or []))
            except Exception as exc:
                tabs_line = f"(diagnostic failed: {exc})"
            diag_text = "=== Full body text (first 3000 chars) ===\n" + (body_text or "")[:3000] + "\n\n=== Download/Invoice elements ===\n" + diag_text + "\n\n=== Tabs/buttons ===\n" + tabs_line
            trace_paths = save_live_brave_trace(driver, label="billing_no_download_btn")
            raise LiveBraveDownloadError(
                f"Reached billing/documents but couldn't locate the Download element.\n"
                f"Trace saved: {trace_paths[0]}, {trace_paths[1]}\n"
                f"Rendered text snippets (first 100):\n{diag_text}"
            )

        download_el.click()

        # The Download link opens a new tab with the document URL.
        try:
            current_handles = set(driver.window_handles)
            WebDriverWait(driver, 10).until(
                lambda d: len(set(d.window_handles) - current_handles) > 0
            )
            new_handles = list(set(driver.window_handles) - current_handles)
            if new_handles:
                driver.switch_to.window(new_handles[0])
        except Exception:
            pass  # No new tab opened

        deadline = time.monotonic() + download_timeout_s
        while time.monotonic() < deadline:
            after = {p.resolve() for p in download_dir.glob("*.pdf")}
            new = after - before
            if new:
                return max(new, key=lambda p: p.stat().st_mtime)
            time.sleep(0.3)

        trace_paths = save_live_brave_trace(driver, label="billing_download_timeout")
        raise LiveBraveDownloadError(
            f"Clicked Download but no new PDF appeared in {download_dir} within "
            f"{download_timeout_s}s.\n"
            f"Trace saved: {trace_paths[0]}, {trace_paths[1]}"
        )
    finally:
        driver.quit()
