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
from invoice_admin.core.naming import build_failure_filename, build_invoice_pdf_filename
from invoice_admin.core.tracker import Tracker

logger = logging.getLogger(__name__)


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ocr_pdf_for_metadata(pdf_bytes: bytes) -> str:
    """Try to OCR a PDF to extract vendor/date/topic for renaming on failure."""
    try:
        import pypdf
        from io import BytesIO

        import pytesseract
        from PIL import Image

        reader = pypdf.PdfReader(BytesIO(pdf_bytes))
        parts: list[str] = []
        for page in reader.pages:
            for img in page.images:
                try:
                    pil_img = Image.open(BytesIO(img.data))
                    text = pytesseract.image_to_string(pil_img, lang="eng+deu").strip()
                    if text:
                        parts.append(text)
                except Exception:
                    pass
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_metadata_via_ocr(pdf_path: Path) -> tuple[str | None, str | None, str | None]:
    """Quick OCR to get vendor, date, and topic for failure renaming."""
    try:
        text = _ocr_pdf_for_metadata(pdf_path.read_bytes())
        if not text.strip():
            return None, None, None

        from invoice_admin.core.config import load_config, repo_root
        from invoice_admin.core.llm import LLMProvider

        root = repo_root()
        config = load_config(root)
        llm = LLMProvider(log_path=config.paths.llm_calls_path)

        prompt = (
            "Extract from this OCR'd document text ONLY a JSON object with these fields. "
            "Return ONLY the JSON, no other text:\n"
            '{"vendor": "sender/issuer name or null", '
            '"invoice_date": "YYYY-MM-DD or null", '
            '"document_topic": "brief topic like shoulder medical receipt or null"}\n\n'
            "Text:\n"
            + text[:5000]
        )
        raw = llm.complete(prompt, model_alias="fast", purpose="ocr_metadata")
        import json as _json
        import re as _re
        m = _re.search(r"\{[\s\S]*\}", raw.strip())
        if m:
            data = _json.loads(m.group(0))
            vendor = str(data.get("vendor", "")).strip() or None
            invoice_date = str(data.get("invoice_date", "")).strip() or None
            doc_topic = str(data.get("document_topic", "")).strip() or None
            return vendor, invoice_date, doc_topic
    except Exception:
        pass
    return None, None, None


def _dest_dir_for_type(invoice_type: str, paths: Any) -> Path:
    if invoice_type == "foyer_claim":
        return paths.foyer_claims_dir
    if invoice_type == "sepa_transfer":
        return paths.sepa_transfers_dir
    if invoice_type == "outgoing_invoice":
        return paths.outgoing_dir
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

    vendor, date_str, topic = _extract_metadata_via_ocr(pdf_path)
    filename = build_failure_filename(
        vendor=vendor,
        invoice_date=date_str,
        document_topic=topic,
    )
    dest = dest_dir / filename
    # Avoid overwriting existing files
    if dest.exists():
        stem = dest.stem
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}.pdf"
            counter += 1
    shutil.move(str(pdf_path), str(dest))
    err_path = dest_dir / f"{filename}.error.json"
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
        document_topic=ext.document_topic,
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
    print(f"watch-inbox: polling every {poll_interval}s", flush=True)
    while True:
        for path in sorted(inbox_dir.glob("*.pdf")):
            print(f"ingesting {path.name}...", flush=True)
            try:
                rid = ingest_pdf_file(path, tracker, llm_provider, config)
                if rid is not None:
                    print(f"  ingested → row {rid}", flush=True)
                else:
                    print("  already ingested (same hash)", flush=True)
            except ExtractionError:
                logger.exception("Extraction failed for %s", path)
            except Exception:
                logger.exception("Unexpected failure ingesting %s", path)
        time.sleep(poll_interval)
