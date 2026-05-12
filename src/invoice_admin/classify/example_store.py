"""Append-only JSONL store for human-labeled classifier training examples."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from invoice_admin.classify.taxonomy import INVOICE_TYPE_LABELS
from invoice_admin.core.pdf import ExtractedInvoiceData

SCHEMA_VERSION = 1

_FEW_SHOT_FIELD_KEYS: tuple[str, ...] = (
    "vendor",
    "invoice_date",
    "due_date",
    "amount",
    "currency",
    "iban",
    "bic",
    "verwendungszweck",
)


def validate_example_invoice_type(invoice_type: str) -> str:
    """Return normalized label or raise ValueError."""
    label = str(invoice_type).strip()
    if label not in INVOICE_TYPE_LABELS:
        raise ValueError(
            f"invoice_type must be one of {sorted(INVOICE_TYPE_LABELS)!r}, got {invoice_type!r}"
        )
    return label


def _is_valid_few_shot_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    ver = row.get("schema_version", 1)
    if ver != 1:
        return False
    ext = row.get("extracted")
    if not isinstance(ext, dict):
        return False
    label_raw = row.get("invoice_type")
    if label_raw is None:
        return False
    try:
        validate_example_invoice_type(str(label_raw))
    except ValueError:
        return False
    return True


def build_classification_few_shot_section(
    path: Path,
    *,
    max_examples: int = 8,
) -> str:
    """Return prompt text from ``classifier_examples.jsonl``, or empty string if missing/empty."""
    if max_examples < 1:
        return ""
    if not path.is_file():
        return ""
    parts: list[str] = []
    count = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if count >= max_examples:
            break
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not _is_valid_few_shot_row(row):
            continue
        ext = row["extracted"]
        subset = {k: ext.get(k) for k in _FEW_SHOT_FIELD_KEYS}
        blob = json.dumps(subset, indent=2, sort_keys=True)
        label = str(row["invoice_type"]).strip()
        parts.append(f'Example {count + 1} (human label: "{label}"):\n{blob}\n')
        count += 1
    if not parts:
        return ""
    return (
        "Prior labeled examples (extracted fields were verified by a human; "
        "use the same taxonomy for the new invoice below):\n\n"
        + "\n".join(parts)
        + "\n"
    )


def _extracted_to_mapping(extracted: ExtractedInvoiceData) -> dict[str, Any]:
    return {
        "vendor": extracted.vendor,
        "invoice_date": extracted.invoice_date,
        "due_date": extracted.due_date,
        "amount": extracted.amount,
        "currency": extracted.currency,
        "iban": extracted.iban,
        "bic": extracted.bic,
        "verwendungszweck": extracted.verwendungszweck,
        "raw_json": extracted.raw_json,
    }


def build_example_record(
    source_pdf: str,
    invoice_type: str,
    extracted: ExtractedInvoiceData,
    *,
    notes: str = "",
) -> dict[str, Any]:
    """Build one JSON-serializable record (one line in classifier_examples.jsonl)."""
    label = validate_example_invoice_type(invoice_type)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_pdf": str(source_pdf),
        "invoice_type": label,
        "extracted": _extracted_to_mapping(extracted),
        "notes": str(notes or ""),
    }


def append_jsonl_record(path: Path, record: dict[str, Any]) -> None:
    """Append a single JSON object as one UTF-8 line (creates parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def iter_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield parsed objects from a JSONL file (skips blank lines)."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        yield json.loads(line)
