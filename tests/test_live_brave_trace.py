"""Tests for optional live Brave trace dumps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from invoice_admin.googleads.live_brave_trace import (
    live_brave_trace_dir,
    live_brave_trace_enabled,
    maybe_save_live_brave_trace,
    save_live_brave_trace,
)


def test_trace_dir_defaults_to_downloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GOOGLEADS_LIVE_BRAVE_TRACE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert live_brave_trace_dir() == tmp_path / "Downloads"


def test_trace_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    d = tmp_path / "traces"
    monkeypatch.setenv("GOOGLEADS_LIVE_BRAVE_TRACE_DIR", str(d))
    assert live_brave_trace_dir() == d


def test_live_brave_trace_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_LIVE_BRAVE_TRACE", "1")
    assert live_brave_trace_enabled() is True
    monkeypatch.delenv("RUN_LIVE_BRAVE_TRACE", raising=False)
    assert live_brave_trace_enabled() is False


def test_maybe_save_skips_when_trace_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUN_LIVE_BRAVE_TRACE", raising=False)
    d = MagicMock()
    maybe_save_live_brave_trace(d, label="x")
    d.save_screenshot.assert_not_called()


def test_save_live_brave_trace_writes_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GOOGLEADS_LIVE_BRAVE_TRACE_DIR", str(tmp_path))
    drv = MagicMock()
    drv.page_source = "<html></html>"
    html_path, png_path = save_live_brave_trace(drv, label="test_label")
    assert html_path.is_file()
    assert html_path.parent == tmp_path
    assert png_path.parent == tmp_path
    assert png_path.suffix == ".png"
    drv.save_screenshot.assert_called_once()
