"""Tests for FoyerClaimHandler (Playwright mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from invoice_admin.core.config import InvoiceConfig, ModelConfig, NotifyConfig, PathsConfig
from invoice_admin.core.tracker import InvoiceRow, Tracker
from invoice_admin.handlers.foyer_claim import FoyerClaimHandler


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


def _playwright_factory(page: MagicMock):
    def factory() -> MagicMock:
        pw = MagicMock()
        pw.__enter__.return_value = pw
        pw.__exit__.return_value = False
        browser = MagicMock()
        pw.chromium.launch.return_value = browser
        context = MagicMock()
        browser.new_context.return_value = context
        context.new_page.return_value = page
        return pw

    return factory


def test_foyer_execute_happy_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FOYER_PLAYWRIGHT_HEADLESS", "1")

    cfg = _cfg(tmp_path)
    cfg.paths.invoices_root.mkdir(parents=True, exist_ok=True)
    pdf = cfg.paths.invoices_root / "bill.pdf"
    pdf.write_bytes(b"%PDF")

    page = MagicMock()
    page.locator.return_value.first.is_visible.return_value = False
    page.get_by_role.side_effect = Exception("use locators")
    page.locator.return_value.first.click.return_value = None
    page.locator.return_value.first.fill.return_value = None
    page.locator.return_value.first.set_input_files.return_value = None
    page.get_by_text.return_value.count.return_value = 0
    page.get_by_text.return_value.first.inner_text.return_value = "Confirmation REF-1"

    handler_cfg = {
        "portal_url": "https://example.invalid",
        "timeout_ms": 5000,
        "locators": {},
    }
    h = FoyerClaimHandler(handler_cfg, playwright_factory=_playwright_factory(page))

    with Tracker(cfg.paths.tracker_path) as tr:
        rid = tr.insert(
            "file",
            "abc",
            invoice_type="foyer_claim",
            pdf_path=str(pdf),
            vendor="Dr Who",
            invoice_date="2026-02-02",
            amount=120.0,
            currency="EUR",
        )
        row = tr.get(rid)
        assert row is not None
        notifier = MagicMock()
        h.execute(row, tr, MagicMock(), cfg, notifier)

        updated = tr.get(rid)
        assert updated is not None
        assert updated.status == "submitted"
        assert updated.submitted_at is not None
        assert updated.notes and "foyer_confirmation=" in updated.notes


def test_foyer_execute_idempotent_terminal(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    handler_cfg = {"portal_url": "https://example.invalid", "timeout_ms": 1000, "locators": {}}
    h = FoyerClaimHandler(handler_cfg, playwright_factory=lambda: MagicMock())

    with Tracker(cfg.paths.tracker_path) as tr:
        rid = tr.insert("file", "x", invoice_type="foyer_claim", status="submitted")
        row = tr.get(rid)
        assert row is not None
        h.execute(row, tr, MagicMock(), cfg, MagicMock())
        # status unchanged
        assert tr.get(rid) and tr.get(rid).status == "submitted"
