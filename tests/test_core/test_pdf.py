"""Tests for invoice_admin.core.pdf."""
from __future__ import annotations

from pathlib import Path

import pytest

from invoice_admin.core.errors import ExtractionError
from invoice_admin.core.pdf import extract_html_invoice_data, extract_pdf_data


def test_extract_pdf_data_success(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")

    class FakeLLM:
        def complete_with_pdf(self, prompt: str, pdf_bytes: bytes, **kwargs: object) -> str:
            assert b"%PDF" in pdf_bytes
            return (
                '{"vendor": "Klempner Müller", "invoice_date": "2026-01-02", '
                '"due_date": null, "amount": 120.5, "currency": "EUR", '
                '"iban": null, "bic": null, "verwendungszweck": "Ref 1"}'
            )

    data = extract_pdf_data(pdf, FakeLLM())
    assert data.vendor == "Klempner Müller"
    assert data.amount == 120.5
    assert data.currency == "EUR"


def test_extract_html_invoice_data_success() -> None:
    class FakeLLM:
        def complete(self, prompt: str, **kwargs: object) -> str:
            return (
                '{"vendor": "HTML Co", "invoice_date": "2026-06-06", '
                '"due_date": null, "amount": 3, "currency": "EUR", '
                '"iban": null, "bic": null, "verwendungszweck": null}'
            )

    out = extract_html_invoice_data("<html>bill</html>", FakeLLM())
    assert out.vendor == "HTML Co"
    assert out.amount == 3.0


def test_extract_pdf_data_invalid_json_raises(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class FakeLLM:
        def complete_with_pdf(self, *a: object, **k: object) -> str:
            return "not json"

    with pytest.raises(ExtractionError):
        extract_pdf_data(pdf, FakeLLM())
