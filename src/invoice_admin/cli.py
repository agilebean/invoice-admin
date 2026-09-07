"""CLI entry point for invoice-admin."""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

from invoice_admin.core.config import load_config, repo_root
from invoice_admin.core.errors import ConfigError


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point. Dispatches to subcommands."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="invoice",
        description="Generic invoice handler — ingest, classify, route, track",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest an invoice from a PDF file (defaults to newest PDF from inbox)")
    p_ingest.add_argument("path", nargs="?", type=Path, default=None, help="Path to PDF file (default: newest .pdf in inbox)")
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

    p_send = sub.add_parser("send", help="Send a client's monthly invoice (Gmail → Brave → PDF → email)")
    p_send.add_argument(
        "--client",
        default=None,
        help="Client identifier from config (e.g. glugglejug; required when more than one client is configured)",
    )
    p_send.add_argument(
        "--month",
        help="Billing month (YYYY-MM, defaults to previous calendar month)",
    )
    p_send.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse the invoice, print fields, skip the email send",
    )
    p_send.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the interactive confirmation prompt (for scheduled/automated runs)",
    )

    p_save = sub.add_parser(
        "save",
        help="Save a provider's received document (commission PDF from Gmail → Downloads → commissions folder)",
    )
    p_save.add_argument(
        "--provider",
        default=None,
        help="Provider identifier from config (e.g. googleads; required when more than one provider flow is configured)",
    )
    p_save.add_argument(
        "--client",
        default=None,
        help="Client identifier, to disambiguate when a provider has flows for several clients",
    )
    p_save.add_argument(
        "--month",
        default=None,
        help="Commission month (YYYY-MM); narrows the Gmail search and verifies the mail matches",
    )
    p_save.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip confirmation; stage the renamed PDF under ~/Downloads instead of the commissions folder",
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
    if args.command == "save":
        return _cmd_save(args, config)
    if args.command == "retry":
        return _cmd_retry(args, config)
    if args.command == "review":
        return _cmd_review(args, config)
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
        from invoice_admin.core.spark_link import message_id_from_spark_open_url
        from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend

        try:
            mid = message_id_from_spark_open_url(args.spark_link)
        except ValueError as e:
            print(f"ingest: {e}", file=sys.stderr)
            return 2

        try:
            gmail = GmailApiReadBackend.from_env()
        except ValueError as e:
            print(f"ingest: Gmail auth — {e}", file=sys.stderr)
            return 2

        gmail_msg_id = gmail.find_by_rfc822_message_id(mid)
        if gmail_msg_id is None:
            print(f"ingest: no Gmail message found for {mid!r}", file=sys.stderr)
            return 1

        trio = gmail.get_message_pdf_with_metadata(gmail_msg_id)
        if trio is None:
            print("ingest: email found but has no PDF attachment", file=sys.stderr)
            return 1
        pdf_bytes, subject, _internal_ms = trio

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(pdf_bytes)
            tmp_pdf = Path(tf.name)

        try:
            with Tracker(paths.tracker_path) as tracker:
                llm = LLMProvider(log_path=paths.llm_calls_path)
                rid = ingest_pdf_file(tmp_pdf, tracker, llm, config)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            tmp_pdf.unlink(missing_ok=True)
            return 1
        except Exception as e:
            print(f"ingest failed: {e}", file=sys.stderr)
            tmp_pdf.unlink(missing_ok=True)
            return 1
        tmp_pdf.unlink(missing_ok=True)
        if rid is None:
            print("already ingested (same file hash)", flush=True)
            return 0
        print(f"ingested tracker id={rid} (subject: {subject})", flush=True)
        return 0

    if args.path is None and not args.spark_link:
        inbox = Path(paths.inbox_dir)
        pdfs = sorted(inbox.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True) if inbox.is_dir() else []
        if not pdfs:
            print(f"ingest: no path given and no PDFs found in inbox ({inbox})", file=sys.stderr)
            return 2
        args.path = pdfs[0]
        print(f"ingest: using newest inbox PDF: {args.path}", file=sys.stderr)

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

    inbox = str(paths.inbox_dir)
    print(f"Watching {inbox} for new PDFs (Ctrl-C to stop)...", flush=True)
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


