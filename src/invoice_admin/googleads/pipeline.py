"""Orchestrate mail → URL → invoice PDF → rename/email artifacts (no Gmail in dry-run)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_admin.googleads.billing_url import extract_billing_url
from invoice_admin.googleads.addresses import (
    DEFAULT_GMAIL_SENDER,
    PRODUCTION_RECIPIENT_JACK,
)
from invoice_admin.googleads.invoice_artifacts import (
    InvoiceOutputFields,
    build_email_body,
    build_email_subject,
    build_renamed_pdf_filename,
)
from invoice_admin.googleads.invoice_pdf import parse_invoice_pdf


@dataclass(frozen=True)
class DryRunReport:
    billing_url: str
    issue_date: date
    amount_eur: Decimal
    renamed_filename: str
    email_subject: str
    email_body: str


def run_dry_run(
    *,
    mail_html_path: Path,
    invoice_pdf_path: Path,
    month_label: str,
) -> DryRunReport:
    """End-to-end pure steps on fixture or saved paths: HTML → URL; PDF → date/€; build mail artifacts."""
    html = mail_html_path.read_text(encoding="utf-8")
    billing_url = extract_billing_url(html)
    issue_date, amount_eur = parse_invoice_pdf(invoice_pdf_path)
    fields = InvoiceOutputFields(
        issue_date=issue_date,
        amount_eur=amount_eur,
        month_label=month_label,
    )
    return DryRunReport(
        billing_url=billing_url,
        issue_date=issue_date,
        amount_eur=amount_eur,
        renamed_filename=build_renamed_pdf_filename(fields),
        email_subject=build_email_subject(fields),
        email_body=build_email_body(fields),
    )


def format_dry_run_report(report: DryRunReport) -> str:
    """Human-readable block for stdout / logs."""
    lines = [
        "Dry run (no Gmail send, no browser)",
        f"  From: {DEFAULT_GMAIL_SENDER}",
        f"  To (monthly recipient): {PRODUCTION_RECIPIENT_JACK}",
        f"  Billing URL: {report.billing_url}",
        f"  Invoice date: {report.issue_date.isoformat()}",
        f"  Amount (EUR): {report.amount_eur}",
        f"  Renamed PDF file: {report.renamed_filename}",
        f"  Email subject: {report.email_subject}",
        "  Email body:",
        "\n".join(f"    {line}" for line in report.email_body.rstrip("\n").split("\n")),
        "  Gmail send skipped (dry-run).",
    ]
    return "\n".join(lines) + "\n"
