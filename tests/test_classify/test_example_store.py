"""Tests for classifier example JSONL helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_admin.classify.example_store import (
    append_jsonl_record,
    build_classification_few_shot_section,
    build_example_record,
    iter_jsonl_records,
    validate_example_invoice_type,
)
from invoice_admin.core.pdf import ExtractedInvoiceData


def _extracted() -> ExtractedInvoiceData:
    return ExtractedInvoiceData(
        vendor="ACME GmbH",
        invoice_date="2026-03-01",
        due_date="2026-03-15",
        amount=123.45,
        currency="EUR",
        iban="DE89370400440532013000",
        bic="COBADEFFXXX",
        verwendungszweck="INV-9",
        raw_json='{"vendor": "ACME GmbH"}',
    )


def test_validate_example_invoice_type_accepts_known() -> None:
    assert validate_example_invoice_type("sepa_transfer") == "sepa_transfer"


def test_validate_example_invoice_type_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="invoice_type"):
        validate_example_invoice_type("not_a_type")


def test_build_example_record_shape() -> None:
    rec = build_example_record(
        source_pdf="/tmp/x.pdf",
        invoice_type="foyer_claim",
        extracted=_extracted(),
        notes="redacted fixture",
    )
    assert rec["schema_version"] == 1
    assert rec["source_pdf"] == "/tmp/x.pdf"
    assert rec["invoice_type"] == "foyer_claim"
    assert rec["notes"] == "redacted fixture"
    ext = rec["extracted"]
    assert ext["vendor"] == "ACME GmbH"
    assert ext["amount"] == 123.45
    assert ext["iban"] == "DE89370400440532013000"
    assert "raw_json" in ext


def test_append_jsonl_record_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "ex.jsonl"
    r1 = build_example_record("a.pdf", "unknown", _extracted())
    r2 = build_example_record("b.pdf", "sepa_transfer", _extracted())
    append_jsonl_record(out, r1)
    append_jsonl_record(out, r2)
    rows = list(iter_jsonl_records(out))
    assert len(rows) == 2
    assert rows[0]["source_pdf"] == "a.pdf"
    assert rows[1]["invoice_type"] == "sepa_transfer"
    # one JSON object per line, valid UTF-8
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    json.loads(lines[0])


def test_build_classification_few_shot_section_empty_path(tmp_path: Path) -> None:
    missing = tmp_path / "none.jsonl"
    assert build_classification_few_shot_section(missing) == ""


def test_build_classification_few_shot_section_skips_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "ex.jsonl"
    p.write_text("not json\n", encoding="utf-8")
    assert build_classification_few_shot_section(p) == ""


def test_build_classification_few_shot_section_includes_examples(tmp_path: Path) -> None:
    out = tmp_path / "ex.jsonl"
    append_jsonl_record(out, build_example_record("x.pdf", "foyer_claim", _extracted()))
    text = build_classification_few_shot_section(out, max_examples=3)
    assert "Prior labeled examples" in text
    assert "foyer_claim" in text
    assert "ACME GmbH" in text


def test_build_classification_few_shot_respects_max(tmp_path: Path) -> None:
    out = tmp_path / "ex.jsonl"
    for i in range(5):
        append_jsonl_record(
            out,
            build_example_record(f"{i}.pdf", "unknown", _extracted()),
        )
    text = build_classification_few_shot_section(out, max_examples=2)
    assert text.count("Example ") == 2
