"""Tests for ``run_month`` orchestration and its CLI subcommand."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoice_admin.googleads.gmail_facade import GmailMessageSummary, GmailTransportError
from invoice_admin.googleads.run_month import RunMonthError, run_month

_BRAVE_PATCH = patch("invoice_admin.googleads.browser_download.ensure_brave_running")

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


@_BRAVE_PATCH
def test_run_month_happy_path(
    _mock_brave: MagicMock,
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
        "invoice_admin.googleads.live_brave_download.live_brave_download_pdf",
        return_value=pdf_copy,
    ) as mock_download:
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
    # Inner download steps must stay visible so the flow never appears to hang.
    assert mock_download.call_args.kwargs["verbose"] is True


@_BRAVE_PATCH
def test_run_month_uses_auto_month_label(
    _mock_brave: MagicMock,
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
        "invoice_admin.googleads.live_brave_download.live_brave_download_pdf",
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


@_BRAVE_PATCH
def test_run_month_brave_launch_timeout_allows_cold_start(
    _mock_brave: MagicMock,
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    """Brave cold start can exceed 7s; run_month must wait much longer."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    pdf_copy = tmp_path / fixture_pdf.name
    pdf_copy.write_bytes(fixture_pdf.read_bytes())

    with patch(
        "invoice_admin.googleads.live_brave_download.live_brave_download_pdf",
        return_value=pdf_copy,
    ):
        run_month(
            gmail_read_backend=mock_gmail_backend,
            billing_query="from:payments-noreply",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
            smtp_backend=mock_smtp_backend,
            smtp_sender="me@gmail.com",
            to_address="you@test.com",
            month_label="April 2026",
            dropbox_dir=tmp_path,
        )
    _mock_brave.assert_called_once_with(
        "127.0.0.1:9222", launch_timeout_s=11.0
    )


@_BRAVE_PATCH
def test_run_month_gmail_search_fails(
    _mock_brave: MagicMock,
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


@_BRAVE_PATCH
def test_run_month_no_gmail_results(
    _mock_brave: MagicMock,
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


@_BRAVE_PATCH
def test_run_month_no_billing_url_in_messages(
    _mock_brave: MagicMock,
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


@_BRAVE_PATCH
def test_run_month_brave_download_fails(
    _mock_brave: MagicMock,
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    with (
        patch(
            "invoice_admin.googleads.live_brave_download.live_brave_download_pdf",
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


@_BRAVE_PATCH
def test_run_month_smtp_fails(
    _mock_brave: MagicMock,
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
            "invoice_admin.googleads.live_brave_download.live_brave_download_pdf",
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
