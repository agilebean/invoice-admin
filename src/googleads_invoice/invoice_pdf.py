"""Parse invoice issue date and EUR total from PDF bytes or paths."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class InvoicePdfError(ValueError):
    """Raised when input is not a readable PDF or expected invoice fields are missing."""


def parse_invoice_pdf(source: str | Path | bytes) -> tuple[date, Decimal]:
    """Return invoice issue date and total amount in EUR from synthetic or real invoice PDFs."""
    if isinstance(source, (str, Path)):
        data = Path(source).expanduser().read_bytes()
    else:
        data = source
    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except PdfReadError as e:
        raise InvoicePdfError(f"Not a valid PDF or unreadable: {e}") from e

    text_parts: list[str] = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts)
    issue = _extract_issue_date(text)
    amount = _extract_amount_due_eur(text)
    return issue, amount


def _extract_issue_date(text: str) -> date:
    match = re.search(r"Invoice date:\s*(\d{4}-\d{2}-\d{2})", text)
    if not match:
        raise InvoicePdfError(
            "Could not parse invoice date (expected a line like 'Invoice date: YYYY-MM-DD')."
        )
    return date.fromisoformat(match.group(1))


def _extract_amount_due_eur(text: str) -> Decimal:
    match = re.search(r"Amount due:\s*(.+)", text)
    if not match:
        raise InvoicePdfError("Could not find amount due line in PDF text.")
    raw = match.group(1).strip()
    raw = re.sub(r"^(EUR|€)\s*", "", raw, flags=re.I).strip()
    raw = re.sub(r"\s*(EUR|€)\s*$", "", raw, flags=re.I).strip()
    try:
        return _parse_money_token(raw)
    except (InvalidOperation, ValueError) as e:
        raise InvoicePdfError(f"Could not parse EUR amount from {raw!r}.") from e


def _parse_money_token(token: str) -> Decimal:
    last_comma = token.rfind(",")
    last_dot = token.rfind(".")
    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot:
            # e.g. 1.234,56
            normalized = token.replace(".", "").replace(",", ".")
        else:
            # e.g. 1,234.56
            normalized = token.replace(",", "")
        return Decimal(normalized)
    if last_comma != -1 and last_dot == -1:
        # e.g. 1234,56
        return Decimal(token.replace(",", "."))
    return Decimal(token)
