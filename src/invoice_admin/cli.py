"""CLI entry point for invoice-admin."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from invoice_admin.core.config import load_config, repo_root
from invoice_admin.core.errors import ConfigError


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point. Dispatches to subcommands."""
    parser = argparse.ArgumentParser(
        prog="invoice",
        description="Generic invoice handler — ingest, classify, route, track",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest an invoice from a PDF file")
    p_ingest.add_argument("path", nargs="?", type=Path, default=None, help="Path to PDF file")
    p_ingest.add_argument(
        "--email",
        dest="spark_link",
        metavar="SPARK-LINK",
        help="Spark readdle-spark://openmessage?messageId=… link (requires IMAP env vars)",
    )

    p_watch = sub.add_parser("watch", help="Watch inbox folder or IMAP for new invoices")
    p_watch.add_argument(
        "--source",
        choices=("inbox", "imap"),
        default="inbox",
        help="inbox = local PDF folder; imap = UNSEEN invoice-like mail (needs IMAP env vars)",
    )

    p_status = sub.add_parser("status", help="Show invoice tracker status")
    p_status.add_argument("--type", dest="invoice_type", help="Filter by invoice type")
    p_status.add_argument("--status", dest="status", help="Filter by status")

    sub.add_parser("followup", help="Run followup engine once")

    p_send = sub.add_parser("send", help="Send outgoing invoice manually")
    p_send.add_argument(
        "--client",
        required=True,
        help="Client identifier (currently: gluggle)",
    )
    p_send.add_argument(
        "--month",
        help="Billing month (YYYY-MM, defaults to previous calendar month)",
    )

    p_retry = sub.add_parser("retry", help="Retry a failed invoice")
    p_retry.add_argument("id", type=int, help="Tracker row ID")
    p_retry.add_argument(
        "--approve",
        action="store_true",
        help="Confirm resetting a failed row back to received",
    )

    p_review = sub.add_parser("review", help="Review and approve a needs_review invoice")
    p_review.add_argument("id", type=int, help="Tracker row ID")
    p_review.add_argument(
        "--approve",
        action="store_true",
        help="Confirm restoring classification from review notes",
    )

    sub.add_parser("cost", help="Show LLM cost dashboard (last 7/30 days)")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        root = repo_root()
        config = load_config(root)
    except (RuntimeError, ConfigError, OSError, ValueError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    return _dispatch(args, config)


def _dispatch(args: argparse.Namespace, config: object) -> int:
    """Route to the correct subcommand handler."""
    if args.command == "ingest":
        return _cmd_ingest(args, config)
    if args.command == "watch":
        return _cmd_watch(args, config)
    if args.command == "status":
        return _cmd_status(args, config)
    if args.command == "followup":
        return _cmd_followup(args, config)
    if args.command == "send":
        return _cmd_send(args, config)
    if args.command == "retry":
        return _cmd_retry(args, config)
    if args.command == "review":
        return _cmd_review(args, config)
    if args.command == "cost":
        return _cmd_cost(args, config)
    return 1


def _cmd_ingest(args: argparse.Namespace, config: object) -> int:
    """Handle `invoice ingest <path>` or `invoice ingest --email <link>`."""
    from invoice_admin.core.llm import LLMProvider
    from invoice_admin.core.tracker import Tracker
    from invoice_admin.sources.file_source import ingest_pdf_file

    paths = config.paths  # type: ignore[attr-defined]
    if args.spark_link and args.path is not None:
        print("ingest: use either a PDF path or --email, not both", file=sys.stderr)
        return 2

    if args.spark_link:
        from invoice_admin.core.imap import fetch_email_by_message_id
        from invoice_admin.core.spark_link import message_id_from_spark_open_url
        from invoice_admin.sources.email_source import ingest_email

        try:
            mid = message_id_from_spark_open_url(args.spark_link)
        except ValueError as e:
            print(f"ingest: {e}", file=sys.stderr)
            return 2
        host = os.environ.get("INVOICE_ADMIN_IMAP_HOST", "").strip()
        user = os.environ.get("INVOICE_ADMIN_IMAP_USER", "").strip()
        pw = os.environ.get("INVOICE_ADMIN_IMAP_PASSWORD", "").strip()
        mbox = os.environ.get("INVOICE_ADMIN_IMAP_MAILBOX", "INBOX").strip() or "INBOX"
        if not host or not user or not pw:
            print(
                "ingest --email needs INVOICE_ADMIN_IMAP_HOST, INVOICE_ADMIN_IMAP_USER, "
                "INVOICE_ADMIN_IMAP_PASSWORD (optional INVOICE_ADMIN_IMAP_MAILBOX).",
                file=sys.stderr,
            )
            return 2
        try:
            em = fetch_email_by_message_id(host, user, pw, mid, mailbox=mbox)
        except OSError as e:
            print(f"IMAP connection failed: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"IMAP fetch failed: {e}", file=sys.stderr)
            return 1
        if em is None:
            print("no message found with that Message-ID", file=sys.stderr)
            return 1
        try:
            with Tracker(paths.tracker_path) as tracker:
                llm = LLMProvider(log_path=paths.llm_calls_path)
                rid = ingest_email(em, tracker, llm, config)
        except Exception as e:
            print(f"ingest failed: {e}", file=sys.stderr)
            return 1
        if rid is None:
            print("already ingested (same Message-ID)", flush=True)
            return 0
        print(f"ingested tracker id={rid}", flush=True)
        return 0

    if args.path is None:
        print("ingest: provide a PDF path or --email with a Spark link", file=sys.stderr)
        return 2
    pdf_path = args.path.expanduser()
    try:
        with Tracker(paths.tracker_path) as tracker:
            llm = LLMProvider(log_path=paths.llm_calls_path)
            rid = ingest_pdf_file(pdf_path, tracker, llm, config)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ingest failed: {e}", file=sys.stderr)
        return 1
    if rid is None:
        print("already ingested (same file hash)", flush=True)
        return 0
    print(f"ingested tracker id={rid}", flush=True)
    return 0


def _cmd_watch(args: argparse.Namespace, config: object) -> int:
    """Poll local inbox PDFs or IMAP UNSEEN until interrupted."""
    from invoice_admin.core.llm import LLMProvider
    from invoice_admin.core.tracker import Tracker

    paths = config.paths  # type: ignore[attr-defined]
    source = getattr(args, "source", "inbox") or "inbox"

    if source == "imap":
        from invoice_admin.core.imap import ImapCollector
        from invoice_admin.sources.email_source import watch_imap

        host = os.environ.get("INVOICE_ADMIN_IMAP_HOST", "").strip()
        user = os.environ.get("INVOICE_ADMIN_IMAP_USER", "").strip()
        pw = os.environ.get("INVOICE_ADMIN_IMAP_PASSWORD", "").strip()
        mbox = os.environ.get("INVOICE_ADMIN_IMAP_MAILBOX", "INBOX").strip() or "INBOX"
        if not host or not user or not pw:
            print(
                "watch --source imap needs INVOICE_ADMIN_IMAP_HOST, INVOICE_ADMIN_IMAP_USER, "
                "INVOICE_ADMIN_IMAP_PASSWORD (optional INVOICE_ADMIN_IMAP_MAILBOX).",
                file=sys.stderr,
            )
            return 2
        poll_s = 60
        raw_poll = os.environ.get("INVOICE_ADMIN_IMAP_POLL_SECONDS", "").strip()
        if raw_poll:
            try:
                poll_s = max(10, int(raw_poll))
            except ValueError:
                poll_s = 60
        collector = ImapCollector(host, user, pw, mailbox=mbox)
        try:
            with Tracker(paths.tracker_path) as tracker:
                llm = LLMProvider(log_path=paths.llm_calls_path)
                watch_imap(collector, tracker, llm, config, poll_interval=poll_s)
        except KeyboardInterrupt:
            return 0
        return 0

    from invoice_admin.sources.file_source import watch_inbox

    try:
        with Tracker(paths.tracker_path) as tracker:
            llm = LLMProvider(log_path=paths.llm_calls_path)
            watch_inbox(paths.inbox_dir, tracker, llm, config, poll_interval=10)
    except KeyboardInterrupt:
        return 0
    return 0


def _cmd_status(args: argparse.Namespace, config: object) -> int:
    """Print tracker rows (plain text)."""
    from invoice_admin.core.tracker import Tracker

    paths = config.paths  # type: ignore[attr-defined]
    inv_t = getattr(args, "invoice_type", None)
    st = getattr(args, "status", None)
    with Tracker(paths.tracker_path) as tracker:
        rows = tracker.list_rows(invoice_type=inv_t, status=st)
    for r in rows:
        line = (
            f"  {r.id:>5}  {r.status:<14}  {r.invoice_type or '-':<18}  "
            f"{r.vendor or '-':<20}  €{r.amount or 0}  {r.pdf_path or '-'}"
        )
        print(line, flush=True)
    print(f"{len(rows)} row(s)", flush=True)
    return 0


def _cmd_followup(_args: argparse.Namespace, config: object) -> int:
    """Run followup engine once."""
    from invoice_admin.core.notify import Notifier
    from invoice_admin.core.tracker import Tracker
    from invoice_admin.followup.engine import FollowupEngine

    paths = config.paths  # type: ignore[attr-defined]
    notify = config.notify  # type: ignore[attr-defined]
    notifier = Notifier(
        ntfy_topic=notify.ntfy_topic,
        pushover_user=notify.pushover_user,
        pushover_token=notify.pushover_token,
    )
    with Tracker(paths.tracker_path) as tracker:
        engine = FollowupEngine(tracker, notifier, config)
        actions = engine.run_once()
    for a in actions:
        print(a, flush=True)
    return 0


def _cmd_send(args: argparse.Namespace, config: object) -> int:
    """Send Gluggle outgoing invoice (requires Gmail, SMTP, Brave; same guards as legacy CLI)."""
    if args.client != "gluggle":
        print("send: only --client gluggle is supported", file=sys.stderr)
        return 2

    _ENV_CONFIRM_RUN_MONTH = "GOOGLEADS_CONFIRM_RUN_MONTH"
    if os.environ.get(_ENV_CONFIRM_RUN_MONTH, "") != "1":
        print(
            f"Refusing: set {_ENV_CONFIRM_RUN_MONTH}=1 after confirming secrets, Brave, and recipient.",
            file=sys.stderr,
        )
        return 2

    raw = getattr(config, "raw", {}) or {}
    handlers = raw.get("handlers") or {}
    hcfg = handlers.get("outgoing_gluggle")
    if not hcfg:
        print("send: missing config/handlers/outgoing_gluggle.yaml", file=sys.stderr)
        return 2

    from googleads_invoice.addresses import DEFAULT_PRODUCTION_RECIPIENT, DEFAULT_TEST_RECIPIENT
    from googleads_invoice.cli import _smtp_app_password_from_env, _smtp_login_user
    from googleads_invoice.gmail_api_backend import GmailApiReadBackend
    from googleads_invoice.gmail_smtp import SmtpGmailBackend

    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    smtp_user = _smtp_login_user()
    try:
        smtp_pw = _smtp_app_password_from_env()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not smtp_pw:
        print("send: set Gmail SMTP app password env (see googleads_invoice CLI docs).", file=sys.stderr)
        return 2

    try:
        gmail_backend = GmailApiReadBackend.from_env()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    smtp_backend = SmtpGmailBackend(user=smtp_user, app_password=smtp_pw)
    handler = OutgoingInvoiceHandler(hcfg, gmail_read=gmail_backend, smtp=smtp_backend)

    test_run = os.environ.get("INVOICE_ADMIN_SEND_TEST", "").strip() == "1"
    to_address = DEFAULT_TEST_RECIPIENT if test_run else DEFAULT_PRODUCTION_RECIPIENT

    if not test_run:
        month_str = args.month or ""
        print(f"About to send invoice ({month_str or 'default month'}) to production:", file=sys.stderr)
        print(f"  To: {to_address}", file=sys.stderr)
        try:
            confirm = input("  Confirm? (Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm not in ("", "y", "yes"):
            print("Aborted.", file=sys.stderr)
            return 2

    from googleads_invoice.run_month import RunMonthError

    try:
        handler.send_monthly_invoice(
            gmail_read_backend=gmail_backend,
            smtp_backend=smtp_backend,
            test_run=test_run,
            month_label=args.month,
            to_address=to_address if test_run else None,
        )
    except RunMonthError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"send failed: {e}", file=sys.stderr)
        return 1
    print("send completed.", flush=True)
    return 0


def _cmd_retry(args: argparse.Namespace, config: object) -> int:
    """Reset a failed row to ``received`` and clear ``error`` (handlers may pick up later)."""
    from invoice_admin.core.tracker import Tracker

    paths = config.paths  # type: ignore[attr-defined]
    if not args.approve:
        print("retry: add --approve to clear error and set status to received", file=sys.stderr)
        return 2
    with Tracker(paths.tracker_path) as tracker:
        row = tracker.get(args.id)
        if row is None:
            print(f"no row id={args.id}", file=sys.stderr)
            return 1
        if row.status != "failed":
            print(f"retry: row {args.id} has status={row.status!r}, expected failed", file=sys.stderr)
            return 1
        err_preview = (row.error or "")[:200]
        tracker.update_status(args.id, "received", error=None)
    print(f"retry: id={args.id} set to received (cleared error). Previous error snippet: {err_preview!r}", flush=True)
    return 0


def _cmd_review(args: argparse.Namespace, config: object) -> int:
    """Approve ``needs_review``: restore ``original_type`` from ``notes`` JSON, then ``received``."""
    import json

    from invoice_admin.core.tracker import Tracker

    _RESTORE_TYPES = frozenset({"foyer_claim", "sepa_transfer", "outgoing_invoice", "unknown"})

    paths = config.paths  # type: ignore[attr-defined]
    if not args.approve:
        print("review: add --approve to apply classification from review notes", file=sys.stderr)
        return 2
    with Tracker(paths.tracker_path) as tracker:
        row = tracker.get(args.id)
        if row is None:
            print(f"no row id={args.id}", file=sys.stderr)
            return 1
        if row.status != "needs_review":
            print(f"review: row {args.id} has status={row.status!r}, expected needs_review", file=sys.stderr)
            return 1
        notes_obj: dict[str, object] = {}
        if row.notes:
            try:
                parsed = json.loads(row.notes)
                if isinstance(parsed, dict):
                    notes_obj = parsed
            except json.JSONDecodeError:
                pass
        orig = notes_obj.get("original_type")
        if not isinstance(orig, str) or orig not in _RESTORE_TYPES:
            orig = "unknown"
        try:
            orig_conf = float(notes_obj["original_confidence"])  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            orig_conf = row.classifier_conf if row.classifier_conf is not None else 0.0
        tracker.update_status(
            args.id,
            "received",
            invoice_type=orig,
            classifier_conf=orig_conf,
            notes=None,
        )
    print(f"review: id={args.id} set to received with invoice_type={orig!r}", flush=True)
    return 0


def _cmd_cost(_args: argparse.Namespace, config: object) -> int:
    """Print LLM cost report."""
    from invoice_admin.core.llm import format_llm_cost_report

    paths = config.paths  # type: ignore[attr-defined]
    text = format_llm_cost_report(paths.llm_calls_path)
    print(text, end="", flush=True)
    return 0