def _client_registry(config: object) -> tuple[dict[str, tuple[str, dict]], dict[str, str]]:
    """Return ``(canonical_client_key -> (handler_name, handler_cfg), alias -> canonical_key)``.

    A handler is a client when its YAML has ``client.key`` and ``client.email``.
    """
    handlers = getattr(config, "raw", {}) or {}
    handlers = handlers.get("handlers") or {}
    clients: dict[str, tuple[str, dict]] = {}
    aliases: dict[str, str] = {}
    for name, h in handlers.items():
        if not isinstance(h, dict):
            continue
        c = h.get("client")
        if not isinstance(c, dict):
            continue
        key = c.get("key")
        if not isinstance(key, str) or not key or not c.get("email"):
            continue
        clients[key] = (name, h)
        for a in c.get("aliases") or []:
            if isinstance(a, str) and a:
                aliases[a] = key
    return clients, aliases


def _resolve_client(
    args: argparse.Namespace, config: object
) -> tuple[str, dict] | None:
    """Pick the handler config for a ``--client`` value; error when unknown or ambiguous."""
    clients, aliases = _client_registry(config)
    if not clients:
        print(
            "send: no clients configured; add client.key + client.email to a handler YAML "
            "(e.g. config/handlers/outgoing_gluggle.yaml)",
            file=sys.stderr,
        )
        return None
    key = args.client
    if key:
        key = aliases.get(key, key)
        if key not in clients:
            print(
                f"send: unknown client {args.client!r}; known clients: {', '.join(sorted(clients))}",
                file=sys.stderr,
            )
            return None
    elif len(clients) == 1:
        key = next(iter(clients))
    else:
        print(
            f"send: choose --client from: {', '.join(sorted(clients))}",
            file=sys.stderr,
        )
        return None
    return key, clients[key][1]


def _provider_registry(config: object) -> list[tuple[str, str, str, dict]]:
    """Return ``(provider, client_key, handler_name, handler_cfg)`` for every commission flow."""
    handlers = getattr(config, "raw", {}) or {}
    handlers = handlers.get("handlers") or {}
    flows: list[tuple[str, str, str, dict]] = []
    for name, h in handlers.items():
        if not isinstance(h, dict):
            continue
        comm = h.get("commission")
        if not isinstance(comm, dict):
            continue
        provider = comm.get("provider")
        if not isinstance(provider, str) or not provider:
            continue
        c = h.get("client")
        client_key = c.get("key") if isinstance(c, dict) else None
        if not isinstance(client_key, str) or not client_key:
            continue
        flows.append((provider, client_key, name, h))
    return flows


def _resolve_provider(
    args: argparse.Namespace, config: object
) -> tuple[str, str, str, dict] | None:
    """Pick the handler config for a ``--provider`` (+ optional ``--client``) value."""
    flows = _provider_registry(config)
    if not flows:
        print(
            "save: no provider flows configured; add commission.provider + client.key to a handler YAML",
            file=sys.stderr,
        )
        return None
    if args.provider:
        flows = [f for f in flows if f[0] == args.provider]
    if args.client:
        clients, aliases = _client_registry(config)
        ck = aliases.get(args.client, args.client)
        flows = [f for f in flows if f[1] == ck]
    if not flows:
        known = sorted({f[0] for f in _provider_registry(config)})
        print(
            f"save: no provider flow matches (provider={args.provider!r}, client={args.client!r}); "
            f"known providers: {', '.join(known)}",
            file=sys.stderr,
        )
        return None
    if len(flows) > 1:
        options = ", ".join(f"{f[1]} ({f[0]})" for f in sorted(flows))
        print(
            f"save: matches multiple flows; choose --client from: {options}",
            file=sys.stderr,
        )
        return None
    return flows[0]


