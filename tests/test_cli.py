from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from googleads_invoice.addresses import DEFAULT_GMAIL_SENDER, DEFAULT_TEST_RECIPIENT
from googleads_invoice.gmail_facade import GmailMessageSummary

from googleads_invoice.cli import _smtp_app_password_from_env, main


def test_cli_dry_run_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["dry-run", "--mail-html", str(mail), "--invoice-pdf", str(pdf)])
    assert code == 0
    out = capsys.readouterr().out
    assert "payments.google.com" in out
    assert "Gmail send skipped" in out
    assert "chaehan.so@gmail.com" in out
    assert "jack.copeland@theglugglejugfactory.com" in out


def test_cli_requires_subcommand() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code != 0


@patch(
    "googleads_invoice.cli.billing_month_label_for_previous_calendar_month",
    return_value="April 2026",
)
def test_cli_dry_run_email_month_from_billing_clock(
    _mock_billing_month: object, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["dry-run", "--mail-html", str(mail), "--invoice-pdf", str(pdf)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Dear Jack," in out
    assert "April 2026" in out


def test_cli_dry_run_mail_html_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    monkeypatch.setenv("GOOGLEADS_INVOICE_MAIL_HTML", str(mail))
    code = main(["dry-run", "--invoice-pdf", str(pdf)])
    assert code == 0
    assert "payments.google.com" in capsys.readouterr().out


def test_cli_dry_run_invoice_pdf_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    monkeypatch.setenv("GOOGLEADS_INVOICE_PDF", str(pdf))
    code = main(["dry-run", "--mail-html", str(mail)])
    assert code == 0
    assert "EUR" in capsys.readouterr().out


@patch(
    "googleads_invoice.cli.billing_month_label_for_previous_calendar_month",
    return_value="April 2026",
)
def test_cli_dry_run_real_world_paths_env_only(
    _mock_billing_month: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    monkeypatch.setenv("GOOGLEADS_INVOICE_MAIL_HTML", str(mail))
    monkeypatch.setenv("GOOGLEADS_INVOICE_PDF", str(pdf))
    code = main(["dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "April 2026" in out
    assert "payments.google.com" in out


def test_cli_dry_run_errors_when_mail_html_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parent
    monkeypatch.delenv("GOOGLEADS_INVOICE_MAIL_HTML", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "dry-run",
                "--invoice-pdf",
                str(root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"),
            ]
        )
    assert excinfo.value.code != 0


def test_cli_dry_run_errors_when_invoice_pdf_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parent
    mail = root / "fixtures" / "gmail" / "billing_mail_happy.html"
    monkeypatch.delenv("GOOGLEADS_INVOICE_PDF", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        main(["dry-run", "--mail-html", str(mail)])
    assert excinfo.value.code != 0


def test_smtp_app_password_from_file_first_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "gmail-app-pw"
    secret.write_text("  first-line-secret  \nignored\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "inline-should-not-win")
    assert _smtp_app_password_from_env() == "first-line-secret"


def test_smtp_app_password_from_file_empty_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "empty"
    secret.write_text("\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", str(secret))
    with pytest.raises(ValueError, match="empty"):
        _smtp_app_password_from_env()


def test_smtp_app_password_from_file_not_a_file_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "nope"
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", str(missing))
    with pytest.raises(ValueError, match="not a file"):
        _smtp_app_password_from_env()


def test_cli_send_test_pdf_errors_when_password_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_TEST_SEND", "1")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "sender@gmail.com")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", raising=False)
    monkeypatch.setenv(
        "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE",
        str(tmp_path / "does-not-exist"),
    )
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(
        ["send-test-pdf", "--to", "recipient@test.com", "--pdf", str(pdf)]
    )
    assert code == 2


@patch("googleads_invoice.cli.SmtpGmailBackend")
def test_cli_send_test_pdf_uses_default_recipient_without_to(
    mock_backend_cls: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_TEST_SEND", "1")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "fake-app-password")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
    monkeypatch.delenv("GOOGLEADS_INVOICE_TO", raising=False)
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"

    code = main(["send-test-pdf", "--pdf", str(pdf)])
    assert code == 0
    backend = mock_backend_cls.return_value
    assert backend.send_text_with_pdf_attachment.call_args.kwargs["to"] == (
        DEFAULT_TEST_RECIPIENT
    )


@patch("googleads_invoice.cli.SmtpGmailBackend")
def test_cli_send_test_pdf_respects_invoice_to_env(
    mock_backend_cls: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_TEST_SEND", "1")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
    monkeypatch.setenv(
        "GOOGLEADS_INVOICE_TO",
        "jack.copeland@theglugglejugfactory.com",
    )
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["send-test-pdf", "--pdf", str(pdf)])
    assert code == 0
    to_addr = (
        mock_backend_cls.return_value.send_text_with_pdf_attachment.call_args.kwargs["to"]
    )
    assert to_addr == "jack.copeland@theglugglejugfactory.com"


@patch("googleads_invoice.cli.SmtpGmailBackend")
def test_cli_send_test_pdf_defaults_smtp_user_to_project_gmail(
    mock_backend_cls: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_TEST_SEND", "1")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_USER", raising=False)
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "fake-app-password")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["send-test-pdf", "--to", "recipient@test.com", "--pdf", str(pdf)])
    assert code == 0
    mock_backend_cls.assert_called_once_with(
        user=DEFAULT_GMAIL_SENDER,
        app_password="fake-app-password",
    )


@patch("googleads_invoice.cli.SmtpGmailBackend")
def test_cli_send_test_pdf_sends_with_mock_backend(
    mock_backend_cls: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_TEST_SEND", "1")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "fake-app-password")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", raising=False)
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(
        ["send-test-pdf", "--to", "recipient@test.com", "--pdf", str(pdf)]
    )
    assert code == 0
    mock_backend_cls.assert_called_once_with(
        user="sender@gmail.com",
        app_password="fake-app-password",
    )
    backend = mock_backend_cls.return_value
    backend.send_text_with_pdf_attachment.assert_called_once()
    call_kw = backend.send_text_with_pdf_attachment.call_args.kwargs
    assert call_kw["sender"] == "sender@gmail.com"
    assert call_kw["to"] == "recipient@test.com"
    assert call_kw["pdf_path"] == pdf
    assert "Dear Jack" in call_kw["body"]


@patch("googleads_invoice.cli.SmtpGmailBackend")
def test_cli_send_test_pdf_with_password_file(
    mock_backend_cls: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = tmp_path / "pw"
    secret.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLEADS_CONFIRM_TEST_SEND", "1")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "sender@gmail.com")
    monkeypatch.delenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", raising=False)
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE", str(secret))
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(
        ["send-test-pdf", "--to", "recipient@test.com", "--pdf", str(pdf)]
    )
    assert code == 0
    mock_backend_cls.assert_called_once_with(
        user="sender@gmail.com",
        app_password="from-file",
    )


def test_cli_list_billing_mail_requires_oauth_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN", raising=False)
    code = main(["list-billing-mail"])
    assert code == 2


@patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
def test_cli_billing_url_from_gmail_prints_url(
    mock_from_env: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/tok.json")
    backend = MagicMock()
    backend.list_messages.return_value = [
        GmailMessageSummary(id="mid1", thread_id="tid", snippet="s"),
    ]
    backend.get_message_html.return_value = (
        '<html><body><a href="https://payments.google.com/billing/x">v</a></body></html>'
    )
    mock_from_env.return_value = backend
    code = main(["billing-url-from-gmail", "--max-scan", "1"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out == "https://payments.google.com/billing/x"


@patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
def test_cli_billing_url_from_gmail_exits_1_when_not_found(
    mock_from_env: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/tok.json")
    backend = MagicMock()
    backend.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet=""),
    ]
    backend.get_message_html.return_value = "<html><body>no links</body></html>"
    mock_from_env.return_value = backend
    code = main(["billing-url-from-gmail"])
    assert code == 1


@patch("googleads_invoice.cli.GmailFacade")
@patch("googleads_invoice.cli.GmailApiReadBackend.from_env")
def test_cli_list_billing_mail_prints_rows(
    mock_from_env: object,
    mock_facade_cls: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
    mock_from_env.return_value = object()
    facade = MagicMock()
    facade.list_messages.return_value = [
        GmailMessageSummary(id="mid", thread_id="tid", snippet="hello"),
    ]
    mock_facade_cls.return_value = facade
    code = main(["list-billing-mail", "--query", "from:x", "--max-results", "3"])
    assert code == 0
    facade.list_messages.assert_called_once_with("from:x", max_results=3)
    assert "mid\ttid\thello" in capsys.readouterr().out


@patch("googleads_invoice.cli.open_mail_app_draft")
def test_cli_mail_app_draft_default_to_virtualfriend_when_omitted(
    mock_open: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_MAIL_APP_DRAFT", "1")
    monkeypatch.delenv("GOOGLEADS_INVOICE_TO", raising=False)
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["mail-app-draft", "--pdf", str(pdf)])
    assert code == 0
    assert mock_open.call_args.kwargs["to_address"] == DEFAULT_TEST_RECIPIENT


@patch("googleads_invoice.cli.open_mail_app_draft")
def test_cli_mail_app_draft_calls_open_draft(
    mock_open: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLEADS_CONFIRM_MAIL_APP_DRAFT", "1")
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["mail-app-draft", "--to", "x@test.com", "--pdf", str(pdf)])
    assert code == 0
    mock_open.assert_called_once()
    kw = mock_open.call_args.kwargs
    assert kw["to_address"] == "x@test.com"
    assert kw["pdf_path"] == pdf


def test_cli_mail_app_draft_refuses_without_confirm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLEADS_CONFIRM_MAIL_APP_DRAFT", raising=False)
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["mail-app-draft", "--to", "x@test.com", "--pdf", str(pdf)])
    assert code == 2


def test_cli_send_test_pdf_refuses_without_confirm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLEADS_CONFIRM_TEST_SEND", raising=False)
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_USER", "a@gmail.com")
    monkeypatch.setenv("GOOGLEADS_GMAIL_SMTP_APP_PASSWORD", "x")
    root = Path(__file__).resolve().parent
    pdf = root / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    code = main(["send-test-pdf", "--to", "b@test.com", "--pdf", str(pdf)])
    assert code == 2
