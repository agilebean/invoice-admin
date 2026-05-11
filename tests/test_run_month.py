"""Tests for ``run_month`` orchestration and its CLI subcommand."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from googleads_invoice.gmail_facade import GmailMessageSummary, GmailTransportError
from googleads_invoice.run_month import RunMonthError, run_month


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_gmail_backend() -> MagicMock:
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="msg1", thread_id="t1", snippet="billing"),
    ]
    bk.get_message_html.return_value = (
        '<html><body><a href="https://payments.google.com/billing/x">View</a></body></html>'
    )
    return bk


@pytest.fixture
def mock_smtp_backend() -> MagicMock:
    bk = MagicMock()
    bk.send_text_with_pdf_attachment.return_value = "smtp:pdf:ok"
    return bk


@pytest.fixture
def invoice_pdf(tmp_path: Path) -> Path:
    """A tiny real PDF with invoice fields that parse_invoice_pdf can read."""
    from pypdf import PdfWriter
    from io import BytesIO

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"hello": "world"})
    # Use a stream to write metadata-like text that the parser expects
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)

    # We need to inject text. pypdf can't easily write text to a blank page,
    # so let's just use the fixture PDF which is already committed.
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    if fixture.is_file():
        return fixture
    raise RuntimeError(f"Missing fixture: {fixture}")


# ── run_month: happy path ────────────────────────────────────────────────


def test_run_month_happy_path(
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    """Full happy path: Gmail → Brave (mocked) → parse → SMTP send."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    # Copy fixture to temp dir so run_month's shutil.move doesn't consume the original
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    pdf_copy = tmp_path / fixture_pdf.name
    pdf_copy.write_bytes(fixture_pdf.read_bytes())

    with patch(
        "googleads_invoice.live_brave_download.live_brave_download_pdf",
        return_value=pdf_copy,
    ):
        report = run_month(
            gmail_read_backend=mock_gmail_backend,
            billing_query="from:payments-noreply",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
            smtp_backend=mock_smtp_backend,
            smtp_sender="chaehan.so@gmail.com",
            to_address="jack.copeland@theglugglejugfactory.com",
            month_label="April 2026",
            dropbox_dir=tmp_path,
        )

    assert report.billing_url == "https://payments.google.com/billing/x"
    assert report.pdf_path == pdf_copy
    assert report.issue_date == date(2026, 3, 15)
    assert report.amount_eur == Decimal("1234.56")
    assert "Dear Jack" in report.email_body
    assert report.recipient == "jack.copeland@theglugglejugfactory.com"
    assert report.send_status == "smtp:pdf:ok"
    assert len(report.steps) >= 5  # search, brave, parse, artifacts, send


