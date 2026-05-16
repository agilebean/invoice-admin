"""Tests for invoice_admin.core.llm."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from invoice_admin.core.llm import LLMProvider, MODEL_ALIASES, format_llm_cost_report


def test_resolve_model_alias() -> None:
    p = LLMProvider()
    assert p._resolve_model("fast") == MODEL_ALIASES["fast"]
    assert p._resolve_model("anthropic/claude-3-haiku") == "anthropic/claude-3-haiku"


def test_resolve_model_unknown_raises() -> None:
    p = LLMProvider()
    with pytest.raises(ValueError):
        p._resolve_model("not-an-alias")


def test_complete_logs_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    log_db = tmp_path / "llm.sqlite"
    provider = LLMProvider(log_path=log_db)

    fake_usage = SimpleNamespace(prompt_tokens=3, completion_tokens=5)
    fake_choice = SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))
    fake_resp = SimpleNamespace(choices=[fake_choice], usage=fake_usage)

    with patch("agentkit.llm._litellm.litellm.completion", return_value=fake_resp):
        with patch("agentkit.llm._litellm.litellm.completion_cost", return_value=0.01):
            out = provider.complete("hi", model_alias="fast", purpose="general")
    assert out == '{"ok": true}'

    import sqlite3

    conn = sqlite3.connect(str(log_db))
    cur = conn.execute("SELECT success, model FROM llm_calls ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    assert row[0] == 1
    assert row[1] == MODEL_ALIASES["fast"]


def test_complete_logs_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    log_db = tmp_path / "llm.sqlite"
    provider = LLMProvider(log_path=log_db)

    with patch("agentkit.llm._litellm.litellm.completion", side_effect=RuntimeError("boom")):
        with pytest.raises(Exception):
            provider.complete("hi", model_alias="fast")

    import sqlite3

    conn = sqlite3.connect(str(log_db))
    cur = conn.execute("SELECT success, error FROM llm_calls ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    assert row[0] == 0
    assert row[1] is not None


def test_format_llm_cost_report(tmp_path: Path) -> None:
    log_db = tmp_path / "llm.sqlite"
    conn = sqlite3.connect(str(log_db))
    conn.execute(
        """
        CREATE TABLE llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL,
            completion_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            duration_ms INTEGER NOT NULL,
            handler TEXT NOT NULL,
            purpose TEXT NOT NULL,
            success INTEGER NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    fixed = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)
    recent = (fixed - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (fixed - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO llm_calls (model, prompt_tokens, completion_tokens, cost_usd, "
        "duration_ms, handler, purpose, success, error, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("m", 1, 1, 0.12, 1, "h", "classification", 1, None, recent),
    )
    conn.execute(
        "INSERT INTO llm_calls (model, prompt_tokens, completion_tokens, cost_usd, "
        "duration_ms, handler, purpose, success, error, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("m", 1, 1, 0.5, 1, "h", "classification", 1, None, old),
    )
    conn.commit()
    conn.close()

    out = format_llm_cost_report(log_db, now=fixed)
    assert "LLM Cost Report — last 7 days" in out
    assert "classification" in out
    assert "LLM Cost Report — last 30 days" in out
    assert "$0.62" in out
