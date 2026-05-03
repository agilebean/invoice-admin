"""Tests for :mod:`~googleads_invoice.api_download` (pure logic + CLI wiring; network mocked)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from googleads_invoice.api_download import (
    ApiDownloadError,
    _extract_ids_from_url,
    api_download_pdf,
)
from googleads_invoice.cli import main


# ── _extract_ids_from_url ──────────────────────────────────────────────


class TestExtractIdsFromUrl:
    def test_extracts_billing_id_from_query(self) -> None:
        url = "https://ads.google.com/aw/billing/documents?billingId=12345"
        ids = _extract_ids_from_url(url)
        assert ids.get("billing_id") == "12345"

    def test_extracts_customer_id_from_query(self) -> None:
        url = "https://ads.google.com/aw/billing/documents?customer_id=98765"
        ids = _extract_ids_from_url(url)
        assert ids.get("customer_id") == "98765"

    def test_extracts_ids_from_path(self) -> None:
        url = "https://ads.google.com/aw/billing/documents/customer/555"
        ids = _extract_ids_from_url(url)
        assert ids.get("customer_id") == "555"

    def test_empty_for_unknown_url(self) -> None:
        url = "https://payments.google.com/invoice"
        ids = _extract_ids_from_url(url)
        assert ids == {}


# ── api_download_pdf ────────────────────────────────────────────────────


class TestApiDownloadPdf:
    def test_successful_api_download(self, tmp_path: Path) -> None:
        """Happy path: API returns a billing document with a download URL."""
        mock_session = MagicMock()
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {
            "billingDocuments": [{
                "pdfDownloadUrl": "https://cdn.google.com/invoice.pdf?token=abc",
            }],
        }
        api_resp.headers = {"Content-Type": "application/json"}

        pdf_resp = MagicMock()
        pdf_resp.status_code = 200
        pdf_resp.headers = {"Content-Type": "application/pdf"}
        pdf_resp.iter_content.return_value = [b"%PDF-1.4 test data"]

        mock_session.get.side_effect = [api_resp, pdf_resp]

        credentials = MagicMock()

        with patch(
            "googleads_invoice.api_download.AuthorizedSession",
            return_value=mock_session,
        ):
            result = api_download_pdf(
                billing_url="https://ads.google.com/aw/billing/documents?customer_id=123&billingId=456",
                credentials=credentials,
                download_dir=tmp_path,
            )

        assert result.suffix == ".pdf"
        assert result.stat().st_size > 0
        assert result.parent == tmp_path.resolve()

    def test_raises_error_when_api_returns_401(self, tmp_path: Path) -> None:
        """HTTP 401 means the token lacks the adwords scope."""
        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 401
        mock_session.get.return_value = resp

        credentials = MagicMock()

        with patch(
            "googleads_invoice.api_download.AuthorizedSession",
            return_value=mock_session,
        ):
            with pytest.raises(ApiDownloadError, match="adwords"):
                api_download_pdf(
                    billing_url="https://ads.google.com/aw/billing/documents?customer_id=123",
                    credentials=credentials,
                    download_dir=tmp_path,
                )

    def test_raises_error_when_no_customer_id(self, tmp_path: Path) -> None:
        """Without a customer ID, the API can't be queried."""
        credentials = MagicMock()

        with pytest.raises(ApiDownloadError, match="Could not download"):
            api_download_pdf(
                billing_url="https://c.gle/abc123",
                credentials=credentials,
                download_dir=tmp_path,
            )

    def test_follows_redirects_from_cdn(self, tmp_path: Path) -> None:
        """When the download URL redirects (302 → signed URL), follow it."""
        mock_session = MagicMock()

        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {
            "billingDocuments": [{"pdfDownloadUrl": "https://cdn.google.com/redirect"}],
        }

        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"Location": "https://cdn.google.com/signed.pdf?token=abc"}

        pdf_resp = MagicMock()
        pdf_resp.status_code = 200
        pdf_resp.headers = {"Content-Type": "application/pdf"}
        pdf_resp.iter_content.return_value = [b"%PDF-1.4 data"]

        mock_session.get.side_effect = [api_resp, redirect_resp, pdf_resp]

        credentials = MagicMock()

        with patch(
            "googleads_invoice.api_download.AuthorizedSession",
            return_value=mock_session,
        ):
            result = api_download_pdf(
                billing_url="https://ads.google.com/aw/billing/documents?customer_id=123",
                credentials=credentials,
                download_dir=tmp_path,
            )

        assert result.suffix == ".pdf"
        assert result.stat().st_size > 0

    def test_tries_multiple_api_versions(self, tmp_path: Path) -> None:
        """Tries newer versions first; falls back if 404."""
        mock_session = MagicMock()

        # First two versions return 404, third returns success
        responses = []
        for _ in range(3):
            r = MagicMock()
            r.status_code = 404
            responses.append(r)

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "billingDocuments": [{"pdfDownloadUrl": "https://cdn.google.com/invoice.pdf"}]
        }
        responses.append(success)

        pdf_resp = MagicMock()
        pdf_resp.status_code = 200
        pdf_resp.headers = {"Content-Type": "application/pdf"}
        pdf_resp.iter_content.return_value = [b"%PDF-1.4 data"]
        responses.append(pdf_resp)

        mock_session.get.side_effect = responses

        credentials = MagicMock()

        with patch(
            "googleads_invoice.api_download.AuthorizedSession",
            return_value=mock_session,
        ):
            result = api_download_pdf(
                billing_url="https://ads.google.com/aw/billing/documents?customer_id=123",
                credentials=credentials,
                download_dir=tmp_path,
            )

        assert result.suffix == ".pdf"

    def test_raise_error_on_network_failure(self, tmp_path: Path) -> None:
        mock_session = MagicMock()
        mock_session.get.side_effect = ConnectionError("network unreachable")

        credentials = MagicMock()

        with patch(
            "googleads_invoice.api_download.AuthorizedSession",
            return_value=mock_session,
        ):
            with pytest.raises(ApiDownloadError, match="Could not download"):
                api_download_pdf(
                    billing_url="https://ads.google.com/aw/billing/documents?customer_id=123",
                    credentials=credentials,
                    download_dir=tmp_path,
                )


