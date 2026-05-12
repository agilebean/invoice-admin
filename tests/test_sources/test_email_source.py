"""Tests for invoice_admin.sources.email_source."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from invoice_admin.core.config import InvoiceConfig, ModelConfig, NotifyConfig, PathsConfig
from invoice_admin.core.imap import EmailMessage
from invoice_admin.core.tracker import Tracker
from invoice_admin.sources.email_source import ingest_email


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


def test_ingest_email_html_only(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    msg = EmailMessage(
        message_id="<html-1@example.com>",
        sender="a@b.com",
        subject="Invoice",
        date=datetime.now(timezone.utc),
        html_body="<html><body>Vendor ACME amount 12 EUR</body></html>",
        pdf_attachments=[],
    )

    class FakeLLM:
        def __init__(self) -> None:
            self._calls = 0

        def complete(self, prompt: str, **kwargs: object) -> str:
            self._calls += 1
            if self._calls == 1:
                return json.dumps(
                    {
                        "vendor": "ACME",
                        "invoice_date": "2026-04-04",
                        "due_date": None,
                        "amount": 12,
                        "currency": "EUR",
                        "iban": None,
                        "bic": None,
                        "verwendungszweck": None,
                    }
                )
            return json.dumps(
                {"invoice_type": "unknown", "confidence": 0.99, "reasoning": "x"}
            )

        def complete_with_pdf(self, *a, **k):
            raise AssertionError("not used")

    with Tracker(cfg.paths.tracker_path) as tr:
        rid = ingest_email(msg, tr, FakeLLM(), cfg)
        assert rid is not None
        row = tr.get(rid)
        assert row is not None
        assert row.source_type == "email"
        assert Path(row.pdf_path or "").suffix == ".html"
