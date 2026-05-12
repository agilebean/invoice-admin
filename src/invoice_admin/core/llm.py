"""LLM provider abstraction via litellm."""
from __future__ import annotations

import base64
import sqlite3
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import litellm

MODEL_ALIASES: dict[str, str] = {
    "fast": "claude-haiku-4-5",
    "smart": "claude-opus-4-7",
    "cheap": "deepseek/deepseek-chat",
    "local": "ollama/llama3.1:70b",
}


@dataclass
class LLMCallRecord:
    """Logged to llm_calls.sqlite."""

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
                record.model,
                record.prompt_tokens,
                record.completion_tokens,
                record.cost_usd,
                record.duration_ms,
                record.handler,
                record.purpose,
                1 if record.success else 0,
                record.error,
                created,
            ),
        )
        self._log_conn.commit()

    def _resolve_model(self, alias: str) -> str:
        if alias in self._aliases:
            return self._aliases[alias]
        if "/" in alias or alias.startswith("claude") or alias.startswith("gpt"):
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
        """Call LLM, log, return completion text. Raises litellm exceptions on failure."""
        self._init_log()
        t0 = time.perf_counter()
        err: str | None = None
        success = False
        text = ""
        pt, ct = 0, 0
        cost = 0.0
        model: str = model_alias
        try:
            model = self._resolve_model(model_alias)
            messages: list[dict[str, Any]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = litellm.completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            text = str(choice.message.content or "")
            usage = getattr(resp, "usage", None)
            if usage is not None:
                pt = int(getattr(usage, "prompt_tokens", 0) or 0)
                ct = int(getattr(usage, "completion_tokens", 0) or 0)
            try:
                cost = float(litellm.completion_cost(completion_response=resp))
            except Exception:
                cost = 0.0
            success = True
            return text
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self._log_call(
                LLMCallRecord(
                    model=model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    cost_usd=cost,
                    duration_ms=duration_ms,
                    handler=handler,
                    purpose=purpose,
                    success=success,
                    error=err,
                )
            )

    def complete_with_pdf(
        self,
        prompt: str,
        pdf_bytes: bytes,
        model_alias: str = "smart",
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        handler: str = "unknown",
        purpose: str = "pdf_extraction",
    ) -> str:
        """Multimodal completion with a PDF document (Anthropic-style message parts)."""
        self._init_log()
        t0 = time.perf_counter()
        err: str | None = None
        success = False
        text = ""
        pt, ct = 0, 0
        cost = 0.0
        model: str = model_alias
        b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
        doc_part: dict[str, Any] = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64,
            },
        }
        user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}, doc_part]
        try:
            model = self._resolve_model(model_alias)
            messages: list[dict[str, Any]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": user_content})
            resp = litellm.completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            text = str(choice.message.content or "")
            usage = getattr(resp, "usage", None)
            if usage is not None:
                pt = int(getattr(usage, "prompt_tokens", 0) or 0)
                ct = int(getattr(usage, "completion_tokens", 0) or 0)
            try:
                cost = float(litellm.completion_cost(completion_response=resp))
            except Exception:
                cost = 0.0
            success = True
            return text
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self._log_call(
                LLMCallRecord(
                    model=model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    cost_usd=cost,
                    duration_ms=duration_ms,
                    handler=handler,
                    purpose=purpose,
                    success=success,
                    error=err,
                )
            )


def _parse_llm_log_created_at(raw: str) -> datetime:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_llm_cost_report(log_path: Path, *, now: datetime | None = None) -> str:
    """Build LLM cost dashboard text for last 7 and 30 days from llm_calls.sqlite."""
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
            ts = _parse_llm_log_created_at(str(created_at))
        except ValueError:
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
