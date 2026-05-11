"""Parse EUR total from Jack's commission PDF (amount only; month/year come from email)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from googleads_invoice.invoice_pdf import _parse_money_token


class CommissionPdfError(ValueError):
    """Raised when the commission PDF cannot be parsed for EUR amount."""


def parse_commission_pdf_amount(source: str | Path | bytes) -> Decimal:
    """Return the EUR total — last ``€ …`` or ``EUR …`` amount (see plan §6).

    Matches left-to-right; the **last** match is the invoice total table row total.
    """
    if isinstance(source, (str, Path)):
        data = Path(source).expanduser().read_bytes()
    else:
        data = source
    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except PdfReadError as e:
        raise CommissionPdfError(f"Not a valid PDF or unreadable: {e}") from e

    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n".join(parts)

    combo = re.compile(
        r"€\s*([\d.,]+)|\bEUR\s+([\d.,]+)",
        re.IGNORECASE,
    )
    last_token: str | None = None
    for m in combo.finditer(text):
        last_token = m.group(1) or m.group(2)

    if last_token is None:
        due = re.search(
            r"Amount due:\s*(?:EUR\s+)?([\d.,]+)",
            text,
            re.IGNORECASE,
        )
        if due:
            last_token = due.group(1)

    if last_token is None:
        raise CommissionPdfError("Could not find a EUR total in commission PDF text.")
    try:
        return _parse_money_token(last_token)
    except (InvalidOperation, ValueError) as e:
        raise CommissionPdfError(
            f"Could not parse EUR amount token {last_token!r}: {e}"
        ) from e
