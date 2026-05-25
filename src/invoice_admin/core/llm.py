"""LLM provider abstraction — delegates to agentkit.llm, keeps per-project logging."""
from __future__ import annotations

import os
import sqlite3
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agentkit.llm import (
    DEFAULT_MODEL_ALIASES,
    complete as _agentkit_complete,
    response_cost_usd,
    resolve_model,
)

from invoice_admin.core.errors import ExtractionError

MODEL_ALIASES: dict[str, str] = dict(DEFAULT_MODEL_ALIASES)

_LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")


@dataclass
class LLMCallRecord:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_ms: int
    handler: str
    purpose: str
    success: bool
    error: str | None


_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
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
);
"""


class LLMProvider:
    """Single entry point for all LLM calls. Logs every call."""

    def __init__(
        self,
        alias_map: dict[str, str] | None = None,
        log_path: Path | None = None,
    ) -> None:
        self._aliases = dict(alias_map or MODEL_ALIASES)
        self._log_path = log_path
        self._log_conn: sqlite3.Connection | None = None

    def _init_log(self) -> None:
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        if self._log_conn is None:
            self._log_conn = sqlite3.connect(str(self._log_path))
        self._log_conn.execute(_LOG_SCHEMA)
        self._log_conn.commit()

    def _log_call(self, record: LLMCallRecord) -> None:
        if self._log_path is None or self._log_conn is None:
            return
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._log_conn.execute(
            """
            INSERT INTO llm_calls (
                model, prompt_tokens, completion_tokens, cost_usd, duration_ms,
                handler, purpose, success, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.model, record.prompt_tokens, record.completion_tokens,
                record.cost_usd, record.duration_ms,
                record.handler, record.purpose,
                1 if record.success else 0, record.error, created,
            ),
        )
        self._log_conn.commit()

    def _resolve_model(self, alias: str) -> str:
        if alias == "local":
            return os.environ.get("LM_STUDIO_MODEL", _LM_STUDIO_BASE_URL.split("//")[1] or "local-model")
        if alias in self._aliases:
            return self._aliases[alias]
        if "/" in alias:
            return alias
        raise ValueError(f"Unknown model alias: {alias!r}")

    def complete(
        self,
        prompt: str,
        model_alias: str = "fast",
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        handler: str = "unknown",
        purpose: str = "general",
    ) -> str:
        self._init_log()
        t0 = time.perf_counter()
        err: str | None = None
        text = ""
        model = model_alias
        record_data: dict[str, Any] = {}

        def _log_fn(log_rec: dict[str, Any]) -> None:
            nonlocal record_data
            record_data = log_rec

        try:
            messages: list[dict[str, Any]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            text = _agentkit_complete(
                messages,
                alias=model_alias,
                max_tokens=max_tokens,
                temperature=temperature,
                aliases=self._aliases,
                log_fn=_log_fn,
            )
            model = record_data.get("model", model_alias)
            return text
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self._log_call(
                LLMCallRecord(
                    model=model,
                    prompt_tokens=record_data.get("input_tokens", 0),
                    completion_tokens=record_data.get("output_tokens", 0),
                    cost_usd=record_data.get("cost_usd", 0.0),
                    duration_ms=duration_ms,
                    handler=handler,
                    purpose=purpose,
                    success=err is None,
                    error=err,
                )
            )

    def complete_with_pdf(
        self,
        prompt: str,
        pdf_bytes: bytes,
        model_alias: str = "fast",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        handler: str = "unknown",
        purpose: str = "general",
    ) -> str:
        import base64

        self._init_log()
        t0 = time.perf_counter()
        err: str | None = None
        text = ""
        model = model_alias
        record_data: dict[str, Any] = {}

        def _log_fn(log_rec: dict[str, Any]) -> None:
            nonlocal record_data
            record_data = log_rec

        try:
            b64 = base64.b64encode(pdf_bytes).decode("ascii")
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:application/pdf;base64,{b64}"},
                        },
                    ],
                }
            ]
            text = _agentkit_complete(
                messages,
                alias=model_alias,
                max_tokens=max_tokens,
                temperature=temperature,
                aliases=self._aliases,
                log_fn=_log_fn,
            )
            model = record_data.get("model", model_alias)
            return text
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self._log_call(
                LLMCallRecord(
                    model=model,
                    prompt_tokens=record_data.get("input_tokens", 0),
                    completion_tokens=record_data.get("output_tokens", 0),
                    cost_usd=record_data.get("cost_usd", 0.0),
                    duration_ms=duration_ms,
                    handler=handler,
                    purpose=purpose,
                    success=err is None,
                    error=err,
                )
            )


def format_llm_cost_report(log_path: Path, *, now: datetime | None = None) -> str:
    """Build LLM cost dashboard text for last 7 and 30 days from llm_calls.sqlite."""
    from datetime import datetime, timedelta, timezone

    if not log_path.is_file():
        return f"No LLM call log found at {log_path}\n"
    conn = sqlite3.connect(str(log_path))
    try:
        cur = conn.execute(
            "SELECT purpose, cost_usd, created_at FROM llm_calls ORDER BY id",
        )
        rows_raw = cur.fetchall()
    finally:
        conn.close()

    parsed: list[tuple[str, float, datetime]] = []
    for purpose, cost_usd, created_at in rows_raw:
        try:
            ts_str = str(created_at)
            ts = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            continue
        try:
            cost = float(cost_usd or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        parsed.append((str(purpose), cost, ts))

    lines_out: list[str] = []
    ref = now or datetime.now(timezone.utc)
    for window in (7, 30):
        lines_out.append(f"LLM Cost Report — last {window} days")
        cutoff = ref - timedelta(days=window)
        by_purpose: dict[str, tuple[int, float]] = {}
        for purpose, cost, ts in parsed:
            if ts < cutoff:
                continue
            n, total = by_purpose.get(purpose, (0, 0.0))
            by_purpose[purpose] = (n + 1, total + cost)
        if not by_purpose:
            lines_out.append("  (no calls)")
            lines_out.append("")
            continue
        for purpose in sorted(by_purpose):
            n, total = by_purpose[purpose]
            label = f"{purpose}:"
            lines_out.append(f"  {label:<18} {n:>3} calls, ${total:.2f}")
        tot_n = sum(v[0] for v in by_purpose.values())
        tot_c = sum(v[1] for v in by_purpose.values())
        lines_out.append(f"  {'Total:':<18} {tot_n:>3} calls, ${tot_c:.2f}")
        lines_out.append("")
    return "\n".join(lines_out).rstrip() + "\n"
