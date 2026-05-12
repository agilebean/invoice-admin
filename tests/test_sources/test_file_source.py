"""Tests for invoice_admin.sources.file_source."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_admin.core.config import InvoiceConfig, ModelConfig, NotifyConfig, PathsConfig
from invoice_admin.core.errors import ExtractionError
from invoice_admin.core.tracker import Tracker
from invoice_admin.sources.file_source import ingest_pdf_file, sha256_file


def _cfg(tmp: Path) -> InvoiceConfig:
    inv = tmp / "Invoices"
    paths = PathsConfig(
        invoices_root=inv,
        inbox_dir=inv / "_inbox",
        foyer_claims_dir=inv / "foyer_claims",
        sepa_transfers_dir=inv / "sepa_transfers",
        outgoing_dir=inv / "outgoing",
        failures_dir=inv / "_failures",
        tracker_path=tmp / "state" / "tracker.sqlite",
        log_path=tmp / "state" / "log.jsonl",
        llm_calls_path=tmp / "state" / "llm.sqlite",
        classifier_examples_path=tmp / "config" / "classifier_examples.jsonl",
    )
    models = ModelConfig(fast="f", smart="s", cheap="c", local="l")
    notify = NotifyConfig(None, None, None)
    return InvoiceConfig(
        paths=paths,
        models=models,
        notify=notify,
        dry_run=True,
        max_auto_amount_eur=2000,
        classifier_min_confidence=0.7,
        raw={},
    )


def test_sha256_file_stable(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == sha256_file(p)


def test_ingest_pdf_file_idempotent(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True, exist_ok=True)
    pdf = cfg.paths.inbox_dir / "one.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class FakeLLM:
        def complete_with_pdf(self, prompt, pdf_bytes, **kwargs):
            return json.dumps(
                {
                    "vendor": "Vendor",
                    "invoice_date": "2026-03-03",
                    "due_date": None,
                    "amount": 50,
                    "currency": "EUR",
                    "iban": None,
                    "bic": None,
                    "verwendungszweck": None,
                }
            )

        def complete(self, prompt, **kwargs):
            return json.dumps(
                {"invoice_type": "sepa_transfer", "confidence": 0.95, "reasoning": "ok"}
            )

    with Tracker(cfg.paths.tracker_path) as tr:
        r1 = ingest_pdf_file(pdf, tr, FakeLLM(), cfg)
        assert r1 is not None
        assert not pdf.exists()
        dest = list(cfg.paths.sepa_transfers_dir.glob("**/*.pdf"))
        assert len(dest) == 1
        r2 = ingest_pdf_file(dest[0], tr, FakeLLM(), cfg)
        assert r2 is None


def test_ingest_pdf_file_extraction_error_moves_to_failures(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.paths.inbox_dir.mkdir(parents=True, exist_ok=True)
    pdf = cfg.paths.inbox_dir / "bad.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class BoomLLM:
        def complete_with_pdf(self, *a, **k):
            raise ExtractionError("bad pdf")

        def complete(self, *a, **k):
            raise RuntimeError("should not classify")

    with Tracker(cfg.paths.tracker_path) as tr:
        with pytest.raises(ExtractionError):
            ingest_pdf_file(pdf, tr, BoomLLM(), cfg)
    day_dirs = list(cfg.paths.failures_dir.iterdir())
    assert day_dirs
    moved = list(day_dirs[0].glob("bad.pdf"))
    assert moved
    err = day_dirs[0] / "bad.pdf.error.json"
    assert err.is_file()
