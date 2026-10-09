"""Tests for invoice_admin.core.naming."""
from __future__ import annotations

from invoice_admin.core.naming import (
    _clean_name,
    amount_currency_slug,
    build_invoice_pdf_filename,
    build_invoice_pdf_filename_with_vendor_slug,
    slugify_vendor,
)


def test_slugify_vendor_ascii() -> None:
    assert slugify_vendor("Klempner Müller") == "klempner-mueller"


def test_clean_name_transliterates_german() -> None:
    assert _clean_name("Feuerstättenbescheid Straße") == "Feuerstaettenbescheid Strasse"


def test_build_invoice_pdf_filename_keeps_german_topic() -> None:
    name = build_invoice_pdf_filename(
        invoice_date="2026-09-25",
        vendor="Harry Koska",
        amount=167.95,
        currency="EUR",
        document_topic="Kaminkehrer Rechnungen und Feuerstättenbescheid",
    )
    assert "Feuerstaettenbescheid" in name


def test_slugify_vendor_empty_fallback() -> None:
    assert slugify_vendor("@@@") == "vendor"


def test_amount_currency_slug() -> None:
    assert amount_currency_slug(487.0, "eur") == "487EUR"
    assert amount_currency_slug(10.5, "USD") == "10.5USD"


def test_build_invoice_pdf_filename() -> None:
    name = build_invoice_pdf_filename(
        invoice_date="2026-05-12",
        vendor="ACME Co",
        amount=100.0,
        currency="EUR",
    )
    assert name.startswith("2026-05-12_")
    assert name.endswith("100EUR.pdf")


def test_build_invoice_pdf_filename_with_vendor_slug_matches_slugify() -> None:
    a = build_invoice_pdf_filename(
        invoice_date="2026-01-01",
        vendor="Acme Co",
        amount=10.0,
        currency="EUR",
    )
    b = build_invoice_pdf_filename_with_vendor_slug(
        invoice_date="2026-01-01",
        vendor_slug="acme-co",
        amount=10.0,
        currency="EUR",
    )
    assert a == b
