"""CLI entrypoint for monthly Google Ads invoice workflow."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from invoice_admin.googleads.addresses import (
    DEFAULT_GMAIL_SENDER,
    DEFAULT_TEST_RECIPIENT,
    DEFAULT_PRODUCTION_RECIPIENT,
    DROPBOX_INVOICE_DIR,
)
from invoice_admin.googleads.billing_period import (
    billing_month_label_for_previous_calendar_month,
)
from invoice_admin.googleads.gmail_api_backend import (
    GmailApiReadBackend,
    billing_mail_query_from_env,
    commission_mail_query_from_env,
)
from invoice_admin.googleads.gmail_facade import GmailFacade
from invoice_admin.googleads.gmail_smtp import SmtpGmailBackend
from invoice_admin.googleads.invoice_artifacts import (
    InvoiceOutputFields,
    build_email_body,
    build_email_subject,
    build_renamed_pdf_filename,
)
from invoice_admin.googleads.invoice_pdf import parse_invoice_pdf
from invoice_admin.googleads.pipeline import DryRunReport
from invoice_admin.googleads.save_commission_pdf import SaveCommissionPdfError, save_commission_pdf

_ENV_MAIL_HTML = "GOOGLEADS_INVOICE_MAIL_HTML"
_ENV_INVOICE_PDF = "GOOGLEADS_INVOICE_PDF"
_ENV_SMTP_USER = "GOOGLEADS_GMAIL_SMTP_USER"
_ENV_SMTP_PW = "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD"
_ENV_SMTP_PW_FILE = "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE"
_ENV_CONFIRM_RUN_MONTH = "GOOGLEADS_CONFIRM_RUN_MONTH"
_ENV_INVOICE_TO = "GOOGLEADS_INVOICE_TO"


def _resolve_recipient(to_flag: str | None) -> str:
    """CLI ``--to`` wins, then ``GOOGLEADS_INVOICE_TO``, else production default."""
    if to_flag and str(to_flag).strip():
        return str(to_flag).strip()
    env = os.environ.get(_ENV_INVOICE_TO, "").strip()
    return env if env else DEFAULT_TEST_RECIPIENT


def _smtp_login_user() -> str:
    """SMTP login / From: ``GOOGLEADS_GMAIL_SMTP_USER`` or project Gmail default."""
    return os.environ.get(_ENV_SMTP_USER, "").strip() or DEFAULT_GMAIL_SENDER


def _smtp_app_password_from_env() -> str:
    """Return Gmail app password from env, or first line of *password file* (more secure than export)."""
    raw_path = os.environ.get(_ENV_SMTP_PW_FILE, "").strip()
    if raw_path:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise ValueError(
                f"{_ENV_SMTP_PW_FILE} is not a file: {path} "
                f"(use chmod 600; never commit this file)."
            )
        raw = path.read_text(encoding="utf-8")
        lines = raw.strip().splitlines()
        if not lines:
            raise ValueError(f"{_ENV_SMTP_PW_FILE} is empty: {path}")
        line = lines[0].strip()
        if not line:
            raise ValueError(f"{_ENV_SMTP_PW_FILE} is empty: {path}")
        return line
    return os.environ.get(_ENV_SMTP_PW, "").strip()




def main(argv: list[str] | None = None) -> int:
    if os.environ.get("_GOOGLEADS_INVOICE_VIA_S6") != "1":
        print(
            "googleads-invoice: this entrypoint is deprecated; use 'invoice googleads ...' instead.",
            file=sys.stderr,
        )
    parser = argparse.ArgumentParser(prog="googleads-invoice")
    sub = parser.add_subparsers(dest="command", required=True)

    send_p = sub.add_parser(
        "send",
        help=(
            "Send monthly invoice via Gmail SMTP. "
            "Full monthly flow (Gmail search → Brave download → PDF parse → SMTP send). "
            f"Production send requires {_ENV_CONFIRM_RUN_MONTH}=1, Gmail OAuth token, Brave with "
            "--remote-debugging-port, and SMTP app password."
        ),
    )
    send_p.add_argument(
        "--query",
        default=None,
        help="Gmail search q= string (default: GOOGLEADS_GMAIL_BILLING_QUERY or built-in).",
    )
    send_p.add_argument(
        "--max-scan",
        type=int,
        default=5,
        help="Max Gmail messages to scan for billing URL (default: 5).",
    )
    send_p.add_argument(
        "--debugger-address",
        default=None,
        help=(
            "Brave debugger address, e.g. 127.0.0.1:9222 "
            "(default: GOOGLEADS_BROWSER_DEBUGGER_ADDRESS env)."
        ),
    )
    send_p.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help=(
            "Directory for Brave PDF downloads "
            "(default: GOOGLEADS_LIVE_BRAVE_TRACE_DIR env, or ~/Downloads)."
        ),
    )
    send_p.add_argument(
        "--to",
        default=None,
        help=(
            f"Recipient email override (default: {DEFAULT_PRODUCTION_RECIPIENT})."
        ),
    )
    send_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Download and parse invoice PDF, print fields, skip SMTP send and confirmation.",
    )
    send_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip interactive confirmation prompt (for scheduled/automated runs).",
    )

    save_p = sub.add_parser(
        "save",
        help=(
            "Search Gmail for commission emails from Jack Copeland, download the PDF attachment, "
            "parse it, and save to the commissions directory (same as monthly invoice Dropbox folder)."
        ),
    )
    save_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Test mode: skip confirmation prompt; save renamed PDF under ~/Downloads (not commissions)."
        ),
    )

    args = parser.parse_args(argv)
    if args.command == "send":
        if not args.dry_run and not args.yes:
            if os.environ.get(_ENV_CONFIRM_RUN_MONTH, "") != "1":
                print(
                    f"Refusing: set {_ENV_CONFIRM_RUN_MONTH}=1 after confirming all "
                    "secrets, Brave, and recipient are correct.",
                    file=sys.stderr,
                )
                return 2

        query = (args.query or "").strip() or billing_mail_query_from_env()
        max_scan = int(args.max_scan)

        addr = (args.debugger_address or "").strip() or os.environ.get(
            "GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", ""
        ).strip()
        if not addr:
            print(
                "Provide --debugger-address or set GOOGLEADS_BROWSER_DEBUGGER_ADDRESS.",
                file=sys.stderr,
            )
            return 2

        dl_dir_raw = args.download_dir
        if dl_dir_raw is None:
            dl_env = os.environ.get("GOOGLEADS_LIVE_BRAVE_TRACE_DIR", "").strip()
            download_dir = Path(dl_env).expanduser() if dl_env else Path.home() / "Downloads"
        else:
            download_dir = dl_dir_raw.expanduser()

        is_dry = args.dry_run

        smtp_user = _smtp_login_user()
        try:
            smtp_pw = _smtp_app_password_from_env()
        except ValueError as e:
            if not is_dry:
                print(str(e), file=sys.stderr)
                return 2
            smtp_pw = "dry-run"
        if not smtp_pw:
            if not is_dry:
                print(
                    f"Set {_ENV_SMTP_PW} or {_ENV_SMTP_PW_FILE} "
                    "(Gmail app password; prefer file with chmod 600).",
                    file=sys.stderr,
                )
                return 2
            smtp_pw = "dry-run"

        to_addr = DEFAULT_PRODUCTION_RECIPIENT

        try:
            gmail_backend = GmailApiReadBackend.from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2

        smtp_backend = SmtpGmailBackend(user=smtp_user, app_password=smtp_pw)

        month_str = billing_month_label_for_previous_calendar_month()
        if is_dry:
            print(f"DRY RUN — {month_str} invoice (no send):", file=sys.stderr)
        elif args.yes:
            pass
        else:
            from invoice_admin.googleads.addresses import CC_RECIPIENTS
            print(f"About to send {month_str} invoice:", file=sys.stderr)
            print(f"  To: {to_addr}", file=sys.stderr)
            print(f"  CC: {', '.join(CC_RECIPIENTS)}", file=sys.stderr)
            from invoice_admin.googleads.addresses import BCC_RECIPIENTS
            print(f"  BCC: {', '.join(BCC_RECIPIENTS)}", file=sys.stderr)
            try:
                confirm = input("  Confirm? (Y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("", "y", "yes"):
                print("Aborted.", file=sys.stderr)
                return 2

        try:
            from invoice_admin.googleads.run_month import RunMonthError, run_month

            report = run_month(
                gmail_read_backend=gmail_backend,
                billing_query=query,
                max_scan=max_scan,
                debugger_address=addr,
                download_dir=download_dir,
                smtp_backend=smtp_backend,
                smtp_sender=smtp_user if not is_dry else "dry-run@example.com",
                to_address=to_addr if not is_dry else "dry-run@example.com",
                dry_run=is_dry,
                client_prefix="Glugglejug",
            )
        except RunMonthError as e:
            print(str(e), file=sys.stderr)
            return 2

        if is_dry:
            print(f"  Billing URL: {report.billing_url}", file=sys.stderr)
            print(f"  Invoice: {report.issue_date}, EUR {report.amount_eur}", file=sys.stderr)
            print(f"  Filename: {report.renamed_filename}", file=sys.stderr)
            print("Dry run complete (no email sent).", file=sys.stderr)
            return 0

        print("Invoice sent successfully.", file=sys.stderr)
        print(f"  Billing URL: {report.billing_url}", file=sys.stderr)
        if report.dropbox_path:
            print(f"  PDF moved to: {report.dropbox_path}", file=sys.stderr)
        else:
            print(f"  PDF saved: {report.pdf_path}", file=sys.stderr)
        print(f"  Invoice: {report.issue_date}, EUR {report.amount_eur}", file=sys.stderr)
        print(f"  Sent to: {report.recipient}", file=sys.stderr)
        print(f"  Subject: {report.email_subject!r}", file=sys.stderr)
        print(f"  Attachment: {report.renamed_filename}", file=sys.stderr)
        return 0

    if args.command == "save":
        query = commission_mail_query_from_env()

        try:
            backend = GmailApiReadBackend.from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2

        if not args.dry_run:
            print(
                "About to save commission PDF:",
                file=sys.stderr,
            )
            print(f"  Query: {query}", file=sys.stderr)
            print(f"  Destination: {DROPBOX_INVOICE_DIR}", file=sys.stderr)
            try:
                confirm = input("  Confirm? (Y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm not in ("", "y", "yes"):
                print("Aborted.", file=sys.stderr)
                return 2

        try:
            report = save_commission_pdf(
                gmail_read_backend=backend,
                commission_query=query,
                dry_run=args.dry_run,
            )
        except SaveCommissionPdfError as e:
            print(str(e), file=sys.stderr)
            return 2

        print("Commission PDF saved successfully.", file=sys.stderr)
        print(f"  Email: {report.message_id}", file=sys.stderr)
        print(f"  PDF: {report.pdf_path}", file=sys.stderr)
        print(f"  Date: {report.commission_date}, EUR {report.amount_eur}", file=sys.stderr)
        print(f"  Renamed: {report.renamed_filename}", file=sys.stderr)
        return 0

    return 2
