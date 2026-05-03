from datetime import date
from decimal import Decimal

from googleads_invoice.invoice_artifacts import (
    InvoiceOutputFields,
    build_email_body,
    build_email_subject,
    build_renamed_pdf_filename,
)


def test_build_renamed_pdf_filename_deterministic() -> None:
    fields = InvoiceOutputFields(
        issue_date=date(2026, 3, 15),
        amount_eur=Decimal("1234.56"),
        month_label="March 2026",
    )
    name = build_renamed_pdf_filename(fields)
    assert name == "google-ads-invoice_2026-03-15_1234.56-EUR.pdf"


def test_build_renamed_pdf_filename_whole_euros() -> None:
    fields = InvoiceOutputFields(
        issue_date=date(2026, 1, 5),
        amount_eur=Decimal("1000.00"),
        month_label="January 2026",
    )
    assert build_renamed_pdf_filename(fields) == "google-ads-invoice_2026-01-05_1000-EUR.pdf"


def test_build_email_subject_includes_month_and_amount() -> None:
    fields = InvoiceOutputFields(
        issue_date=date(2026, 4, 1),
        amount_eur=Decimal("99.50"),
        month_label="April 2026",
    )
    assert (
        build_email_subject(fields) == "Google Ads invoice — April 2026 (EUR 99.50)"
    )


def test_build_email_body_includes_jack_month_date_and_amount() -> None:
    fields = InvoiceOutputFields(
        issue_date=date(2026, 4, 1),
        amount_eur=Decimal("1234.56"),
        month_label="April 2026",
    )
    body = build_email_body(fields)
    assert "Jack" in body
    assert "April 2026" in body
    assert "Dear Jack" in body
