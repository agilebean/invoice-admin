"""Outgoing invoice handler — wraps existing googleads_invoice functionality."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from invoice_admin.core.config import InvoiceConfig
from invoice_admin.core.errors import HandlerError
from invoice_admin.core.notify import Notifier
from invoice_admin.core.tracker import InvoiceRow, Tracker


class OutgoingInvoiceHandler:
    """Wraps googleads_invoice for Gluggle Jug: monthly invoice send + commission PDF save.

    CC/BCC for production SMTP still come from ``googleads_invoice.addresses`` inside
    ``run_month`` until that package is refactored; YAML ``email.cc`` / ``email.bcc`` mirror intent.
    """

    invoice_type = "outgoing_invoice"

    def __init__(
        self,
        handler_config: dict[str, Any],
        *,
        gmail_read: Any | None = None,
        smtp: Any | None = None,
    ) -> None:
        """handler_config is raw YAML from ``outgoing_gluggle.yaml`` (see load_config)."""
        self._cfg = handler_config
        self._gmail_read = gmail_read
        self._smtp = smtp

    @staticmethod
    def _expand_path(value: str) -> Path:
        return Path(value).expanduser().resolve()

    def dry_run_from_paths(
        self,
        mail_html_path: Path,
        invoice_pdf_path: Path,
        month_label: str | None = None,
    ) -> Any:
        """Same contract as ``googleads_invoice.pipeline.run_dry_run`` (fixture-driven)."""
        from googleads_invoice.billing_period import billing_month_label_for_previous_calendar_month
        from googleads_invoice.pipeline import run_dry_run

        label = month_label or billing_month_label_for_previous_calendar_month()
        return run_dry_run(
            mail_html_path=mail_html_path,
            invoice_pdf_path=invoice_pdf_path,
            month_label=label,
        )

    def send_monthly_invoice(
        self,
        *,
        gmail_read_backend: Any,
        smtp_backend: Any,
        test_run: bool = False,
        month_label: str | None = None,
        download_dir: Path | None = None,
        to_address: str | None = None,
        navigation_timeout_s: float = 45,
        download_timeout_s: float = 120,
        max_scan: int = 5,
    ) -> Any:
        """Run Gmail → Brave → parse → SMTP → Dropbox using YAML wiring."""
        from googleads_invoice.run_month import run_month

        billing = self._cfg["billing"]
        email = self._cfg["email"]
        paths = self._cfg["paths"]
        client = self._cfg["client"]
        port = int(billing["brave_debug_port"])
        debugger_address = f"127.0.0.1:{port}"
        query = str(billing["query"])
        dropbox_dir = self._expand_path(str(paths["dropbox_invoice_dir"]))
        smtp_sender = str(email["sender"])
        recipient = to_address or (
            str(email["test_recipient"]) if test_run else str(client["email"])
        )
        dl = download_dir if download_dir is not None else Path.home() / "Downloads"
        return run_month(
            gmail_read_backend=gmail_read_backend,
            billing_query=query,
            max_scan=max_scan,
            debugger_address=debugger_address,
            download_dir=dl,
            navigation_timeout_s=navigation_timeout_s,
            download_timeout_s=download_timeout_s,
            smtp_backend=smtp_backend,
            smtp_sender=smtp_sender,
            to_address=recipient,
            test_run=test_run,
            month_label=month_label,
            dropbox_dir=dropbox_dir,
        )

    def save_commission(
        self,
        *,
        gmail_read_backend: Any,
        test_run: bool = False,
        downloads_dir: Path | None = None,
        commission_dir: Path | None = None,
        max_scan: int = 10,
    ) -> Any:
        """Search commission mail, stage PDF, parse, move to Dropbox (YAML paths)."""
        from googleads_invoice.save_commission_pdf import save_commission_pdf as _save_commission

        commission = self._cfg["commission"]
        paths = self._cfg["paths"]
        q = str(commission["query"])
        dest = (
            commission_dir
            if commission_dir is not None
            else self._expand_path(str(paths["dropbox_commission_dir"]))
        )
        return _save_commission(
            gmail_read_backend=gmail_read_backend,
            commission_query=q,
            max_scan=max_scan,
            commission_dir=dest,
            test_run=test_run,
            downloads_dir=downloads_dir,
        )

    def execute(
        self,
        row: InvoiceRow,
        tracker: Tracker,
        llm_provider: Any,
        config: InvoiceConfig,
        notifier: Notifier,
    ) -> None:
        """Run a queued action from ``row.notes`` JSON: ``action`` = ``run_month`` | ``save_commission``."""
        if row.invoice_type not in (None, "outgoing_invoice"):
            return
        if row.status in ("submitted", "paid", "failed", "reimbursed"):
            return
        try:
            meta = json.loads(row.notes) if row.notes else {}
        except json.JSONDecodeError as e:
            raise HandlerError(f"Invalid outgoing row notes JSON: {e}") from e
        action = meta.get("action")
        if action == "run_month":
            if self._gmail_read is None or self._smtp is None:
                raise HandlerError(
                    "OutgoingInvoiceHandler: pass gmail_read= and smtp= to __init__ for run_month"
                )
            self.send_monthly_invoice(
                gmail_read_backend=self._gmail_read,
                smtp_backend=self._smtp,
                test_run=bool(meta.get("test_run", False)),
                month_label=meta.get("month_label"),
            )
            tracker.update_status(row.id, "submitted")
        elif action == "save_commission":
            if self._gmail_read is None:
                raise HandlerError(
                    "OutgoingInvoiceHandler: pass gmail_read= to __init__ for save_commission"
                )
            self.save_commission(
                gmail_read_backend=self._gmail_read,
                test_run=bool(meta.get("test_run", False)),
            )
            tracker.update_status(row.id, "submitted")
        else:
            raise HandlerError(f"Unknown or missing outgoing action in row notes: {action!r}")
