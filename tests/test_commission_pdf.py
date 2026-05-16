"""Tests for Jack commission PDF amount parsing."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from invoice_admin.googleads.commission_pdf import CommissionPdfError, parse_commission_pdf_amount


def test_parse_commission_pdf_amount_fixture_matches_last_euro() -> None:
    pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    assert parse_commission_pdf_amount(pdf) == Decimal("1234.56")


def test_parse_commission_pdf_amount_rejects_non_pdf() -> None:
    with pytest.raises(CommissionPdfError, match="Not a valid PDF"):
        parse_commission_pdf_amount(b"not pdf")
