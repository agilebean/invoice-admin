"""Tests for SepaTransferHandler and IBAN validation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from invoice_admin.core.config import InvoiceConfig, ModelConfig, NotifyConfig, PathsConfig
from invoice_admin.core.tracker import InvoiceRow, Tracker
from invoice_admin.handlers.sepa_transfer import SepaTransferHandler, validate_iban


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


def _sepa_cfg(*, dry_run: bool = True, iban_self: str = "DE44500105175407324931") -> dict:
    return {
        "blz": "54061170",
        "fints_endpoint": "https://hbci-pintan.gad.de/cgi-bin/hbciservlet",
        "code": "54061170",
        "dry_run": dry_run,
        "max_auto_amount_eur": 2000,
        "iban_self": iban_self,
        "account_holder": "Test User",
        "tan_mechanism": "decoupledTAN",
    }


def test_validate_iban_known_samples() -> None:
    assert validate_iban("DE89 3704 0044 0532 0130 00") is True
    assert validate_iban("DE44500105175407324931") is True


def test_validate_iban_invalid() -> None:
    assert validate_iban("DE00 0000 0000 0000 0000 00") is False
    assert validate_iban("NOPE") is False


def test_sepa_dry_run_writes_log_and_sets_prepared(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    h = SepaTransferHandler(_sepa_cfg(dry_run=True))
    with Tracker(cfg.paths.tracker_path) as tr:
        rid = tr.insert(
            "file",
            "s1",
            invoice_type="sepa_transfer",
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            amount=100.0,
            currency="EUR",
            vendor="ACME",
            verwendungszweck="INV-1",
            status="received",
        )
        row = tr.get(rid)
        assert row is not None
        notifier = MagicMock()
        h.execute(row, tr, MagicMock(), cfg, notifier)

        updated = tr.get(rid)
        assert updated is not None
        assert updated.status == "prepared"
        assert notifier.send.called

    log = cfg.paths.log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(log)
    assert payload["event"] == "sepa_dry_run"
    assert payload["payload"]["creditor_iban"] == "DE89370400440532013000"


def test_sepa_invalid_iban_needs_review(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    h = SepaTransferHandler(_sepa_cfg())
    with Tracker(cfg.paths.tracker_path) as tr:
        rid = tr.insert(
            "file",
            "s2",
            invoice_type="sepa_transfer",
            iban="DE00 0000 0000 0000 0000 00",
            amount=10.0,
            currency="EUR",
            status="received",
        )
        row = tr.get(rid)
        assert row is not None
        h.execute(row, tr, MagicMock(), cfg, MagicMock())
        assert tr.get(rid) and tr.get(rid).status == "needs_review"


def test_sepa_amount_guard_needs_review(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    h = SepaTransferHandler(_sepa_cfg())
    with Tracker(cfg.paths.tracker_path) as tr:
        rid = tr.insert(
            "file",
            "s3",
            invoice_type="sepa_transfer",
            iban="DE89370400440532013000",
            amount=99999.0,
            currency="EUR",
            status="received",
        )
        row = tr.get(rid)
        assert row is not None
        h.execute(row, tr, MagicMock(), cfg, MagicMock())
        assert tr.get(rid) and tr.get(rid).status == "needs_review"


def test_sepa_live_mode_uses_dispatch_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINTS_PIN", "not-a-real-pin")
    cfg = _cfg(tmp_path)
    h = SepaTransferHandler(_sepa_cfg(dry_run=False))

    def fake_dispatch(self, payload, pin):  # type: ignore[no-untyped-def]
        assert pin == "not-a-real-pin"
        return "TX-123"

    monkeypatch.setattr(SepaTransferHandler, "_dispatch_fints", fake_dispatch)

    with Tracker(cfg.paths.tracker_path) as tr:
        rid = tr.insert(
            "file",
            "s4",
            invoice_type="sepa_transfer",
            iban="DE89370400440532013000",
            amount=50.0,
            currency="EUR",
            status="received",
        )
        row = tr.get(rid)
        assert row is not None
        notifier = MagicMock()
        h.execute(row, tr, MagicMock(), cfg, notifier)
        updated = tr.get(rid)
        assert updated is not None
        assert updated.status == "awaiting_tan"
        assert updated.notes and "fints_txn=TX-123" in updated.notes
        assert notifier.send.called
