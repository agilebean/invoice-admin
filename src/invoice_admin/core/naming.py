"""Filename helpers for ingested invoices."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone


def slugify_vendor(name: str) -> str:
    """Normalize vendor name for filesystem-safe slugs (NFKD + ASCII)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace(" ", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "vendor"


def amount_currency_slug(amount: float | None, currency: str | None) -> str:
    """Build `<amount><CCY>` fragment for filenames (e.g. `487EUR`)."""
    ccy = (currency or "EUR").strip().upper() or "EUR"
    if amount is None:
        return f"0{ccy}"
    if float(amount).is_integer():
        amt = str(int(amount))
    else:
        amt = f"{float(amount):.2f}".rstrip("0").rstrip(".")
    return f"{amt}{ccy}"


def invoice_date_for_filename(invoice_date: str | None) -> str:
    """Prefer invoice issue date (YYYY-MM-DD); default to today's UTC date."""
    if invoice_date and len(invoice_date) >= 10:
        return invoice_date[:10]
    return datetime.now(timezone.utc).date().isoformat()


def build_invoice_pdf_filename(
    *,
    invoice_date: str | None,
    vendor: str | None,
    amount: float | None,
    currency: str | None,
) -> str:
    """Return `YYYY-MM-DD_<vendor-slug>_<amount><CCY>.pdf` stem+suffix."""
    day = invoice_date_for_filename(invoice_date)
    slug = slugify_vendor(vendor or "unknown")
    ac = amount_currency_slug(amount, currency)
    return f"{day}_{slug}_{ac}.pdf"


def build_invoice_pdf_filename_with_vendor_slug(
    *,
    invoice_date: str | None,
    vendor_slug: str,
    amount: float | None,
    currency: str | None,
) -> str:
    """Same as build_invoice_pdf_filename but caller supplies a slug stem (hyphens allowed)."""
    return build_invoice_pdf_filename(
        invoice_date=invoice_date,
        vendor=vendor_slug.replace("-", " "),
        amount=amount,
        currency=currency,
    )
