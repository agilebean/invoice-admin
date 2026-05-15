"""Filename helpers for ingested invoices."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone


def _clean_name(text: str, max_len: int = 60) -> str:
    """Normalize text for human-readable filenames. Keeps spaces, removes unsafe chars."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = s.replace("/", "-").replace(":", "-").replace(";", "-")
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = s.strip(" .-")
    if len(s) > max_len:
        s = s[:max_len].rsplit(" ", 1)[0].strip(" .-")
    return s or "unknown"


def slugify_vendor(text: str) -> str:
    """Slugify a vendor name for use in filenames and identifiers."""
    cleaned = _clean_name(text, max_len=60)
    slug = re.sub(r"\s+", "-", cleaned).lower()
    if not re.search(r"[a-z0-9]", slug):
        return "vendor"
    return slug


def amount_currency_slug(amount: float | None, currency: str | None) -> str:
    ccy = (currency or "EUR").strip().upper() or "EUR"
    if amount is None:
        return f"0{ccy}"
    if float(amount).is_integer():
        return f"{int(amount)}{ccy}"
    return f"{float(amount):.2f}".rstrip("0").rstrip(".") + ccy


def invoice_date_for_filename(invoice_date: str | None) -> str:
    if invoice_date and len(invoice_date) >= 10:
        return invoice_date[:10]
    return datetime.now(timezone.utc).date().isoformat()


def build_invoice_pdf_filename(
    *,
    invoice_date: str | None,
    vendor: str | None,
    amount: float | None,
    currency: str | None,
    document_topic: str | None = None,
) -> str:
    """Return `YYYY-MM-DD <vendor> [- <topic>] [- <amount><CCY>].pdf`."""
    day = invoice_date_for_filename(invoice_date)
    vendor_name = _clean_name(vendor or "unknown", max_len=50)
    frags = [day, vendor_name]
    if document_topic:
        topic = _clean_name(document_topic, max_len=60)
        if topic and topic.lower() != vendor_name.lower():
            frags.append(f"- {topic}")
    if amount is not None and amount > 0:
        frags.append(f"- {amount_currency_slug(amount, currency)}")
    return "_".join(frags) + ".pdf"


def build_failure_filename(
    *,
    vendor: str | None,
    invoice_date: str | None,
    document_topic: str | None,
) -> str:
    day = invoice_date_for_filename(invoice_date)
    vendor_name = _clean_name(vendor or "unknown", max_len=50)
    frags = [day, vendor_name]
    if document_topic:
        topic = _clean_name(document_topic, max_len=60)
        if topic and topic.lower() != vendor_name.lower():
            frags.append(f"- {topic}")
    return "_".join(frags) + ".pdf"


def build_invoice_pdf_filename_with_vendor_slug(
    *,
    invoice_date: str | None,
    vendor_slug: str,
    amount: float | None,
    currency: str | None,
) -> str:
    return build_invoice_pdf_filename(
        invoice_date=invoice_date,
        vendor=vendor_slug.replace("-", " ").title(),
        amount=amount,
        currency=currency,
    )
