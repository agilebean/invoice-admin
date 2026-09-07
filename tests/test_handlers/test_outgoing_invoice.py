"""Tests for OutgoingInvoiceHandler wiring (no live I/O)."""
from __future__ import annotations

from pathlib import Path

import yaml

from invoice_admin.core.config import repo_root
from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler


def _gluggle_yaml() -> dict:
    p = repo_root() / "config" / "handlers" / "outgoing_gluggle.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_handler_loads_gluggle_yaml() -> None:
    cfg = _gluggle_yaml()
    h = OutgoingInvoiceHandler(cfg)
    assert h._cfg["client"]["email"] == "jack.copeland@theglugglejugfactory.com"
    assert "payments-noreply" in str(h._cfg["billing"]["query"])


def test_send_monthly_invoice_passes_dropbox_from_yaml(monkeypatch) -> None:
    """Ensure YAML dropbox path is forwarded (run_month not invoked)."""
    cfg = _gluggle_yaml()
    calls: dict = {}

    def fake_run_month(**kwargs):  # type: ignore[no-untyped-def]
        calls.update(kwargs)
        return object()

    monkeypatch.setattr(
        "invoice_admin.googleads.run_month.run_month",
        fake_run_month,
    )
    h = OutgoingInvoiceHandler(cfg)
    g = object()
    s = object()
    h.send_monthly_invoice(gmail_read_backend=g, smtp_backend=s, dry_run=True)
    assert calls["gmail_read_backend"] is g
    assert calls["smtp_backend"] is s
    assert calls["dry_run"] is True
    assert calls["to_address"] == cfg["email"]["test_recipient"]
    exp_drop = Path(cfg["paths"]["invoice_dir"]).expanduser().resolve()
    assert calls["dropbox_dir"] == exp_drop
    assert calls["billing_query"] == cfg["billing"]["query"]
    assert calls["debugger_address"] == f"127.0.0.1:{cfg['billing']['brave_debug_port']}"