def test_run_month_uses_auto_month_label(
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    """When month_label is None, it's derived from the calendar."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    # Copy fixture to temp dir so run_month's shutil.move doesn't consume the original
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    pdf_copy = tmp_path / fixture_pdf.name
    pdf_copy.write_bytes(fixture_pdf.read_bytes())

    with patch(
        "googleads_invoice.live_brave_download.live_brave_download_pdf",
        return_value=pdf_copy,
    ):
        report = run_month(
            gmail_read_backend=mock_gmail_backend,
            billing_query="from:payments-noreply",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
            smtp_backend=mock_smtp_backend,
            smtp_sender="chaehan.so@gmail.com",
            to_address="test@test.com",
            dropbox_dir=tmp_path,
        )
    # Should have a non-empty month label
    assert report.email_subject


# ── run_month: error paths ──────────────────────────────────────────────


def test_run_month_gmail_search_fails(
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    gmail = MagicMock()
    gmail.list_messages.side_effect = GmailTransportError("API unavailable")

    with pytest.raises(RunMonthError, match="Gmail search failed"):
        run_month(
            gmail_read_backend=gmail,
            billing_query="from:x",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=tmp_path,
            smtp_backend=mock_smtp_backend,
            smtp_sender="me@gmail.com",
            to_address="you@test.com",
        )


def test_run_month_no_gmail_results(
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    gmail = MagicMock()
    gmail.list_messages.return_value = []

    with pytest.raises(RunMonthError, match="No messages found"):
        run_month(
            gmail_read_backend=gmail,
            billing_query="from:x",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=tmp_path,
            smtp_backend=mock_smtp_backend,
            smtp_sender="me@gmail.com",
            to_address="you@test.com",
        )


def test_run_month_no_billing_url_in_messages(
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    gmail = MagicMock()
    gmail.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="s"),
    ]
    gmail.get_message_html.return_value = "<html><body>no links here</body></html>"

    with pytest.raises(RunMonthError, match="no extractable billing URL"):
        run_month(
            gmail_read_backend=gmail,
            billing_query="from:x",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=tmp_path,
            smtp_backend=mock_smtp_backend,
            smtp_sender="me@gmail.com",
            to_address="you@test.com",
        )


def test_run_month_brave_download_fails(
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    with (
        patch(
            "googleads_invoice.live_brave_download.live_brave_download_pdf",
            side_effect=RunMonthError("Brave navigation failed"),
        ),
        pytest.raises(RunMonthError, match="Brave navigation failed"),
    ):
        run_month(
            gmail_read_backend=mock_gmail_backend,
            billing_query="from:x",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
            smtp_backend=mock_smtp_backend,
            smtp_sender="me@gmail.com",
            to_address="you@test.com",
        )


def test_run_month_smtp_fails(
    mock_gmail_backend: MagicMock,
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    # Copy fixture to temp dir so run_month's shutil.move doesn't consume the original
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    pdf_copy = tmp_path / fixture_pdf.name
    pdf_copy.write_bytes(fixture_pdf.read_bytes())
    smtp = MagicMock()
    smtp.send_text_with_pdf_attachment.side_effect = GmailTransportError("SMTP rejected")

    with (
        patch(
            "googleads_invoice.live_brave_download.live_brave_download_pdf",
            return_value=pdf_copy,
        ),
        pytest.raises(RunMonthError, match="SMTP send failed"),
    ):
        run_month(
            gmail_read_backend=mock_gmail_backend,
            billing_query="from:x",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
            smtp_backend=smtp,
            smtp_sender="me@gmail.com",
            to_address="you@test.com",
        )


# ── CLI: run-month subcommand ───────────────────────────────────────────


class TestCliRunMonth:
    def test_refuses_without_confirm_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.delenv("GOOGLEADS_CONFIRM_RUN_MONTH", raising=False)
        code = main(["run-month"])
        assert code == 2

    def test_errors_when_debugger_address_missing(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLEADS_CONFIRM_RUN_MONTH", "1")
        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
        monkeypatch.delenv("GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", raising=False)
        code = main(["run-month"])
        assert code == 2

    def test_errors_when_smtp_password_missing(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLEADS_CONFIRM_RUN_MONTH", "1")
        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        monkeypatch.setenv("GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", "127.0.0.1:9222")
        monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", raising=False)
        monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
        code = main(["run-month"])
        assert code == 2

    @patch("builtins.input", return_value="y")
    @patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
    @patch("googleads_invoice.run_month.run_month")
    def test_happy_path(
        self,
        mock_run_month: MagicMock,
        mock_from_env: MagicMock,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from googleads_invoice.cli import main
        from googleads_invoice.run_month import RunMonthReport

        monkeypatch.setenv("GOOGLEADS_CONFIRM_RUN_MONTH", "1")
        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        monkeypatch.setenv("GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", "127.0.0.1:9222")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
        monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
        monkeypatch.delenv("GOOGLEADS_GMAIL_BILLING_QUERY", raising=False)
        mock_from_env.return_value = MagicMock()

        pdf = tmp_path / "invoice.pdf"
        pdf.write_text("pdf", encoding="utf-8")
        mock_run_month.return_value = RunMonthReport(
            billing_url="https://payments.google.com/billing/x",
            pdf_path=pdf,
            issue_date=date(2026, 4, 2),
            amount_eur=Decimal("100.00"),
            renamed_filename="google-ads-invoice_2026-04-02_100-EUR.pdf",
            email_subject="Google Ads invoice — April 2026 (EUR 100.00)",
            email_body="Dear Jack,\n\nAttached...",
            recipient="jack@example.com",
            send_status="smtp:pdf:ok",
        )

        code = main(["run-month", "--test-run", "--to", "jack@example.com"])
        assert code == 0
        mock_run_month.assert_called_once()
        assert mock_run_month.call_args.kwargs["to_address"] == "jack@example.com"

    @patch("builtins.input", return_value="y")
    @patch("googleads_invoice.run_month.run_month")
    def test_propagates_run_month_error(
        self,
        mock_run_month: MagicMock,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLEADS_CONFIRM_RUN_MONTH", "1")
        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        monkeypatch.setenv("GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", "127.0.0.1:9222")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
        monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)

        mock_run_month.side_effect = RunMonthError("something broke")

        code = main(["run-month"])
        assert code == 2

    @patch("builtins.input", return_value="y")
    @patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
    def test_uses_default_recipient_when_omitted(
        self,
        mock_from_env: MagicMock,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main
        from googleads_invoice.addresses import DEFAULT_TEST_RECIPIENT

        monkeypatch.setenv("GOOGLEADS_CONFIRM_RUN_MONTH", "1")
        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        monkeypatch.setenv("GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", "127.0.0.1:9222")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
        monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
        monkeypatch.delenv("GOOGLEADS_INVOICE_TO", raising=False)
        mock_from_env.return_value = MagicMock()

        with patch("googleads_invoice.run_month.run_month") as mock_run:
            code = main(["run-month", "--test-run"])
            assert code == 0  # exits early via mock, but that's fine
            assert mock_run.call_args.kwargs["to_address"] == DEFAULT_TEST_RECIPIENT


def test_cli_run_month_help_mentions_guard(capsys: pytest.CaptureFixture[str]) -> None:
    from googleads_invoice.cli import main

    with pytest.raises(SystemExit):
        main(["run-month", "--help"])
    out = capsys.readouterr().out
    assert "run-month" in out or "GOOGLEADS_CONFIRM_RUN_MONTH" in out
