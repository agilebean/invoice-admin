"""Tests for handler Protocol and path helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from invoice_admin.core.config import InvoiceConfig, ModelConfig, NotifyConfig, PathsConfig
from invoice_admin.core.tracker import InvoiceRow, Tracker
from invoice_admin.handlers.base import Handler, prepare_invoice_pdf, rename_invoice_pdf


class _DummyHandler:
    @property
    def invoice_type(self) -> str:
        return "dummy"

    def execute(self, row, tracker, llm_provider, config, notifier) -> None:  # type: ignore[no-untyped-def]
        return None


def test_handler_protocol_runtime_checkable() -> None:
    assert isinstance(_DummyHandler(), Handler)


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


def test_prepare_invoice_pdf_resolves_relative_to_invoices_root(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.paths.invoices_root.mkdir(parents=True, exist_ok=True)
    rel = Path("sub") / "a.pdf"
    abs_dir = cfg.paths.invoices_root / "sub"
    abs_dir.mkdir(parents=True, exist_ok=True)
    (abs_dir / "a.pdf").write_bytes(b"%PDF")

    row = InvoiceRow(
        id=1,
        status="received",
        ingested_at="",
        status_updated_at="",
        source_type="file",
        source_ref="x",
        pdf_path=str(rel),
    )
    got = prepare_invoice_pdf(row, cfg)
    assert got.is_file()


def test_prepare_invoice_pdf_missing_raises(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    row = InvoiceRow(
        id=1,
        status="received",
        ingested_at="",
        status_updated_at="",
        source_type="file",
        source_ref="x",
        pdf_path=str(tmp_path / "nope.pdf"),
    )
    with pytest.raises(FileNotFoundError):
        prepare_invoice_pdf(row, cfg)


def test_rename_invoice_pdf(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.paths.invoices_root.mkdir(parents=True, exist_ok=True)
    p = cfg.paths.invoices_root / "old.pdf"
    p.write_bytes(b"%PDF")

    row = InvoiceRow(
        id=1,
        status="received",
        ingested_at="",
        status_updated_at="",
        source_type="file",
        source_ref="x",
        pdf_path=str(p),
        invoice_date="2026-01-10",
        amount=25.0,
        currency="EUR",
    )
    out = rename_invoice_pdf(row, cfg, vendor_slug="Acme Co")
    assert out.name.endswith("EUR.pdf")
    assert out.exists()
