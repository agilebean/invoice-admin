"""Tests for invoice_admin.core.naming."""
from __future__ import annotations

from invoice_admin.core.naming import (
    amount_currency_slug,
    build_invoice_pdf_filename,
    build_invoice_pdf_filename_with_vendor_slug,
    slugify_vendor,
)


def test_slugify_vendor_ascii() -> None:
    assert slugify_vendor("Klempner Müller") == "klempner-muller"


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
