"""Orchestrate the full monthly flow: Gmail search → Brave PDF download → parse → SMTP send.

This is the "one command" caller for the month-end workflow. Each real I/O boundary
(Gmail API, Brave browser, SMTP) is injectable so tests stay fast and mockable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from googleads_invoice.billing_period import (
    billing_month_label_for_previous_calendar_month,
)
from googleads_invoice.billing_url import (
    BillingUrlNotFoundError,
    extract_billing_url,
)
from googleads_invoice.gmail_api_backend import GmailApiReadBackend
from googleads_invoice.gmail_facade import GmailTransportError
from googleads_invoice.gmail_smtp import SmtpGmailBackend
from googleads_invoice.invoice_artifacts import (
    InvoiceOutputFields,
    build_email_body,
    build_email_subject,
    build_renamed_pdf_filename,
)
from googleads_invoice.invoice_pdf import InvoicePdfError, parse_invoice_pdf
from googleads_invoice.live_brave_download import (
    LiveBraveDownloadError,
    live_brave_download_pdf,
)


class RunMonthError(RuntimeError):
    """A step in the monthly flow failed; the message describes what and where."""


@dataclass(frozen=True)
class RunMonthReport:
    """Everything produced (or discovered) during ``run_month``."""

    billing_url: str
    pdf_path: Path
    issue_date: date
    amount_eur: Decimal
    renamed_filename: str
    email_subject: str
    email_body: str
    recipient: str
    send_status: str
    steps: list[str] = field(default_factory=list)


def run_month(
    *,
    # Gmail read
    gmail_read_backend: GmailApiReadBackend,
    billing_query: str,
    max_scan: int = 5,
    # Brave download
    debugger_address: str,
    download_dir: Path,
    navigation_timeout_s: float = 45,
    download_timeout_s: float = 120,
    # SMTP send
    smtp_backend: SmtpGmailBackend,
    smtp_sender: str,
    to_address: str,
    # Month label (None = auto from previous calendar month)
    month_label: str | None = None,
) -> RunMonthReport:
    """Run the full monthly invoice flow: Gmail → Brave download → parse → SMTP send.

    Returns a :class:`RunMonthReport` with all fields populated. Raises
    :exc:`RunMonthError` if any step fails irrecoverably.
    """
    steps: list[str] = []

    # 1. Gmail search → billing URL
    label = month_label or billing_month_label_for_previous_calendar_month()
    steps.append("Searching Gmail for billing notification...")
    try:
        rows = gmail_read_backend.list_messages(
            billing_query, max_results=max_scan
        )
    except GmailTransportError as e:
        raise RunMonthError(f"Gmail search failed: {e}") from e
    if not rows:
        raise RunMonthError(
            f"No messages found for query {billing_query!r} "
            f"(tried {max_scan} max). Check the query or your OAuth token."
        )

    billing_url: str | None = None
    for r in rows:
        try:
            html = gmail_read_backend.get_message_html(r.id)
            billing_url = extract_billing_url(html)
            steps.append(f"Found billing URL in message {r.id}")
            break
        except (GmailTransportError, BillingUrlNotFoundError):
            continue

    if billing_url is None:
        raise RunMonthError(
            f"Scanned {len(rows)} billing messages but found no extractable "
            f"billing URL (expected a payments.google.com or pay.google.com link)."
        )

    # 2. Brave download → PDF
    steps.append("Launching Brave to download invoice PDF...")
    try:
        pdf_path = live_brave_download_pdf(
            debugger_address=debugger_address,
            deeplink_url=billing_url,
            download_dir=download_dir,
            navigation_timeout_s=navigation_timeout_s,
            download_timeout_s=download_timeout_s,
        )
    except LiveBraveDownloadError as e:
        raise RunMonthError(str(e)) from e
    steps.append(f"PDF downloaded: {pdf_path}")

    # 3. Parse PDF → date + EUR
    steps.append("Parsing invoice PDF...")
    try:
        issue_date, amount_eur = parse_invoice_pdf(pdf_path)
    except InvoicePdfError as e:
        raise RunMonthError(f"Failed to parse invoice PDF: {e}") from e
    steps.append(
        f"Invoice: {issue_date.isoformat()}, EUR {amount_eur}"
    )

    # 4. Build artifacts
    fields = InvoiceOutputFields(
        issue_date=issue_date,
        amount_eur=amount_eur,
        month_label=label,
    )
    renamed = build_renamed_pdf_filename(fields)
    subject = build_email_subject(fields)
    body = build_email_body(fields)
    steps.append(f"Artifacts built: filename={renamed}, subject={subject!r}")

    # 5. SMTP send
    steps.append(f"Sending email to {to_address}...")
    try:
        status = smtp_backend.send_text_with_pdf_attachment(
            sender=smtp_sender,
            to=to_address,
            subject=subject,
            body=body,
            pdf_path=pdf_path,
            attachment_name=renamed,
        )
    except GmailTransportError as e:
        raise RunMonthError(f"SMTP send failed: {e}") from e
    steps.append(f"Email sent (status: {status})")

    return RunMonthReport(
        billing_url=billing_url,
        pdf_path=pdf_path,
        issue_date=issue_date,
        amount_eur=amount_eur,
        renamed_filename=renamed,
        email_subject=subject,
        email_body=body,
        recipient=to_address,
        send_status=status,
        steps=steps,
    )
