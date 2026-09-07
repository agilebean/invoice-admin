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
        f"""client:
  key: glugglejug
  aliases: ["gluggle"]
  name: Gluggle Jug
  email: jack@example.com
  file_prefix: Glugglejug
email:
  sender: me@example.com
  test_recipient: me-test@example.com
commission:
  provider: googleads
  rate: 0.03
  sender_email: jack@example.com
  query: from:jack@example.com commission
billing:
  query: from:payments-noreply@google.com billing
  brave_debug_port: 9222
paths:
  invoice_dir: "{root / "GluggleJug GoogleAds"}"
  commission_dir: "{root / "GluggleJug Commissions"}"
""",
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
    code = main(["send", "--client", "nope", "--dry-run"])
    assert code == 2


def test_cli_send_default_client_when_single(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare ``invoice send --dry-run`` resolves the only configured client."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch.object(OutgoingInvoiceHandler, "send_monthly_invoice") as mock_send:
        code = main(["send", "--dry-run"])
    assert code == 0
    kwargs = mock_send.call_args.kwargs
    assert kwargs["dry_run"] is True


def test_cli_send_client_alias_gluggle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--client gluggle`` resolves to the canonical ``glugglejug``."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch.object(OutgoingInvoiceHandler, "send_monthly_invoice") as mock_send:
        code = main(["send", "--client", "gluggle", "--dry-run"])
    assert code == 0
    mock_send.assert_called_once()


def test_cli_send_dry_run_needs_no_smtp_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--dry-run`` must not require an SMTP app password."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", raising=False)
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch.object(OutgoingInvoiceHandler, "send_monthly_invoice") as mock_send:
        code = main(["send", "--dry-run"])
    assert code == 0
    mock_send.assert_called_once()


def test_cli_send_requires_smtp_password_for_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production send without an SMTP app password refuses with code 2."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", raising=False)
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch("builtins.input") as mock_input:
        code = main(["send", "--yes"])
    assert code == 2
    mock_input.assert_not_called()


def test_cli_send_yes_skips_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--yes`` sends production without asking for confirmation."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "pw")
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with (
        patch.object(OutgoingInvoiceHandler, "send_monthly_invoice") as mock_send,
        patch("builtins.input") as mock_input,
    ):
        code = main(["send", "--yes"])
    assert code == 0
    mock_input.assert_not_called()
    assert mock_send.call_args.kwargs["dry_run"] is False


def test_cli_send_prompt_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production send aborts (code 2) when the user answers no."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "pw")
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch("builtins.input", return_value="n"):
        code = main(["send"])
    assert code == 2


def test_cli_send_prompt_confirms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production send runs when the user confirms."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "pw")
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with (
        patch.object(OutgoingInvoiceHandler, "send_monthly_invoice") as mock_send,
        patch("builtins.input", return_value="y"),
    ):
        code = main(["send"])
    assert code == 0
    assert mock_send.call_args.kwargs["dry_run"] is False


def test_cli_save_default_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare ``invoice save --dry-run`` resolves the only provider flow."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch.object(OutgoingInvoiceHandler, "save_commission") as mock_save:
        code = main(["save", "--dry-run"])
    assert code == 0
    assert mock_save.call_args.kwargs["dry_run"] is True


def test_cli_save_unknown_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    code = main(["save", "--provider", "metaads", "--dry-run"])
    assert code == 2
    err = capsys.readouterr().err
    assert "googleads" in err


def test_cli_save_destination_line_points_at_commissions_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The confirmation must print the commissions folder, never the invoice folder."""
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with (
        patch(
            "invoice_admin.handlers.outgoing_invoice.OutgoingInvoiceHandler.save_commission",
            return_value=MagicMock(),
        ),
        patch("builtins.input", return_value="y"),
    ):
        code = main(["save"])
    assert code == 0
    err = capsys.readouterr().err
    assert "GluggleJug Commissions" in err
    assert "GluggleJug GoogleAds" not in err


def test_cli_save_abort_on_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch("builtins.input", return_value="n"):
        code = main(["save"])
    assert code == 2


def test_cli_save_dry_run_skips_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with (
        patch.object(OutgoingInvoiceHandler, "save_commission") as mock_save,
        patch("builtins.input") as mock_input,
    ):
        code = main(["save", "--dry-run"])
    assert code == 0
    mock_input.assert_not_called()
    assert mock_save.call_args.kwargs["dry_run"] is True


def test_cli_save_month_targets_subject_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--month YYYY-MM`` narrows the Gmail query and pins the expected month."""
    from datetime import date
    from unittest.mock import MagicMock, patch

    from invoice_admin.googleads.gmail_api_backend import GmailApiReadBackend
    from invoice_admin.handlers.outgoing_invoice import OutgoingInvoiceHandler

    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    monkeypatch.setattr(
        GmailApiReadBackend, "from_env", classmethod(lambda cls: MagicMock())
    )
    with patch.object(OutgoingInvoiceHandler, "save_commission") as mock_save:
        code = main(["save", "--month", "2026-07", "--dry-run"])
    assert code == 0
    kwargs = mock_save.call_args.kwargs
    assert kwargs["expected_month"] == date(2026, 7, 1)
    assert 'subject:"July"' in kwargs["commission_query"]


def test_cli_save_invalid_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INVOICE_ADMIN_REPO_ROOT", str(tmp_path))
    _write_min_repo(tmp_path)
    assert main(["save", "--month", "2026-13", "--dry-run"]) == 2
    assert main(["save", "--month", "july", "--dry-run"]) == 2


def test_cli_googleads_passthrough_removed() -> None:
    """The ``invoice googleads`` namespace no longer exists."""
    with pytest.raises(SystemExit):
        main(["googleads"])


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
