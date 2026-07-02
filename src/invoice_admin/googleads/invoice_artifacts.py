"""Deterministic filename and email strings from parsed invoice fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class InvoiceOutputFields:
    """Structured values used to build artifacts (from PDF parse + your month label)."""

    issue_date: date
    amount_eur: Decimal
    month_label: str
    client_prefix: str = ""


def build_renamed_pdf_filename(fields: InvoiceOutputFields) -> str:
    """ASCII-safe PDF filename: google-ads-invoice_{ISO date}_{amount}-EUR.pdf."""
    d = fields.issue_date.isoformat()
    amt = _eur_plain_amount(fields.amount_eur)
    return f"google-ads-invoice_{d}_{amt}-EUR.pdf"


def build_email_subject(fields: InvoiceOutputFields) -> str:
    """Short subject line for Jack’s monthly invoice mail."""
    disp = _eur_display_amount(fields.amount_eur)
    return f"Google Ads invoice — {fields.month_label} (EUR {disp})"


def build_email_body(fields: InvoiceOutputFields) -> str:
    """Plain-text body for Jack's monthly invoice mail."""
    return (
        f"Dear Jack,\n\n"
        f"Please find the GoogleAds invoice attached for {fields.month_label}.\n\n"
        f"Cheers,\n"
        f"Chaehan\n"
    )


def _eur_plain_amount(amount: Decimal) -> str:
    """Amount string for filenames: quantize to cents, drop redundant `.00`."""
    q = amount.quantize(Decimal("0.01"))
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _eur_commission_filename_amount(amount: Decimal) -> str:
    """Comma-grouped EUR digits for commission PDF filenames (after ``€``, no suffix symbol)."""
    q = amount.quantize(Decimal("0.01"))
    negative = q < 0
    q = abs(q)
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    frac: str | None
    if "." in s:
        whole_s, frac = s.split(".", 1)
    else:
        whole_s = s
        frac = None
    grouped_int = f"{int(whole_s):,}"
    body = grouped_int + (f".{frac}" if frac else "")
    return f"-{body}" if negative else body


def _eur_display_amount(amount: Decimal) -> str:
    """Two-decimal display for email copy."""
    return format(amount.quantize(Decimal("0.01")), "f")
