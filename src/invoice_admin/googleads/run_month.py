"""Orchestrate the full monthly flow: Gmail search → Brave PDF download → parse → SMTP send.

This is the "one command" caller for the month-end workflow. Each real I/O boundary
(Gmail API, Brave browser, SMTP) is injectable so tests stay fast and mockable.
"""

from __future__ import annotations

import re
import sys
import time
from calendar import month_name
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_admin.googleads.billing_period import (
    billing_month_label_for_previous_calendar_month,
)
from invoice_admin.googleads.billing_url import (
    BillingUrlNotFoundError,
    extract_billing_url,
)
from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
from invoice_admin.googleads.gmail_facade import GmailTransportError
from invoice_admin.googleads.gmail_smtp import SmtpGmailBackend
from invoice_admin.googleads.invoice_artifacts import (
    InvoiceOutputFields,
    build_email_body,
    build_email_subject,
    build_renamed_pdf_filename,
)
from invoice_admin.googleads.invoice_pdf import InvoicePdfError, parse_invoice_pdf
from invoice_admin.googleads.addresses import (
    CC_RECIPIENTS,
    BCC_RECIPIENTS,
    GOOGLE_DRIVE_INVOICE_DIR,
)


class RunMonthError(RuntimeError):
    """A step in the monthly flow failed; the message describes what and where."""


# Saved invoice filenames embed this marker (see live_brave_download._build_download_filename).
_SAVED_INVOICE_MARKER = "GoogleAds Invoice"

_MONTH_NUMBERS = {name: i for i, name in enumerate(month_name) if name}


def _billing_label_parts(label: str) -> tuple[str, int, int] | None:
    """(month name, year, month number) from ``"March 2026"`` or ``"2026-03"``; else None."""
    parts = label.split()
    if len(parts) == 2 and parts[0] in _MONTH_NUMBERS:
        try:
            year = int(parts[1])
        except ValueError:
            return None
        return parts[0], year, _MONTH_NUMBERS[parts[0]]
    m = re.fullmatch(r"(\d{4})-(\d{2})", label)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return month_name[month], year, month
    return None


def _issue_date_in_billing_window(issue_date: date, year: int, month: int) -> bool:
    """True when the issue date falls in the billing month or the month after it.

    Google issues the monthly invoice at month end or in the first days after it.
    The window rejects a same-named file from an earlier year.
    """
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 2, 1)
    elif month == 11:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 2, 1)
    return start <= issue_date < end


