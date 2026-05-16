from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_admin.googleads.addresses import DEFAULT_GMAIL_SENDER, PRODUCTION_RECIPIENT_JACK
from invoice_admin.googleads.pipeline import DryRunReport, format_dry_run_report, run_dry_run


def test_format_dry_run_report_includes_mailbox_line() -> None:
    r = DryRunReport(
        billing_url="https://pay.example/p",
        issue_date=date(2026, 3, 15),
        amount_eur=Decimal("1"),
        renamed_filename="f.pdf",
        email_subject="subj",
        email_body="Hi\n",
    )
    s = format_dry_run_report(r)
    assert DEFAULT_GMAIL_SENDER in s
    assert PRODUCTION_RECIPIENT_JACK in s


def test_run_dry_run_composes_billing_parse_and_artifacts() -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    report = run_dry_run(
        mail_html_path=mail,
        invoice_pdf_path=pdf,
        month_label="March 2026",
    )
    assert isinstance(report, DryRunReport)
    assert "payments.google.com" in report.billing_url
    assert report.issue_date.isoformat() == "2026-03-15"
    assert str(report.amount_eur) == "1234.56"
    assert report.renamed_filename == "google-ads-invoice_2026-03-15_1234.56-EUR.pdf"
    assert "March 2026" in report.email_subject
    assert "Jack" in report.email_body
