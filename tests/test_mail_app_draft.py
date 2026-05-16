"""Tests for Mail.app AppleScript draft helper."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoice_admin.googleads.mail_app_draft import (
    MailAppDraftError,
    _applescript_string_expr,
    build_open_draft_applescript,
    open_mail_app_draft,
)


def test_applescript_string_expr_multiline() -> None:
    assert "return" in _applescript_string_expr("a\nb")
    expr = _applescript_string_expr("a\nb")
    assert '"a"' in expr and '"b"' in expr


def test_build_open_draft_contains_fields(tmp_path: Path) -> None:
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF")
    script = build_open_draft_applescript(
        to_address="t@example.com",
        subject='Subj "x"',
        body="Hi\nJack",
        pdf_path=pdf,
    )
    assert "t@example.com" in script
    assert "Subj \\\"x\\\"" in script


def test_open_mail_app_draft_non_macos() -> None:
    with patch.object(sys, "platform", "linux"):
        with pytest.raises(MailAppDraftError, match="macOS"):
            open_mail_app_draft(
                to_address="a@b.com",
                subject="s",
                body="b",
                pdf_path=Path("/nope"),
                attachment_name="x.pdf",
            )


@patch("invoice_admin.googleads.mail_app_draft.subprocess.run")
@patch.object(sys, "platform", "darwin")
def test_open_mail_app_draft_runs_osascript(
    mock_run: MagicMock, tmp_path: Path
) -> None:
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF")
    mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
    open_mail_app_draft(
        to_address="a@b.com",
        subject="s",
        body="line\n",
        pdf_path=pdf,
        attachment_name="inv.pdf",
    )
    mock_run.assert_called_once()
    args, _kwargs = mock_run.call_args
    assert args[0][0] == "osascript"
    assert "-e" in args[0]
