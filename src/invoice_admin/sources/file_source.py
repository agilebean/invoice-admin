"""Filesystem watcher for invoice PDFs."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from invoice_admin.classify.classifier import extract_and_classify
from invoice_admin.core.config import InvoiceConfig
from invoice_admin.core.errors import ExtractionError
from invoice_admin.core.naming import build_invoice_pdf_filename
from invoice_admin.core.tracker import Tracker

logger = logging.getLogger(__name__)


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dest_dir_for_type(invoice_type: str, paths: Any) -> Path:
    year = datetime.now(timezone.utc).year
    if invoice_type == "foyer_claim":
        return paths.foyer_claims_dir / str(year)
    if invoice_type == "sepa_transfer":
        return paths.sepa_transfers_dir / str(year)
    if invoice_type == "outgoing_invoice":
        return paths.outgoing_dir / str(year)
    day = datetime.now(timezone.utc).date().isoformat()
    return paths.failures_dir / day


def _move_to_failure(
    pdf_path: Path,
    paths: Any,
    exc: ExtractionError,
) -> None:
    day = datetime.now(timezone.utc).date().isoformat()
    dest_dir = paths.failures_dir / day
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / pdf_path.name
    shutil.move(str(pdf_path), str(dest))
    err_path = dest_dir / f"{pdf_path.name}.error.json"
    err_path.write_text(
        json.dumps(
            {
                "type": "ExtractionError",
                "message": str(exc),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def ingest_pdf_file(
    pdf_path: Path,
    tracker: Tracker,
    llm_provider: Any,
    config: InvoiceConfig,
) -> int | None:
    """Ingest a single PDF from disk: classify, move, insert tracker row."""
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    digest = sha256_file(pdf_path)
    if tracker.exists(digest):
        return None

    try:
        result = extract_and_classify(
            pdf_path,
            llm_provider,
            min_confidence=config.classifier_min_confidence,
            classifier_examples_path=config.paths.classifier_examples_path,
        )
    except ExtractionError as e:
        _move_to_failure(pdf_path, config.paths, e)
        raise

    ext = result.extracted_data
    filename = build_invoice_pdf_filename(
        invoice_date=ext.invoice_date,
        vendor=ext.vendor,
        amount=ext.amount,
        currency=ext.currency,
    )
    dest_dir = _dest_dir_for_type(result.invoice_type, config.paths)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    shutil.move(str(pdf_path), str(dest_path))

    notes = result.review_notes_json()
    return tracker.insert(
        "file",
        digest,
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


def watch_inbox(
    inbox_dir: Path,
    tracker: Tracker,
    llm_provider: Any,
    config: InvoiceConfig,
    poll_interval: int = 10,
) -> None:
    """Poll inbox_dir for new PDFs and ingest each (blocks until KeyboardInterrupt)."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    while True:
        for path in sorted(inbox_dir.glob("*.pdf")):
            try:
                ingest_pdf_file(path, tracker, llm_provider, config)
            except ExtractionError:
                logger.exception("Extraction failed for %s", path)
            except Exception:
                logger.exception("Unexpected failure ingesting %s", path)
        time.sleep(poll_interval)
