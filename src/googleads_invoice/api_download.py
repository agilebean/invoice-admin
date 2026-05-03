"""Download Google Ads invoice PDF via the Google Ads internal billing API.

Alternative to :mod:`~googleads_invoice.live_brave_download` — no Selenium or
ChromeDriver needed.  Uses the same OAuth2 credentials as the Gmail API backend,
**but** the token must include the ``adwords`` scope.

Setup
-----
1.  In Google Cloud Console → APIs & Services → OAuth consent screen,
    add the scope ``https://www.googleapis.com/auth/adwords``.

2.  Delete your old token file and re-authorize::

        python scripts/get_gmail_token.py

    The new token will have both ``gmail.readonly`` and ``adwords`` scopes.

3.  That's it — ``googleads-invoice run-month --download-method api`` will
    use the same ``GOOGLEADS_OAUTH_TOKEN`` env var.

Strategy
--------
Instead of following the ``c.gle`` redirect chain (which requires browser
session cookies), the module calls the **Google Ads internal REST API**
(``googleads.googleapis.com``) — the same API that the billing Documents
page uses — to obtain a direct PDF download URL.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials


class ApiDownloadError(RuntimeError):
    """Raised when the API-based download flow fails at any step."""


# Google Ads internal billing-documents endpoint (same API the web UI calls).
_ADS_API_VERSIONS = ["v19", "v18", "v17", "v16", "v15", "v14"]
_ADS_API_BASE = "https://googleads.googleapis.com"


def _extract_ids_from_url(billing_url: str) -> dict[str, str]:
    """Extract customer ID and billing ID from a Google Ads billing URL."""
    parsed = urlparse(billing_url)
    qs = parse_qs(parsed.query)
    ids: dict[str, str] = {}

    for key, vals in qs.items():
        if not vals:
            continue
        v = vals[0]
        kl = key.lower()
        if "billingid" in kl or "billing_id" in kl:
            ids["billing_id"] = v
        elif "customer" in kl:
            ids["customer_id"] = v

    path = parsed.path.lower()
    m = re.search(r'customer[^/]*[=/](\d+)', path)
    if m:
        ids.setdefault("customer_id", m.group(1))
    m = re.search(r'billing[^/]*[=/](\d+)', path)
    if m:
        ids.setdefault("billing_id", m.group(1))

    return ids


def _try_ads_internal_api(
    session: AuthorizedSession,
    billing_url: str,
    download_dir: Path,
) -> Path | None:
    """Query Google Ads internal billing-documents API for invoice PDF URLs."""
    ids = _extract_ids_from_url(billing_url)
    customer_id = ids.get("customer_id", "")
    if not customer_id:
        return None

    for version in _ADS_API_VERSIONS:
        endpoint = f"{_ADS_API_BASE}/{version}/customers/{customer_id}/billingDocuments"
        try:
            resp = session.get(endpoint, timeout=15, headers={
                "Accept": "application/json",
            })
            if resp.status_code == 401:
                raise ApiDownloadError(
                    "Google Ads API returned HTTP 401.\n\n"
                    "Your OAuth token needs the 'adwords' scope.\n"
                    "See docs/googleads-api-scope.md for setup instructions."
                )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except ApiDownloadError:
            raise
        except Exception:
            continue

        pdf_url = _extract_download_url(data)
        if pdf_url:
            try:
                return _download_pdf(session, pdf_url, download_dir)
            except ApiDownloadError:
                continue

    return None


def _extract_download_url(data: object) -> str | None:
    """Walk JSON response looking for a PDF download URL field."""
    if isinstance(data, dict):
        for field in ("pdfDownloadUrl", "downloadUrl", "invoiceUrl", "pdfUrl"):
            url = data.get(field)
            if isinstance(url, str) and url.startswith("http"):
                return url
        for val in data.values():
            result = _extract_download_url(val)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_download_url(item)
            if result:
                return result
    return None


def _download_pdf(session: AuthorizedSession, pdf_url: str, download_dir: Path) -> Path:
    """Download a PDF from ``pdf_url``, following redirects to CDN."""
    resp = session.get(pdf_url, timeout=60, stream=True)
    while 300 <= resp.status_code < 400:
        loc = resp.headers.get("Location")
        if not loc:
            break
        resp = session.get(loc, timeout=60, stream=True)

    if resp.status_code != 200:
        raise ApiDownloadError(
            f"PDF download returned HTTP {resp.status_code} for {pdf_url}"
        )

    out = download_dir / f"invoice_api_{int(time.time())}.pdf"
    with open(out, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

    if out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise ApiDownloadError(f"Downloaded PDF is empty: {pdf_url}")
    return out


# ─── Public API ──────────────────────────────────────────────────────────


def api_download_pdf(
    *,
    billing_url: str,
    credentials: Credentials,
    download_dir: Path,
) -> Path:
    """Download invoice PDF using the Google Ads internal billing API.

    Parameters
    ----------
    billing_url:
        The billing deeplink URL from the Gmail notification.
    credentials:
        OAuth2 credentials that **must** include the ``adwords`` scope.
    download_dir:
        Directory to save the PDF into (created if missing).

    Raises
    ------
    ApiDownloadError
        If download fails or the token lacks the required scope.
    """
    download_dir = download_dir.expanduser().resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    session = AuthorizedSession(credentials)

    result = _try_ads_internal_api(session, billing_url, download_dir)
    if result is not None:
        return result

    raise ApiDownloadError(
        "Could not download invoice PDF via the Google Ads API.\n\n"
        "Tried API versions: " + ", ".join(_ADS_API_VERSIONS) + "\n\n"
        "Possible reasons:\n"
        "  • The 'adwords' scope is missing from your OAuth token.\n"
        "  • No Google Ads customer ID was found in the billing URL.\n"
        "  • The Google Ads account has no invoices yet.\n\n"
        "Fallback: use 'live-brave-download' (requires Brave + remote debugging)."
    )
