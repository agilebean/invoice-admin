"""complete_with_pdf must route through agentkit.complete (auth + logging)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from invoice_admin.core.llm import LLMProvider


def test_complete_with_pdf_uses_agentkit_and_logs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")

    class _U:
        prompt_tokens = 7
        completion_tokens = 3
        total_tokens = 10

    class _Msg:
        content = "PDF-OK"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = _U()

    captured: dict[str, Any] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr("agentkit.llm._litellm._post_completion", fake_completion)
    monkeypatch.setattr(
        "agentkit.llm._litellm._estimate_cost", lambda *a, **_: 0.002
    )

    log = tmp_path / "llm_calls.sqlite"
    provider = LLMProvider(log_path=log)
    out = provider.complete_with_pdf(
        "extract", b"%PDF-1.4 fake", model_alias="smart", handler="t", purpose="p"
    )

    assert out == "PDF-OK"
    # routed through agentkit -> the multimodal message reached the HTTP transport
    assert isinstance(captured.get("messages"), list)
    # logged a row with the captured cost
    row = sqlite3.connect(str(log)).execute(
        "SELECT cost_usd, handler, purpose FROM llm_calls"
    ).fetchone()
    assert row == (0.002, "t", "p")
