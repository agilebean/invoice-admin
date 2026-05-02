from pathlib import Path

import pytest

from googleads_invoice.billing_url import BillingUrlNotFoundError, extract_billing_url

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gmail"


def _load_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_extract_billing_url_happy_path_fixture() -> None:
    html = _load_fixture("billing_mail_happy.html")
    url = extract_billing_url(html)
    assert url == "https://payments.google.com/gp/w/home/invoice?id=REDACTED-REF"


def test_extract_billing_url_missing_raises_clear_error() -> None:
    html = _load_fixture("billing_mail_no_billing_url.html")
    with pytest.raises(BillingUrlNotFoundError) as excinfo:
        extract_billing_url(html)
    msg = str(excinfo.value).lower()
    assert "billing" in msg or "invoice" in msg or "url" in msg


def test_extract_billing_url_only_non_google_links_raises() -> None:
    html = _load_fixture("billing_mail_only_non_google_links.html")
    with pytest.raises(BillingUrlNotFoundError):
        extract_billing_url(html)
