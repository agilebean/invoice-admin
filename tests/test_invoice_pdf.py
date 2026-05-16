from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_admin.googleads.invoice_pdf import InvoicePdfError, parse_invoice_pdf

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pdf"


def test_parse_invoice_pdf_path_dot_decimal_eur() -> None:
    path = _FIXTURES / "invoice_eur_dot_decimal.pdf"
    issue_date, amount = parse_invoice_pdf(path)
    assert issue_date == date(2026, 3, 15)
    assert amount == Decimal("1234.56")


def test_parse_invoice_pdf_bytes_comma_decimal_eur() -> None:
    path = _FIXTURES / "invoice_eur_comma_decimal.pdf"
    raw = path.read_bytes()
    issue_date, amount = parse_invoice_pdf(raw)
    assert issue_date == date(2026, 4, 1)
    assert amount == Decimal("1234.56")


def test_parse_invoice_pdf_non_pdf_raises() -> None:
    path = _FIXTURES / "not_a_pdf.txt"
    with pytest.raises(InvoicePdfError) as excinfo:
        parse_invoice_pdf(path)
    assert "pdf" in str(excinfo.value).lower()
