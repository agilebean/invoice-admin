"""CLI entrypoint for monthly Google Ads invoice workflow."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from googleads_invoice.addresses import (
    DEFAULT_GMAIL_SENDER,
    DEFAULT_TEST_RECIPIENT,
)
from googleads_invoice.billing_period import (
    billing_month_label_for_previous_calendar_month,
)
from googleads_invoice.billing_url import (
    BillingUrlNotFoundError,
    extract_billing_url,
)
from googleads_invoice.gmail_api_backend import (
    GmailApiReadBackend,
    billing_mail_query_from_env,
)
from googleads_invoice.gmail_facade import GmailFacade, GmailTransportError
from googleads_invoice.gmail_smtp import SmtpGmailBackend
from googleads_invoice.invoice_artifacts import (
    InvoiceOutputFields,
    build_email_body,
    build_email_subject,
    build_renamed_pdf_filename,
)
from googleads_invoice.invoice_pdf import parse_invoice_pdf
from googleads_invoice.live_brave_download import LiveBraveDownloadError, live_brave_download_pdf
from googleads_invoice.mail_app_draft import MailAppDraftError, open_mail_app_draft
from googleads_invoice.pipeline import format_dry_run_report, run_dry_run
from googleads_invoice.run_month import RunMonthError, run_month

_ENV_MAIL_HTML = "GOOGLEADS_INVOICE_MAIL_HTML"
_ENV_INVOICE_PDF = "GOOGLEADS_INVOICE_PDF"
_ENV_SMTP_USER = "GOOGLEADS_GMAIL_SMTP_USER"
_ENV_SMTP_PW = "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD"
_ENV_SMTP_PW_FILE = "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE"
_ENV_CONFIRM_SEND = "GOOGLEADS_CONFIRM_TEST_SEND"
_ENV_CONFIRM_MAIL_DRAFT = "GOOGLEADS_CONFIRM_MAIL_APP_DRAFT"
_ENV_CONFIRM_LIVE_BRAVE = "GOOGLEADS_CONFIRM_LIVE_BRAVE"
_ENV_CONFIRM_RUN_MONTH = "GOOGLEADS_CONFIRM_RUN_MONTH"
_ENV_INVOICE_TO = "GOOGLEADS_INVOICE_TO"


def _resolve_recipient(to_flag: str | None) -> str:
    """CLI ``--to`` wins, then ``GOOGLEADS_INVOICE_TO``, else test inbox default."""
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


def _path_from_flag_or_env(
    subparser: argparse.ArgumentParser,
    flag_value: Path | None,
    env_key: str,
    flag_name: str,
) -> Path:
    if flag_value is not None:
        return flag_value.expanduser()
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        subparser.error(
            f"dry-run needs {flag_name} or {env_key} "
            "(e.g. HTML exported from Spark, PDF saved from Brave)."
        )
    return Path(raw).expanduser()


def _subject_body_attachment_for_pdf(
    pdf_path: Path,
    *,
    attachment_name: str | None,
) -> tuple[str, str, str, Path]:
    """Shared subject/body/attachment name for ``send-test-pdf`` and ``mail-app-draft``."""
    pdf_path = pdf_path.expanduser()
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))
    month_label = billing_month_label_for_previous_calendar_month()
    issue_date, amount_eur = parse_invoice_pdf(pdf_path)
    fields = InvoiceOutputFields(
        issue_date=issue_date,
        amount_eur=amount_eur,
        month_label=month_label,
    )
    subject = build_email_subject(fields)
    body = build_email_body(fields)
    attach_name = attachment_name or build_renamed_pdf_filename(fields)
    return subject, body, attach_name, pdf_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="googleads-invoice")
    sub = parser.add_subparsers(dest="command", required=True)

    dry = sub.add_parser(
        "dry-run",
        help="Print billing URL, parsed PDF fields, and Jack email artifacts (no send).",
    )
    dry.add_argument(
        "--mail-html",
        type=Path,
        default=None,
        help=f"Path to saved Gmail-style HTML, or set {_ENV_MAIL_HTML}.",
    )
    dry.add_argument(
        "--invoice-pdf",
        type=Path,
        default=None,
        help=f"Path to invoice PDF, or set {_ENV_INVOICE_PDF}.",
    )

    send_p = sub.add_parser(
        "send-test-pdf",
        help=(
            "Send one email with the example (or chosen) invoice PDF attached via Gmail SMTP. "
            f"Requires {_ENV_CONFIRM_SEND}=1, and either {_ENV_SMTP_PW} or {_ENV_SMTP_PW_FILE} "
            f"(first line = secret; chmod 600). Sender defaults to {DEFAULT_GMAIL_SENDER} if "
            f"{_ENV_SMTP_USER} is unset."
        ),
    )
    send_p.add_argument(
        "--to",
        default=None,
        help=(
            f"Recipient (default: {_ENV_INVOICE_TO} env or {DEFAULT_TEST_RECIPIENT}; "
            "set env to jack.copeland@theglugglejugfactory.com for the monthly Jack send)."
        ),
    )
    send_p.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="Invoice PDF path (default: tests/fixtures/pdf/invoice_eur_dot_decimal.pdf from cwd).",
    )
    send_p.add_argument(
        "--attachment-name",
        default=None,
        help="Optional attachment filename (default: build_renamed_pdf_filename from PDF + billing month).",
    )

    mail_draft_p = sub.add_parser(
        "mail-app-draft",
        help=(
            "Open Mail.app with a new outgoing message (Step 2): same subject/body/PDF as send-test-pdf. "
            f"macOS only. Requires {_ENV_CONFIRM_MAIL_DRAFT}=1."
        ),
    )
    mail_draft_p.add_argument(
        "--to",
        default=None,
        help=(
            f"Recipient (default: {_ENV_INVOICE_TO} env or {DEFAULT_TEST_RECIPIENT})."
        ),
    )
    mail_draft_p.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="Invoice PDF path (default: tests/fixtures/pdf/invoice_eur_dot_decimal.pdf from cwd).",
    )
    mail_draft_p.add_argument(
        "--attachment-name",
        default=None,
        help="Optional attachment filename (default: build_renamed_pdf_filename from PDF + billing month).",
    )

    list_p = sub.add_parser(
        "list-billing-mail",
        help=(
            "Search Gmail for billing notifications via Gmail API (OAuth token file). "
            "Does not send mail — use send-test-pdf for SMTP."
        ),
    )
    list_p.add_argument(
        "--query",
        default=None,
        help=(
            "Gmail search q= string (default: GOOGLEADS_GMAIL_BILLING_QUERY or built-in billing query)."
        ),
    )
    list_p.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Max messages to list (default: 10).",
    )

    lb = sub.add_parser(
        "live-brave-download",
        help=(
            "Attach to Brave (--remote-debugging-port), navigate billing deeplink, "
            "click Download on the top row, save the PDF to disk. "
            f"Requires {_ENV_CONFIRM_LIVE_BRAVE}=1."
        ),
    )
    lb.add_argument(
        "--debugger-address",
        default=None,
        help=(
            "Brave debugger address, e.g. 127.0.0.1:9222 "
            "(default: GOOGLEADS_BROWSER_DEBUGGER_ADDRESS env)."
        ),
    )
    lb.add_argument(
        "--deeplink",
        default=None,
        help=(
            "Billing deeplink URL (c.gle short link); "
            "default: GOOGLEADS_BILLING_DEEPLINK env."
        ),
    )
    lb.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help=(
            "Directory to save the downloaded PDF into "
            "(default: GOOGLEADS_LIVE_BRAVE_TRACE_DIR env, or ~/Downloads)."
        ),
    )

    run_p = sub.add_parser(
        "run-month",
        help=(
            "Full monthly flow: Gmail search → Brave download → PDF parse → SMTP send. "
            f"Requires {_ENV_CONFIRM_RUN_MONTH}=1, Gmail OAuth token, Brave with "
            "--remote-debugging-port, and SMTP app password."
        ),
    )
    run_p.add_argument(
        "--query",
        default=None,
        help=(
            "Gmail search q= string (default: GOOGLEADS_GMAIL_BILLING_QUERY or built-in)."
        ),
    )
    run_p.add_argument(
        "--max-scan",
        type=int,
        default=5,
        help="Max Gmail messages to scan for billing URL (default: 5).",
    )
    run_p.add_argument(
        "--debugger-address",
        default=None,
        help=(
            "Brave debugger address, e.g. 127.0.0.1:9222 "
            "(default: GOOGLEADS_BROWSER_DEBUGGER_ADDRESS env)."
        ),
    )
    run_p.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help=(
            "Directory for Brave PDF downloads "
            "(default: GOOGLEADS_LIVE_BRAVE_TRACE_DIR env, or ~/Downloads)."
        ),
    )
    run_p.add_argument(
        "--to",
        default=None,
        help=(
            f"Recipient (default: {_ENV_INVOICE_TO} env or {DEFAULT_TEST_RECIPIENT}; "
            "set env to jack.copeland@theglugglejugfactory.com for Jack)."
        ),
    )

    url_p = sub.add_parser(
        "billing-url-from-gmail",
        help=(
            "Search Gmail (same query as list-billing-mail), fetch HTML for each hit until a "
            "billing payments URL is found (Step 3 → dry-run input)."
        ),
    )
    url_p.add_argument(
        "--query",
        default=None,
        help="Gmail search q= (default: GOOGLEADS_GMAIL_BILLING_QUERY or built-in).",
    )
    url_p.add_argument(
        "--max-scan",
        type=int,
        default=5,
        help="Max messages to download and parse (default: 5).",
    )

    args = parser.parse_args(argv)
    if args.command == "run-month":
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

        smtp_user = _smtp_login_user()
        try:
            smtp_pw = _smtp_app_password_from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        if not smtp_pw:
            print(
                f"Set {_ENV_SMTP_PW} or {_ENV_SMTP_PW_FILE} "
                "(Gmail app password; prefer file with chmod 600).",
                file=sys.stderr,
            )
            return 2

        to_addr = _resolve_recipient(args.to)

        try:
            gmail_backend = GmailApiReadBackend.from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2

        smtp_backend = SmtpGmailBackend(user=smtp_user, app_password=smtp_pw)

        try:
            report = run_month(
                gmail_read_backend=gmail_backend,
                billing_query=query,
                max_scan=max_scan,
                debugger_address=addr,
                download_dir=download_dir,
                smtp_backend=smtp_backend,
                smtp_sender=smtp_user,
                to_address=to_addr,
            )
        except RunMonthError as e:
            print(str(e), file=sys.stderr)
            return 2

        print("Run-month completed successfully.", file=sys.stderr)
        print(f"  Billing URL: {report.billing_url}", file=sys.stderr)
        print(f"  PDF saved: {report.pdf_path}", file=sys.stderr)
        print(f"  Invoice: {report.issue_date}, EUR {report.amount_eur}", file=sys.stderr)
        print(f"  Sent to: {report.recipient}", file=sys.stderr)
        print(f"  Subject: {report.email_subject!r}", file=sys.stderr)
        print(f"  Attachment: {report.renamed_filename}", file=sys.stderr)
        return 0

    if args.command == "live-brave-download":
        if os.environ.get(_ENV_CONFIRM_LIVE_BRAVE, "") != "1":
            print(
                f"Refusing: set {_ENV_CONFIRM_LIVE_BRAVE}=1 after confirming Brave is "
                "running with --remote-debugging-port and the billing deeplink is correct.",
                file=sys.stderr,
            )
            return 2
        addr = (args.debugger_address or "").strip() or os.environ.get(
            "GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", ""
        ).strip()
        if not addr:
            print(
                "Provide --debugger-address or set GOOGLEADS_BROWSER_DEBUGGER_ADDRESS "
                "(e.g. 127.0.0.1:9222).",
                file=sys.stderr,
            )
            return 2
        link = (args.deeplink or "").strip() or os.environ.get(
            "GOOGLEADS_BILLING_DEEPLINK", ""
        ).strip()
        if not link:
            print(
                "Provide --deeplink or set GOOGLEADS_BILLING_DEEPLINK "
                "(the c.gle short link from the billing notification mail).",
                file=sys.stderr,
            )
            return 2
        dl_dir_raw = args.download_dir
        if dl_dir_raw is None:
            dl_env = os.environ.get("GOOGLEADS_LIVE_BRAVE_TRACE_DIR", "").strip()
            dl_dir = Path(dl_env).expanduser() if dl_env else Path.home() / "Downloads"
        else:
            dl_dir = dl_dir_raw.expanduser()
        try:
            pdf_path = live_brave_download_pdf(
                debugger_address=addr,
                deeplink_url=link,
                download_dir=dl_dir,
            )
        except LiveBraveDownloadError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"Downloaded PDF: {pdf_path}", file=sys.stderr)
        return 0
    if args.command == "dry-run":
        mail_html_path = _path_from_flag_or_env(
            dry, args.mail_html, _ENV_MAIL_HTML, "--mail-html"
        )
        invoice_pdf_path = _path_from_flag_or_env(
            dry, args.invoice_pdf, _ENV_INVOICE_PDF, "--invoice-pdf"
        )
        month_label = billing_month_label_for_previous_calendar_month()
        report = run_dry_run(
            mail_html_path=mail_html_path,
            invoice_pdf_path=invoice_pdf_path,
            month_label=month_label,
        )
        print(format_dry_run_report(report), end="")
        return 0
    if args.command == "send-test-pdf":
        if os.environ.get(_ENV_CONFIRM_SEND, "") != "1":
            print(
                f"Refusing to send: set {_ENV_CONFIRM_SEND}=1 after confirming recipient.",
                file=sys.stderr,
            )
            return 2
        user = _smtp_login_user()
        try:
            pw = _smtp_app_password_from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        if not pw:
            print(
                f"Set {_ENV_SMTP_PW} or {_ENV_SMTP_PW_FILE} "
                "(Gmail app password; prefer file with chmod 600).",
                file=sys.stderr,
            )
            return 2
        pdf_path = args.pdf
        if pdf_path is None:
            pdf_path = Path("tests/fixtures/pdf/invoice_eur_dot_decimal.pdf")
        try:
            subject, body, attach_name, pdf_resolved = _subject_body_attachment_for_pdf(
                pdf_path,
                attachment_name=args.attachment_name,
            )
        except FileNotFoundError:
            print(f"PDF not found: {pdf_path.expanduser()}", file=sys.stderr)
            return 2
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2
        to_addr = _resolve_recipient(args.to)
        facade = GmailFacade(SmtpGmailBackend(user=user, app_password=pw))
        facade.send_text_with_pdf_attachment(
            sender=user,
            to=to_addr,
            subject=subject,
            body=body,
            pdf_path=pdf_resolved,
            attachment_name=attach_name,
        )
        print(f"Sent test PDF to {to_addr!r} (subject: {subject!r}).", file=sys.stderr)
        return 0
    if args.command == "mail-app-draft":
        if os.environ.get(_ENV_CONFIRM_MAIL_DRAFT, "") != "1":
            print(
                f"Refusing: set {_ENV_CONFIRM_MAIL_DRAFT}=1 after confirming Mail.app draft is OK.",
                file=sys.stderr,
            )
            return 2
        pdf_path = args.pdf
        if pdf_path is None:
            pdf_path = Path("tests/fixtures/pdf/invoice_eur_dot_decimal.pdf")
        try:
            subject, body, attach_name, pdf_resolved = _subject_body_attachment_for_pdf(
                pdf_path,
                attachment_name=args.attachment_name,
            )
        except FileNotFoundError:
            print(f"PDF not found: {pdf_path.expanduser()}", file=sys.stderr)
            return 2
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2
        to_addr = _resolve_recipient(args.to)
        try:
            open_mail_app_draft(
                to_address=to_addr,
                subject=subject,
                body=body,
                pdf_path=pdf_resolved,
                attachment_name=attach_name,
            )
        except MailAppDraftError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(
            f"Opened Mail.app draft to {to_addr!r} (subject: {subject!r}).",
            file=sys.stderr,
        )
        return 0
    if args.command == "list-billing-mail":
        query = (args.query or "").strip() or billing_mail_query_from_env()
        try:
            backend = GmailApiReadBackend.from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        facade = GmailFacade(backend)
        try:
            rows = facade.list_messages(query, max_results=int(args.max_results))
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2
        for r in rows:
            print(f"{r.id}\t{r.thread_id}\t{r.snippet}")
        return 0
    if args.command == "billing-url-from-gmail":
        query = (args.query or "").strip() or billing_mail_query_from_env()
        try:
            backend = GmailApiReadBackend.from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        try:
            rows = backend.list_messages(
                query, max_results=int(args.max_scan)
            )
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 2
        for r in rows:
            try:
                html = backend.get_message_html(r.id)
                url = extract_billing_url(html)
                print(url)
                return 0
            except GmailTransportError as e:
                print(f"{r.id}: {e}", file=sys.stderr)
                continue
            except BillingUrlNotFoundError:
                continue
        print(
            "No billing URL found in scanned messages (try --max-scan or --query).",
            file=sys.stderr,
        )
        return 1
    return 2