def find_downloaded_invoice(
    directory: Path,
    *,
    client_prefix: str,
    month_label: str,
) -> tuple[Path, date, Decimal] | None:
    """Find a previously downloaded invoice for ``month_label`` in ``directory``.

    The saved filename carries the client prefix and the billing month name; the
    PDF itself carries the issue date. A candidate counts only when both match
    the requested billing month, so an older month's or another client's file is
    never reused. Returns ``(path, issue_date, amount_eur)``, or None.
    """
    parts = _billing_label_parts(month_label)
    if parts is None or not directory.is_dir():
        return None
    month_name_str, year, month = parts
    prefix = f"{client_prefix} " if client_prefix else ""
    pattern = f"*{prefix}{_SAVED_INVOICE_MARKER} {month_name_str}*.pdf"
    candidates = sorted(
        directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for candidate in candidates:
        try:
            issue_date, amount = parse_invoice_pdf(candidate)
        except (InvoicePdfError, OSError):
            continue
        if _issue_date_in_billing_window(issue_date, year, month):
            return candidate, issue_date, amount
    return None


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
    dropbox_path: Path | None = None
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
    dry_run: bool = False,
    # Month label (None = auto from previous calendar month)
    month_label: str | None = None,
    # Destination folder (None = use default from addresses.py)
    dropbox_dir: Path | None = None,
    # Client prefix for filename
    client_prefix: str = "",
    # Reuse a previously downloaded invoice for this month when one is saved
    reuse_downloaded: bool = False,
) -> RunMonthReport:
    """Run the full monthly invoice flow: Gmail → Brave download → parse → SMTP send."""
    _t0 = time.monotonic()
    _last_t = [_t0]
    _STEP = 7

    def _step(n: int, msg: str) -> None:
        now = time.monotonic()
        step_dur = now - _last_t[0]
        total = now - _t0
        _last_t[0] = now
        print(f"  [{n}/{_STEP}] +{step_dur:.1f}s/{total:.1f}s {msg}", flush=True, file=sys.stderr)

    steps: list[str] = []

    label = month_label or billing_month_label_for_previous_calendar_month()
    destination_dir = (
        dropbox_dir if dropbox_dir is not None else Path(GOOGLE_DRIVE_INVOICE_DIR)
    ).expanduser()

    # 0. Reuse a saved invoice from a previous download, when asked and found.
    reused: tuple[Path, date, Decimal] | None = None
    if reuse_downloaded:
        reused = find_downloaded_invoice(
            destination_dir, client_prefix=client_prefix, month_label=label
        )
        if reused is not None:
            _step(1, f"Using already-downloaded invoice {reused[0].name}...")
            steps.append(f"Reused downloaded invoice: {reused[0]}")
        else:
            print(
                f"  No downloaded invoice for {label} in {destination_dir}; "
                f"downloading fresh.",
                flush=True,
                file=sys.stderr,
            )

    if reused is None:
        # 1. Gmail search → billing URL
        _step(1, "Searching Gmail for billing notification...")
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

        _step(2, "Extracting billing URL from Gmail...")
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
                f"billing URL."
            )

        # 2. Brave download → PDF
        from invoice_admin.googleads.browser_download import ensure_brave_running
        from invoice_admin.googleads.live_brave_download import (
            LiveBraveDownloadError,
            live_brave_download_pdf,
        )

        _step(3, "Launching Brave to download invoice PDF...")
        ensure_brave_running(debugger_address, launch_timeout_s=11.0)
        try:
            pdf_path = live_brave_download_pdf(
                debugger_address=debugger_address,
                deeplink_url=billing_url,
                download_dir=download_dir,
                navigation_timeout_s=navigation_timeout_s,
                download_timeout_s=download_timeout_s,
                verbose=True,
                client_prefix=client_prefix,
            )
        except LiveBraveDownloadError as e:
            raise RunMonthError(str(e)) from e
        steps.append(f"PDF downloaded: {pdf_path}")
    else:
        billing_url = ""
        pdf_path = reused[0]

    # 3. Parse PDF → date + EUR
    if reused is None:
        _step(4, "Parsing invoice PDF...")
        try:
            issue_date, amount_eur = parse_invoice_pdf(pdf_path)
        except InvoicePdfError as e:
            raise RunMonthError(f"Failed to parse invoice PDF: {e}") from e
    else:
        issue_date, amount_eur = reused[1], reused[2]
    steps.append(f"Invoice: {issue_date.isoformat()}, EUR {amount_eur}")

    # 4. Build artifacts
    _step(5, "Building email artifacts...")
    fields = InvoiceOutputFields(
        issue_date=issue_date,
        amount_eur=amount_eur,
        month_label=label,
        client_prefix=client_prefix,
    )
    # Use the actual saved filename as the attachment name
    attach_name = pdf_path.name
    subject = build_email_subject(fields)
    body = build_email_body(fields)
    steps.append(f"Artifacts built: attachment={attach_name}")

    # 5. SMTP send
    if dry_run:
        _step(6, "Dry run — skipping email send.")
        steps.append("Email: skipped (dry-run)")
        status = "dry-run: skipped"
    else:
        cc_list = CC_RECIPIENTS
        bcc_list = BCC_RECIPIENTS
        _step(6, f"Sending email to {to_address}...")
        try:
            status = smtp_backend.send_text_with_pdf_attachment(
                sender=smtp_sender,
                to=to_address,
                cc=cc_list,
                bcc=bcc_list,
                subject=subject,
                body=body,
                pdf_path=pdf_path,
                attachment_name=attach_name,
            )
        except GmailTransportError as e:
            raise RunMonthError(f"SMTP send failed: {e}") from e
        steps.append(f"Email sent (status: {status})")

    if reused is not None:
        dest = pdf_path
        steps.append(f"Already in destination: {dest}")
    else:
        _step(7, "Moving file to destination...")
        destination_dir.mkdir(parents=True, exist_ok=True)
        dest = destination_dir / pdf_path.name
        if dest.is_file():
            stem = dest.stem
            ext = dest.suffix
            for i in range(1, 100):
                alt = destination_dir / f"{stem} ({i}){ext}"
                if not alt.is_file():
                    dest = alt
                    break
        import shutil
        shutil.move(str(pdf_path), str(dest))
        if not dest.is_file():
            raise RunMonthError(f"File move failed: {pdf_path} -> {dest}")
        steps.append(f"Moved to: {dest}")

    _tot = time.monotonic() - _t0
    print(f"  Done ({_tot:.1f}s total)", flush=True)

    return RunMonthReport(
        billing_url=billing_url,
        pdf_path=pdf_path,
        dropbox_path=dest,
        issue_date=issue_date,
        amount_eur=amount_eur,
        renamed_filename=attach_name,
        email_subject=subject,
        email_body=body,
        recipient=to_address,
        send_status=status,
        steps=steps,
    )
