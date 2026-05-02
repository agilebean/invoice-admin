from pathlib import Path

import pytest

from googleads_invoice.pipeline import DryRunReport, run_dry_run


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
