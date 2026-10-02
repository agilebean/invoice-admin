"""Tests for ``run_month`` orchestration and its CLI subcommand."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from invoice_admin.googleads.gmail_facade import GmailMessageSummary, GmailTransportError
from invoice_admin.googleads.run_month import (
    RunMonthError,
    find_downloaded_invoice,
    run_month,
)

_BRAVE_PATCH = patch("invoice_admin.googleads.browser_download.ensure_brave_running")

_FIXTURE_PDF = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pdf"
    / "invoice_eur_dot_decimal.pdf"
)  # issue date 2026-03-15, EUR 1234.56
_FIXTURE_PDF_NEXT_MONTH_ISSUE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pdf"
    / "invoice_eur_comma_decimal.pdf"
)  # issue date 2026-04-01, EUR 1234.56


def _write_saved_invoice(
    directory: Path,
    name: str,
    *,
    source: Path = _FIXTURE_PDF,
) -> Path:
    """Write a parseable invoice PDF under the saved-filename convention."""
    p = directory / name
    p.write_bytes(source.read_bytes())
    return p


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


# ── find_downloaded_invoice (reuse of a previous dry-run download) ──────


class TestFindDownloadedInvoice:
    def test_finds_matching_month_and_parses_fields(self, tmp_path: Path) -> None:
        saved = _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        found = find_downloaded_invoice(
            tmp_path, client_prefix="Glugglejug", month_label="March 2026"
        )
        assert found is not None
        path, issue_date, amount = found
        assert path == saved
        assert issue_date == date(2026, 3, 15)
        assert amount == Decimal("1234.56")

    def test_accepts_issue_date_in_following_calendar_month(self, tmp_path: Path) -> None:
        """Google issues the invoice at month end or in the first days after it."""
        _write_saved_invoice(
            tmp_path,
            "2026-04-01 Glugglejug GoogleAds Invoice March €1,234.56.pdf",
            source=_FIXTURE_PDF_NEXT_MONTH_ISSUE,
        )
        assert (
            find_downloaded_invoice(
                tmp_path, client_prefix="Glugglejug", month_label="March 2026"
            )
            is not None
        )

    def test_rejects_other_month_name(self, tmp_path: Path) -> None:
        _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        assert (
            find_downloaded_invoice(
                tmp_path, client_prefix="Glugglejug", month_label="April 2026"
            )
            is None
        )

    def test_rejects_same_month_name_from_an_earlier_year(self, tmp_path: Path) -> None:
        """A March 2026 file must not satisfy a March 2025 billing month."""
        _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        assert (
            find_downloaded_invoice(
                tmp_path, client_prefix="Glugglejug", month_label="March 2025"
            )
            is None
        )

    def test_rejects_other_client_prefix(self, tmp_path: Path) -> None:
        _write_saved_invoice(
            tmp_path, "2026-03-15 OtherClient GoogleAds Invoice March €1,234.56.pdf"
        )
        assert (
            find_downloaded_invoice(
                tmp_path, client_prefix="Glugglejug", month_label="March 2026"
            )
            is None
        )

    def test_accepts_yyyy_mm_month_label(self, tmp_path: Path) -> None:
        _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        assert (
            find_downloaded_invoice(
                tmp_path, client_prefix="Glugglejug", month_label="2026-03"
            )
            is not None
        )

    def test_picks_newest_of_same_month_duplicates(self, tmp_path: Path) -> None:
        import os
        import time

        first = _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        newest = _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56 (1).pdf"
        )
        now = time.time()
        os.utime(first, (now - 10, now - 10))
        os.utime(newest, (now - 5, now - 5))
        found = find_downloaded_invoice(
            tmp_path, client_prefix="Glugglejug", month_label="March 2026"
        )
        assert found is not None
        assert found[0] == newest

    def test_skips_unreadable_candidate(self, tmp_path: Path) -> None:
        import os
        import time

        saved = _write_saved_invoice(
            tmp_path, "2026-03-10 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        broken = tmp_path / "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        broken.write_bytes(b"not a pdf")
        now = time.time()
        os.utime(saved, (now - 10, now - 10))
        os.utime(broken, (now - 5, now - 5))
        found = find_downloaded_invoice(
            tmp_path, client_prefix="Glugglejug", month_label="March 2026"
        )
        assert found is not None
        assert found[0] == saved

    def test_missing_directory_returns_none(self, tmp_path: Path) -> None:
        assert (
            find_downloaded_invoice(
                tmp_path / "nope", client_prefix="Glugglejug", month_label="March 2026"
            )
            is None
        )

    def test_unparseable_label_returns_none(self, tmp_path: Path) -> None:
        _write_saved_invoice(
            tmp_path, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
        )
        assert (
            find_downloaded_invoice(
                tmp_path, client_prefix="Glugglejug", month_label="whenever"
            )
            is None
        )


# ── run_month: reuse of an already-downloaded invoice ───────────────────


@_BRAVE_PATCH
def test_run_month_dry_run_saves_for_later_reuse(
    _mock_brave: MagicMock,
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    """The n-answer dry run saves the renamed PDF where the next y run reuses it."""
    dest = tmp_path / "drive"
    dest.mkdir()
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    staged = _write_saved_invoice(
        download_dir, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
    )

    with patch(
        "invoice_admin.googleads.live_brave_download.live_brave_download_pdf",
        return_value=staged,
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
            month_label="March 2026",
            dropbox_dir=dest,
            client_prefix="Glugglejug",
            dry_run=True,
        )

    mock_smtp_backend.send_text_with_pdf_attachment.assert_not_called()
    saved = dest / staged.name
    assert saved.is_file()
    assert not staged.exists()
    assert report.dropbox_path == saved
    found = find_downloaded_invoice(
        dest, client_prefix="Glugglejug", month_label="March 2026"
    )
    assert found is not None
    assert found[0] == saved


@_BRAVE_PATCH
def test_run_month_reuse_skips_gmail_and_download(
    _mock_brave: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    """reuse_downloaded=True sends the saved PDF without Gmail or Brave."""
    dest = tmp_path / "drive"
    dest.mkdir()
    saved = _write_saved_invoice(
        dest, "2026-03-15 Glugglejug GoogleAds Invoice March €1,234.56.pdf"
    )
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    gmail = MagicMock()

    with patch(
        "invoice_admin.googleads.live_brave_download.live_brave_download_pdf"
    ) as mock_download:
        report = run_month(
            gmail_read_backend=gmail,
            billing_query="from:payments-noreply",
            max_scan=5,
            debugger_address="127.0.0.1:9222",
            download_dir=download_dir,
            smtp_backend=mock_smtp_backend,
            smtp_sender="chaehan.so@gmail.com",
            to_address="jack.copeland@theglugglejugfactory.com",
            month_label="March 2026",
            dropbox_dir=dest,
            client_prefix="Glugglejug",
            reuse_downloaded=True,
        )

    gmail.list_messages.assert_not_called()
    mock_download.assert_not_called()
    mock_smtp_backend.send_text_with_pdf_attachment.assert_called_once()
    send_kwargs = mock_smtp_backend.send_text_with_pdf_attachment.call_args.kwargs
    assert send_kwargs["pdf_path"] == saved
    assert send_kwargs["attachment_name"] == saved.name
    assert report.pdf_path == saved
    assert report.dropbox_path == saved
    assert report.billing_url == ""
    assert report.send_status == "smtp:pdf:ok"
    assert any("Reused" in step for step in report.steps)
    # The reused file stays put: no duplicate and no rename.
    assert sorted(dest.glob("*.pdf")) == [saved]


@_BRAVE_PATCH
def test_run_month_reuse_falls_back_to_download_when_none_saved(
    _mock_brave: MagicMock,
    mock_gmail_backend: MagicMock,
    mock_smtp_backend: MagicMock,
    tmp_path: Path,
) -> None:
    """With no saved invoice for the month, the normal Gmail + Brave flow runs."""
    dest = tmp_path / "drive"
    dest.mkdir()
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    pdf_copy = tmp_path / _FIXTURE_PDF.name
    pdf_copy.write_bytes(_FIXTURE_PDF.read_bytes())

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
            month_label="March 2026",
            dropbox_dir=dest,
            client_prefix="Glugglejug",
            reuse_downloaded=True,
        )

    mock_download.assert_called_once()
    mock_gmail_backend.list_messages.assert_called_once()
    assert report.billing_url == "https://payments.google.com/billing/x"
    assert report.pdf_path == pdf_copy
    assert (dest / pdf_copy.name).is_file()
