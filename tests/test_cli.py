"""Tests for invoice_admin.cli."""
from __future__ import annotations

from pathlib import Path

import pytest

from invoice_admin.cli import main


def _write_min_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text("[project]\nname = 't'\n", encoding="utf-8")
    inv = root / "Invoices"
    state = root / "state"
    cfg = f"""dry_run: true
max_auto_amount_eur: 2000
classifier_min_confidence: 0.7
models:
  fast: claude-haiku-4-5
  smart: claude-opus-4-7
  cheap: deepseek/deepseek-chat
  local: ollama/llama3.1:70b
notify:
  ntfy_topic: null
paths:
  invoices_root: {inv}
  tracker_path: {state / "tracker.sqlite"}
  log_path: {state / "log.jsonl"}
  llm_calls_path: {state / "llm.sqlite"}
"""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "default.yaml").write_text(cfg, encoding="utf-8")
    (root / "config" / "handlers").mkdir(parents=True, exist_ok=True)
    (root / "config" / "handlers" / "outgoing_gluggle.yaml").write_text(
        "client:\n  email: test@example.com\n",
        encoding="utf-8",
    )


def test_cli_status_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    code = main(["status"])
    assert code == 0


def test_cli_send_unknown_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    code = main(["send", "--client", "nope"])
    assert code == 2


def test_cli_ingest_email_no_gmail_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``invoice ingest --email`` without Gmail OAuth token returns 2 (auth error)."""
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN", raising=False)
    _write_min_repo(tmp_path)
    from invoice_admin.core.spark_link import spark_deep_link

    url = spark_deep_link("<x@y.com>")
    code = main(["ingest", "--email", url])
    assert code == 2


def test_cli_review_requires_approve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    code = main(["review", "1"])
    assert code == 2


def test_cli_review_approve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from invoice_admin.core.tracker import Tracker

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    db = tmp_path / "state" / "tracker.sqlite"
    with Tracker(db) as t:
        rid = t.insert(
            "file",
            "ref-review",
            status="needs_review",
            invoice_type="needs_review",
            notes='{"original_type":"foyer_claim","original_confidence":0.55}',
        )
    code = main(["review", str(rid), "--approve"])
    assert code == 0
    with Tracker(db) as t:
        row = t.get(rid)
    assert row is not None
    assert row.status == "received"
    assert row.invoice_type == "foyer_claim"
    assert abs((row.classifier_conf or 0) - 0.55) < 1e-6


def test_cli_retry_requires_approve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    assert main(["retry", "1"]) == 2


def test_cli_retry_approve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from invoice_admin.core.tracker import Tracker

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    db = tmp_path / "state" / "tracker.sqlite"
    with Tracker(db) as t:
        rid = t.insert("file", "ref-fail", status="failed", error='{"type":"X"}')
    code = main(["retry", str(rid), "--approve"])
    assert code == 0
    with Tracker(db) as t:
        row = t.get(rid)
    assert row is not None
    assert row.status == "received"
    assert row.error is None


def test_cli_watch_imap_missing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    assert main(["watch", "--source", "imap"]) == 2


def test_cli_ingest_requires_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    assert main(["ingest"]) == 2
