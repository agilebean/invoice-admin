"""Tests for ``save_commission_pdf`` orchestration and its CLI subcommand."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from googleads_invoice.gmail_facade import GmailMessageSummary
from googleads_invoice.save_commission_pdf import SaveCommissionPdfError, save_commission_pdf


@pytest.fixture
def mock_gmail_backend() -> MagicMock:
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="msg1", thread_id="t1", snippet="commission"),
    ]
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    bk.get_message_pdf_with_metadata.return_value = (
        fixture_pdf.read_bytes(),
        "Invoice March Commission (EUR)",
        1772323200000,  # 2026-03-01 00:00 UTC
    )
    return bk


def test_save_commission_pdf_happy_path(
    mock_gmail_backend: MagicMock,
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    commission_out = tmp_path / "Commissions"
    downloads.mkdir(parents=True)
    commission_out.mkdir(parents=True)

    report = save_commission_pdf(
        gmail_read_backend=mock_gmail_backend,
        commission_query="from:jack.copeland@theglugglejugfactory.com commission",
        max_scan=10,
        commission_dir=commission_out,
        downloads_dir=downloads,
    )

    assert report.message_id == "msg1"
    assert report.commission_date == date(2026, 3, 1)
    assert report.amount_eur == Decimal("1234.56")
    assert report.renamed_filename == "2026-03 Commission March €1,234.56.pdf"
    assert "March" in report.renamed_filename
    assert "Commission" in report.renamed_filename
    assert report.renamed_filename.startswith("2026-03")
    assert "€1,234.56" in report.renamed_filename
    assert report.renamed_filename.endswith(".pdf")
    assert report.pdf_path.is_file()
    assert report.pdf_path.parent == commission_out
    assert report.pdf_path.name == report.renamed_filename
    assert not list(downloads.glob("Commission download*.pdf"))


def test_save_commission_pdf_test_run_writes_under_downloads(
    mock_gmail_backend: MagicMock,
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True)
    report = save_commission_pdf(
        gmail_read_backend=mock_gmail_backend,
        commission_query="from:jack commission",
        test_run=True,
        downloads_dir=downloads,
        commission_dir=tmp_path / "Ignored",
    )
    assert report.pdf_path.is_file()
    assert report.pdf_path.parent == downloads


def test_save_commission_pdf_no_emails(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True)
    bk = MagicMock()
    bk.list_messages.return_value = []
    with pytest.raises(SaveCommissionPdfError, match="No commission emails"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
            downloads_dir=downloads,
        )


def test_save_commission_pdf_no_attachment(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True)
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="commission"),
        GmailMessageSummary(id="m2", thread_id="t2", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.return_value = None
    with pytest.raises(SaveCommissionPdfError, match="No PDF attachment"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
            downloads_dir=downloads,
        )


def test_save_commission_pdf_skips_non_attachment_emails(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    commission_out = tmp_path / "out"
    downloads.mkdir(parents=True)
    commission_out.mkdir(parents=True)
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t1", snippet="commission"),
        GmailMessageSummary(id="m2", thread_id="t2", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.side_effect = [
        None,
        (
            fixture_pdf.read_bytes(),
            "Invoice April Commission (EUR)",
            1775001600000,  # 2026-04-01 00:00 UTC
        ),
    ]
    report = save_commission_pdf(
        gmail_read_backend=bk,
        commission_query="from:jack commission",
        commission_dir=commission_out,
        downloads_dir=downloads,
    )
    assert report.message_id == "m2"
    assert report.commission_date == date(2026, 4, 1)
    assert report.renamed_filename == "2026-04 Commission April €1,234.56.pdf"
    assert "April" in report.renamed_filename


def test_save_commission_pdf_unparseable_pdf(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir(parents=True)
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.return_value = (
        b"not a pdf at all",
        "Invoice March Commission (EUR)",
        1772323200000,
    )
    with pytest.raises(SaveCommissionPdfError, match="Failed to parse"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
            downloads_dir=downloads,
        )


def test_save_commission_pdf_no_month_in_subject(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    commission_out = tmp_path / "out"
    downloads.mkdir(parents=True)
    commission_out.mkdir(parents=True)
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "pdf"
        / "invoice_eur_dot_decimal.pdf"
    )
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.return_value = (
        fixture_pdf.read_bytes(),
        "Commission invoice attached",
        1772323200000,
    )
    with pytest.raises(SaveCommissionPdfError, match="Could not find month"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=commission_out,
            downloads_dir=downloads,
        )


class TestCliSaveCommissionPdf:
    def test_test_run_skips_confirmation(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        mock_report = MagicMock()
        mock_report.message_id = "m1"
        mock_report.pdf_path = Path("2026-03 Commission March €1,234.56.pdf")
        mock_report.commission_date = date(2026, 3, 1)
        mock_report.amount_eur = Decimal("1234.56")
        mock_report.renamed_filename = "2026-03 Commission March €1,234.56.pdf"

        with (
            patch(
                "googleads_invoice.cli.GmailApiReadBackend.from_env",
            ),
            patch(
                "googleads_invoice.cli.save_commission_pdf",
                return_value=mock_report,
            ) as mock_save,
        ):
            code = main(["save-commission-pdf", "--test-run"])
            assert code == 0
            assert mock_save.call_args.kwargs["test_run"] is True

    @patch("builtins.input", return_value="y")
    def test_confirms_then_saves(
        self,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        mock_report = MagicMock()
        mock_report.message_id = "m1"
        mock_report.pdf_path = Path("2026-04 Commission April €1,234.56.pdf")
        mock_report.commission_date = date(2026, 4, 1)
        mock_report.amount_eur = Decimal("1234.56")
        mock_report.renamed_filename = "2026-04 Commission April €1,234.56.pdf"

        with (
            patch("googleads_invoice.cli.GmailApiReadBackend.from_env"),
            patch(
                "googleads_invoice.cli.save_commission_pdf",
                return_value=mock_report,
            ) as mock_save,
        ):
            code = main(["save-commission-pdf"])
            assert code == 0
            assert mock_save.call_args.kwargs["test_run"] is False

    @patch("builtins.input", return_value="n")
    def test_abort_on_no(
        self,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        with patch("googleads_invoice.cli.GmailApiReadBackend.from_env"):
            code = main(["save-commission-pdf"])
            assert code == 2

    def test_errors_when_oauth_missing(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        monkeypatch.delenv("GOOGLE_OAUTH_TOKEN", raising=False)
        code = main(["save-commission-pdf", "--test-run"])
        assert code == 2


def test_cli_save_commission_pdf_help_lists_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    from googleads_invoice.cli import main

    with pytest.raises(SystemExit):
        main(["save-commission-pdf", "--help"])
    err = capsys.readouterr()
    combined = err.out + err.err
    assert "save-commission-pdf" in combined
    assert "~/Downloads" in combined or "Downloads" in combined
