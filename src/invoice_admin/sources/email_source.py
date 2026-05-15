"""IMAP email watcher for invoice-bearing emails."""
from __future__ import annotations

import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from invoice_admin.classify.classifier import classify_invoice
from invoice_admin.core.config import InvoiceConfig
from invoice_admin.core.errors import ExtractionError, tracker_error_blob
from invoice_admin.core.imap import EmailMessage
from invoice_admin.core.naming import build_invoice_pdf_filename
from invoice_admin.core.pdf import extract_html_invoice_data, extract_pdf_data
from invoice_admin.core.tracker import Tracker

logger = logging.getLogger(__name__)


def _dest_dir_for_type(invoice_type: str, paths: Any) -> Path:
    if invoice_type == "foyer_claim":
        return paths.foyer_claims_dir
    if invoice_type == "sepa_transfer":
        return paths.sepa_transfers_dir
    if invoice_type == "outgoing_invoice":
        return paths.outgoing_dir
    day = datetime.now(timezone.utc).date().isoformat()
    return paths.failures_dir / day


def _merge_notes(result_notes: str | None, extra_pdfs: int | None) -> str | None:
    obj: dict[str, Any] = {}
    if result_notes:
        obj.update(json.loads(result_notes))
    if extra_pdfs is not None:
        obj["extra_pdf_attachments"] = extra_pdfs
    return json.dumps(obj, sort_keys=True) if obj else None


def ingest_email(
    email_msg: EmailMessage,
    tracker: Tracker,
    llm_provider: Any,
    config: InvoiceConfig,
) -> int | None:
    """Ingest one email: idempotent on Message-ID, classify, persist artifact path + tracker row."""
    if tracker.exists(email_msg.message_id):
        return None

    tmp_path: Path | None = None
    try:
        if email_msg.pdf_attachments:
            if len(email_msg.pdf_attachments) > 1:
                logger.info(
                    "Email %s has %d PDF attachments; processing first only",
                    email_msg.message_id,
                    len(email_msg.pdf_attachments),
                )
            data = email_msg.pdf_attachments[0]
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            extracted = extract_pdf_data(tmp_path, llm_provider)
        elif email_msg.html_body:
            extracted = extract_html_invoice_data(email_msg.html_body, llm_provider)
        else:
            raise ExtractionError("Email has no PDF attachment and no HTML body")

        result = classify_invoice(
            extracted,
            llm_provider,
            min_confidence=config.classifier_min_confidence,
            classifier_examples_path=config.paths.classifier_examples_path,
        )
        ext = result.extracted_data
        filename = build_invoice_pdf_filename(
            invoice_date=ext.invoice_date,
            vendor=ext.vendor,
            amount=ext.amount,
            currency=ext.currency,
        )
        dest_dir = _dest_dir_for_type(result.invoice_type, config.paths)
        dest_dir.mkdir(parents=True, exist_ok=True)

        if tmp_path is not None:
            dest_path = dest_dir / filename
            tmp_path.replace(dest_path)
        else:
            dest_path = dest_dir / (Path(filename).stem + ".html")
            dest_path.write_text(email_msg.html_body or "", encoding="utf-8")

        extra = None
        if email_msg.pdf_attachments and len(email_msg.pdf_attachments) > 1:
            extra = len(email_msg.pdf_attachments) - 1
        notes = _merge_notes(result.review_notes_json(), extra)

        return tracker.insert(
            "email",
            email_msg.message_id,
            invoice_type=result.invoice_type,
            classifier_conf=result.confidence,
            vendor=ext.vendor,
            invoice_date=ext.invoice_date,
            due_date=ext.due_date,
            amount=ext.amount,
            currency=ext.currency,
            iban=ext.iban,
            bic=ext.bic,
            verwendungszweck=ext.verwendungszweck,
            pdf_path=str(dest_path),
            status="received",
            notes=notes,
        )
    except ExtractionError as e:
        return tracker.insert(
            "email",
            email_msg.message_id,
            status="failed",
            error=tracker_error_blob(e),
        )
    except Exception as e:
        try:
            tracker.insert(
                "email",
                email_msg.message_id,
                status="failed",
                error=tracker_error_blob(e),
            )
        except Exception:
            logger.exception("Failed to record tracker failure row")
        raise
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                logger.warning("Could not remove temp PDF %s", tmp_path)


def watch_imap(
    imap_collector: Any,
    tracker: Tracker,
    llm_provider: Any,
    config: InvoiceConfig,
    poll_interval: int = 60,
) -> None:
    """Poll IMAP for new invoice emails and ingest each."""
    while True:
        for msg in imap_collector.collect_unseen():
            try:
                ingest_email(msg, tracker, llm_provider, config)
            except Exception:
                logger.exception("Unexpected failure ingesting %s", msg.message_id)
        time.sleep(poll_interval)
