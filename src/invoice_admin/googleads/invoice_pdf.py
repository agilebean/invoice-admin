"""Parse invoice issue date and EUR total from PDF bytes or paths.

Supports both synthetic test PDFs and real Google Ads invoice PDFs.
"""

from __future__ import annotations

import re
from datetime import date, datetime
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
    # Format 1: synthetic test PDF — "Invoice date: 2026-03-15"
    match = re.search(r"Invoice date:\s*(\d{4}-\d{2}-\d{2})", text)
    if match:
        return date.fromisoformat(match.group(1))

    # Format 2: real Google Ads invoice — "Apr 30, 2026" or "April 30, 2026"
    # The date appears after "Invoice date" column header or near the top
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{1,2}),\s+(\d{4})",
        text,
        re.MULTILINE,
    )
    if match:
        month_str = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3))
        # Handle both abbreviated and full month names
        try:
            dt = datetime.strptime(f"{month_str} {day} {year}", "%b %d %Y")
        except ValueError:
            dt = datetime.strptime(f"{month_str} {day} {year}", "%B %d %Y")
        return dt.date()

    # Format 3: any date-like pattern as last resort
    match = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})", text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        year = int(match.group(3))
        dt = datetime.strptime(f"{month_str} {day} {year}", "%b %d %Y")
        return dt.date()

    # Format 4: commission PDF — "Invoice April Commission (EUR)" / "Invoice January Commission (EUR)"
    match = re.search(
        r"Invoice\s+(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+Commission",
        text,
    )
    if match:
        month_str = match.group(1)
        # Commission month is derived from the billing month label; use today as fallback
        return date(date.today().year, datetime.strptime(month_str, "%B").month, 1)

    raise InvoicePdfError(
        "Could not parse invoice date from PDF text. "
        "Expected either 'Invoice date: YYYY-MM-DD' (synthetic) or "
        "'Mon DD, YYYY' (real Google Ads invoice). "
        f"Text extracted: {text[:300]!r}"
    )


def _extract_amount_due_eur(text: str) -> Decimal:
    # Format 1: synthetic test PDF — "Amount due: <amount>"
    match = re.search(r"Amount due:\s*(.+)", text)
    if match:
        raw = match.group(1).strip()
        raw = re.sub(r"^(EUR|€)\s*", "", raw, flags=re.I).strip()
        raw = re.sub(r"\s*(EUR|€)\s*$", "", raw, flags=re.I).strip()
        try:
            return _parse_money_token(raw)
        except (InvalidOperation, ValueError):
            pass  # Fall through to Format 2

    # Format 2: real Google Ads invoice — "€6,496.76" followed by "Total in EUR"
    lines = text.split("\n")
    total_amount: Decimal | None = None
    for i, line in enumerate(lines):
        if "Total in EUR" in line:
            # Search backward for the nearest "€" amount before this line
            for j in range(i - 1, max(0, i - 10), -1):
                euro_match = re.search(r"€\s*([\d.,]+)", lines[j])
                if euro_match:
                    total_amount = _parse_money_token(euro_match.group(1))
                    break
            break

    if total_amount is not None:
        return total_amount

    # Format 3: any "€" amount in the text (last resort)
    all_euro = re.findall(r"€\s*([\d.,]+)", text)
    if all_euro:
        # Take the last € amount (usually the total)
        return _parse_money_token(all_euro[-1])

    raise InvoicePdfError(
        "Could not find EUR total in PDF text. "
        "Expected 'Amount due:' or '€' with 'Total in EUR' or a plain '€' amount."
    )


def _parse_money_token(token: str) -> Decimal:
    """Parse a monetary value string like '1,234.56' or '1.234,56' or '1234.56'."""
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