def _cmd_send(args: argparse.Namespace, config: object) -> int:
    """Send a client's monthly Google Ads invoice (requires Gmail, SMTP, Brave)."""
    resolved = _resolve_client(args, config)
    if resolved is None:
        return 2
    _client_key, hcfg = resolved

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.googleads.gmail_smtp import (
        _smtp_app_password_from_env,
        _smtp_login_user,
        SmtpGmailBackend,
    )

    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    smtp_user = _smtp_login_user()
    is_dry = bool(args.dry_run)
    if not is_dry:
        try:
            smtp_pw = _smtp_app_password_from_env()
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        if not smtp_pw:
            print(
                "send: set Gmail SMTP app password env "
                "(GOOGLEADS_GMAIL_SMTP_APP_PASSWORD or GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE).",
                file=sys.stderr,
            )
            return 2
    else:
        smtp_pw = "dry-run"

    try:
        gmail_backend = GmailApiReadBackend.from_env()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not is_dry and not args.yes:
        client_email = str(hcfg["client"]["email"])
        print(f"About to send invoice to {client_email}:", file=sys.stderr)
        try:
            confirm = input("  Confirm? (Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm not in ("", "y", "yes"):
            print("Aborted.", file=sys.stderr)
            return 2

    smtp_backend = SmtpGmailBackend(user=smtp_user, app_password=smtp_pw)
    handler = OutgoingInvoiceHandler(hcfg, gmail_read=gmail_backend, smtp=smtp_backend)

    from invoice_admin.googleads.run_month import RunMonthError

    try:
        report = handler.send_monthly_invoice(
            gmail_read_backend=gmail_backend,
            smtp_backend=smtp_backend,
            dry_run=is_dry,
            month_label=args.month,
        )
    except RunMonthError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"send failed: {e}", file=sys.stderr)
        return 1
    if is_dry:
        print(f"  Billing URL: {report.billing_url}", file=sys.stderr)
        print(f"  Invoice: {report.issue_date}, EUR {report.amount_eur}", file=sys.stderr)
        print(f"  Filename: {report.renamed_filename}", file=sys.stderr)
        print("Dry run complete (no email sent).", file=sys.stderr)
        return 0
    print("send completed.", flush=True)
    print(f"  Invoice: {report.issue_date}, EUR {report.amount_eur}", file=sys.stderr)
    print(f"  Sent to: {report.recipient}", file=sys.stderr)
    print(f"  Subject: {report.email_subject!r}", file=sys.stderr)
    print(f"  Attachment: {report.renamed_filename}", file=sys.stderr)
    return 0


def _parse_commission_month(raw: str | None) -> date | None:
    """Parse ``YYYY-MM`` into the first day of that month; None when no flag given."""
    if raw is None:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})", raw)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return date(year, month, 1)


def _cmd_save(args: argparse.Namespace, config: object) -> int:
    """Save a provider's commission PDF (Gmail → Downloads staging → commissions folder)."""
    resolved = _resolve_provider(args, config)
    if resolved is None:
        return 2
    provider, client_key, _handler_name, hcfg = resolved

    expected_month = _parse_commission_month(args.month)
    if args.month and expected_month is None:
        print(f"save: --month must be YYYY-MM (got {args.month!r})", file=sys.stderr)
        return 2

    from invoice_admin.googleads.gmail_api_backend import (
        GmailApiReadBackend,
        commission_mail_query_from_env,
    )

    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    try:
        gmail_backend = GmailApiReadBackend.from_env()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    comm = hcfg["commission"]
    query = (os.environ.get("GOOGLEADS_COMMISSION_QUERY", "").strip()
             or str(comm.get("query") or "").strip()
             or commission_mail_query_from_env())
    if expected_month is not None:
        import calendar
        month_name = calendar.month_name[expected_month.month]
        query = f'{query} subject:"{month_name}"'
    dest = Path(str(hcfg["paths"]["commission_dir"])).expanduser()

    if not args.dry_run:
        print("About to save commission PDF:", file=sys.stderr)
        print(f"  Client: {client_key}", file=sys.stderr)
        print(f"  Provider: {provider}", file=sys.stderr)
        print(f"  Query: {query}", file=sys.stderr)
        print(f"  Destination: {dest}", file=sys.stderr)
        try:
            confirm = input("  Confirm? (Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm not in ("", "y", "yes"):
            print("Aborted.", file=sys.stderr)
            return 2

    handler = OutgoingInvoiceHandler(hcfg, gmail_read=gmail_backend)
    try:
        report = handler.save_commission(
            gmail_read_backend=gmail_backend,
            dry_run=args.dry_run,
            commission_query=query,
            expected_month=expected_month,
        )
    except Exception as e:
        print(f"save failed: {e}", file=sys.stderr)
        return 1
    print("Commission PDF saved successfully.", file=sys.stderr)
    print(f"  PDF: {report.pdf_path}", file=sys.stderr)
    print(f"  Date: {report.commission_date}, EUR {report.amount_eur}", file=sys.stderr)
    print(f"  Renamed: {report.renamed_filename}", file=sys.stderr)
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