# ── CLI: api-download subcommand ────────────────────────────────────────


class TestCliApiDownload:
    def test_refuses_without_confirm_env(self) -> None:
        code = main(["api-download"])
        assert code == 2

    def test_errors_when_deeplink_missing(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLEADS_CONFIRM_API_DOWNLOAD", "1")
        monkeypatch.delenv("GOOGLEADS_BILLING_DEEPLINK", raising=False)
        code = main(["api-download"])
        assert code == 2

    @patch("googleads_invoice.cli.api_download_pdf")
    @patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
    def test_happy_path(
        self,
        mock_from_env: MagicMock,
        mock_download: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("GOOGLEADS_CONFIRM_API_DOWNLOAD", "1")
        monkeypatch.setenv("GOOGLEADS_BILLING_DEEPLINK", "https://c.gle/abc")
        monkeypatch.setenv("GOOGLEADS_OAUTH_TOKEN", "/tmp/dummy.json")
        mock_from_env.return_value = MagicMock()

        pdf = tmp_path / "invoice.pdf"
        pdf.write_text("pdf", encoding="utf-8")
        mock_download.return_value = pdf

        code = main(["api-download"])
        assert code == 0
        mock_download.assert_called_once()
        assert "Downloaded" in capsys.readouterr().err

    @patch("googleads_invoice.cli.api_download_pdf")
    @patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
    def test_uses_flag_args_over_env(
        self,
        mock_from_env: MagicMock,
        mock_download: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("GOOGLEADS_CONFIRM_API_DOWNLOAD", "1")
        monkeypatch.setenv("GOOGLEADS_BILLING_DEEPLINK", "should-not-win")
        monkeypatch.setenv("GOOGLEADS_OAUTH_TOKEN", "/tmp/dummy.json")
        mock_from_env.return_value = MagicMock()

        pdf = tmp_path / "invoice.pdf"
        pdf.write_text("pdf", encoding="utf-8")
        mock_download.return_value = pdf

        code = main([
            "api-download",
            "--deeplink", "https://c.gle/flag",
            "--download-dir", str(tmp_path / "custom"),
        ])
        assert code == 0
        _, kwargs = mock_download.call_args
        assert kwargs["billing_url"] == "https://c.gle/flag"
        assert kwargs["download_dir"] == tmp_path / "custom"

    @patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
    def test_propagates_api_download_error(
        self,
        mock_from_env: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLEADS_CONFIRM_API_DOWNLOAD", "1")
        monkeypatch.setenv("GOOGLEADS_BILLING_DEEPLINK", "https://c.gle/abc")
        monkeypatch.setenv("GOOGLEADS_OAUTH_TOKEN", "/tmp/dummy.json")

        mock_from_env.return_value = MagicMock()

        with patch(
            "googleads_invoice.cli.api_download_pdf",
            side_effect=ApiDownloadError("something went wrong"),
        ):
            code = main(["api-download"])
            assert code == 2


# ── run-month --download-method api ─────────────────────────────────────


class TestRunMonthApiDownload:
    """Verify run-month with --download-method=api passes the flag correctly."""

    @patch("builtins.input", return_value="y")
    @patch("googleads_invoice.cli.run_month")
    @patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
    def test_run_month_uses_api_method(
        self,
        mock_from_env: MagicMock,
        mock_run_month: MagicMock,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from googleads_invoice.cli import main
        from googleads_invoice.run_month import RunMonthReport

        monkeypatch.setenv("GOOGLEADS_CONFIRM_RUN_MONTH", "1")
        monkeypatch.setenv("GOOGLEADS_OAUTH_TOKEN", "/tmp/dummy.json")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
        monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
        monkeypatch.delenv("GOOGLEADS_BROWSER_DEBUGGER_ADDRESS", raising=False)
        mock_from_env.return_value = MagicMock()

        pdf = tmp_path / "invoice.pdf"
        pdf.write_text("pdf", encoding="utf-8")
        mock_run_month.return_value = RunMonthReport(
            billing_url="https://payments.google.com/billing/x",
            pdf_path=pdf,
            issue_date=date(2026, 4, 2),
            amount_eur=Decimal("100.00"),
            renamed_filename="invoice.pdf",
            email_subject="subj",
            email_body="body",
            recipient="jack@example.com",
            send_status="smtp:pdf:ok",
        )

        code = main(["run-month", "--download-method", "api", "--to", "jack@example.com"])
        assert code == 0
        assert mock_run_month.call_args.kwargs["download_method"] == "api"

    def test_run_month_rejects_invalid_method(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from googleads_invoice.cli import main

        with pytest.raises(SystemExit):
            main(["run-month", "--download-method", "invalid"])
