"""SEPA transfer preparation via FinTS against VR Landau."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from invoice_admin.core.config import InvoiceConfig
from invoice_admin.core.errors import HandlerError
from invoice_admin.core.notify import Notification, Notifier
from invoice_admin.core.tracker import InvoiceRow, Tracker

logger = logging.getLogger(__name__)


def _merge_notes(existing: str | None, message: str) -> str:
    parts = [p.strip() for p in [(existing or ""), message] if p.strip()]
    return "\n".join(parts)


def validate_iban(iban: str) -> bool:
    """Validate IBAN using mod-97 check. Returns True if structurally valid."""
    ib = iban.replace(" ", "").upper()
    if len(ib) < 15 or len(ib) > 34:
        return False
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", ib):
        return False
    rearr = ib[4:] + ib[:4]
    digits = ""
    for ch in rearr:
        if ch.isdigit():
            digits += ch
        elif "A" <= ch <= "Z":
            digits += str(ord(ch) - ord("A") + 10)
        else:
            return False
    try:
        return int(digits) % 97 == 1
    except ValueError:
        return False


def _error_blob(exc: BaseException) -> str:
    return json.dumps({"type": type(exc).__name__, "message": str(exc)}, indent=2)


def _append_jsonl_log(config: InvoiceConfig, record: dict[str, Any]) -> None:
    path = config.paths.log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class SepaTransferHandler:
    """Prepares SEPA transfers via FinTS against VR Landau. Dry-run is default."""

    invoice_type = "sepa_transfer"

    def __init__(self, sepa_config: dict[str, Any]) -> None:
        """sepa_config is merged YAML + env (see load_config)."""
        self._blz = str(sepa_config["blz"])
        self._endpoint = str(sepa_config["fints_endpoint"])
        self._code = str(sepa_config.get("code", sepa_config["blz"]))
        self._iban_self = str(sepa_config.get("iban_self", "")).strip()
        self._account_holder = str(sepa_config.get("account_holder", "")).strip()
        self._max_auto_amount = float(sepa_config.get("max_auto_amount_eur", 2000))
        self._dry_run = bool(sepa_config.get("dry_run", True))
        self._tan_mechanism = str(sepa_config.get("tan_mechanism", "decoupledTAN"))

    def execute(
        self,
        row: InvoiceRow,
        tracker: Tracker,
        llm_provider: Any,
        config: InvoiceConfig,
        notifier: Notifier,
    ) -> None:
        """Prepare SEPA transfer (dry-run by default)."""
        if row.status in ("paid", "failed"):
            return

        if not row.iban or not validate_iban(row.iban):
            tracker.update_status(
                row.id,
                "needs_review",
                notes=_merge_notes(row.notes, "Invalid or missing creditor IBAN"),
            )
            notifier.send(
                Notification(
                    title="SEPA needs review",
                    body=f"Row {row.id}: invalid or missing IBAN for {row.vendor or 'unknown'}",
                    priority="high",
                    click_url=None,
                )
            )
            return

        if row.amount is None:
            tracker.update_status(
                row.id,
                "needs_review",
                notes=_merge_notes(row.notes, "Missing invoice amount"),
            )
            notifier.send(
                Notification(
                    title="SEPA needs review",
                    body=f"Row {row.id}: missing amount",
                    priority="high",
                    click_url=None,
                )
            )
            return

        if float(row.amount) > self._max_auto_amount:
            tracker.update_status(
                row.id,
                "needs_review",
                notes=_merge_notes(
                    row.notes,
                    f"Amount €{row.amount} exceeds max_auto_amount_eur={self._max_auto_amount}",
                ),
            )
            notifier.send(
                Notification(
                    title="SEPA needs review",
                    body=(
                        f"Row {row.id}: €{row.amount} exceeds automatic limit "
                        f"€{self._max_auto_amount}"
                    ),
                    priority="high",
                    click_url=None,
                )
            )
            return

        if not self._iban_self:
            tracker.update_status(
                row.id,
                "needs_review",
                notes=_merge_notes(row.notes, "Missing debtor IBAN (INVOICE_ADMIN_IBAN_SELF)"),
            )
            notifier.send(
                Notification(
                    title="SEPA needs review",
                    body="Missing INVOICE_ADMIN_IBAN_SELF",
                    priority="high",
                    click_url=None,
                )
            )
            return

        payload = self._build_sepa_payload(row)

        if self._dry_run:
            now = datetime.now(timezone.utc).isoformat()
            log_record = {
                "event": "sepa_dry_run",
                "ts": now,
                "row_id": row.id,
                "payload": payload,
            }
            _append_jsonl_log(config, log_record)
            logger.info("SEPA dry-run payload: %s", json.dumps(payload, sort_keys=True))
            tracker.update_status(row.id, "prepared")
            amt = row.amount
            vendor = row.vendor or "unknown"
            notifier.send(
                Notification(
                    title="SEPA dry run",
                    body=f"[DRY RUN] Would transfer €{amt} to {vendor}",
                    priority="default",
                    click_url=None,
                )
            )
            return

        pin = os.environ.get("FINTS_PIN", "").strip()
        if not pin:
            tracker.update_status(
                row.id,
                "failed",
                error=_error_blob(HandlerError("Missing FINTS_PIN for live SEPA")),
            )
            notifier.send(
                Notification(
                    title="SEPA failed",
                    body="Missing FINTS_PIN",
                    priority="urgent",
                    click_url=None,
                )
            )
            raise HandlerError("Missing FINTS_PIN for live SEPA")

        try:
            txn_id = self._dispatch_fints(payload, pin)
        except Exception as e:
            tracker.update_status(row.id, "failed", error=_error_blob(e))
            notifier.send(
                Notification(
                    title="SEPA failed",
                    body=str(e)[:4000],
                    priority="urgent",
                    click_url=None,
                )
            )
            raise HandlerError(str(e)) from e

        now = datetime.now(timezone.utc).isoformat()
        note = (row.notes or "").strip()
        if txn_id:
            note = f"{note}\nfints_txn={txn_id}".strip()
        tracker.update_status(row.id, "awaiting_tan", submitted_at=now, notes=note or None)
        notifier.send(
            Notification(
                title="SEPA awaiting TAN",
                body=f"Tap to approve €{row.amount} to {row.vendor or 'vendor'} in SecureGo+",
                priority="high",
                click_url=None,
            )
        )

    def _build_sepa_payload(self, row: InvoiceRow) -> dict[str, Any]:
        """Build the SEPA transfer payload dict. Does NOT call FinTS."""
        return {
            "debitor_iban": self._iban_self,
            "debitor_name": self._account_holder,
            "creditor_iban": (row.iban or "").replace(" ", ""),
            "creditor_bic": row.bic,
            "creditor_name": row.vendor,
            "amount": row.amount,
            "currency": (row.currency or "EUR").upper(),
            "purpose": row.verwendungszweck or "",
            "blz": self._blz,
            "bank_code": self._code,
            "fints_endpoint": self._endpoint,
            "tan_mechanism": self._tan_mechanism,
        }

    def _dispatch_fints(self, payload: dict[str, Any], pin: str) -> str | None:
        """Call FinTS (live). Returns a transaction reference or None when TAN is pending."""
        from fints.client import FinTS3PinTanClient

        login = os.environ.get("INVOICE_ADMIN_FINTS_LOGIN", "").strip()
        product_id = os.environ.get("INVOICE_ADMIN_FINTS_PRODUCT_ID", "").strip()
        if not login or not product_id:
            raise HandlerError(
                "Live FinTS requires INVOICE_ADMIN_FINTS_LOGIN and INVOICE_ADMIN_FINTS_PRODUCT_ID"
            )

        client = FinTS3PinTanClient(
            str(self._blz),
            login,
            pin,
            str(self._endpoint),
            product_id=product_id,
        )
        with client:
            if getattr(client, "init_tan_response", None):
                return None
        return "fints-connected"
