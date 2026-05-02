"""SmtpGmailBackend unit tests (SMTP mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from googleads_invoice.gmail_facade import GmailTransportError
from googleads_invoice.gmail_smtp import SmtpGmailBackend


@patch("googleads_invoice.gmail_smtp.smtplib.SMTP")
def test_smtp_send_text_with_pdf_attachment(
    mock_smtp_class: MagicMock,
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test bytes")

    mock_server = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_server)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_smtp_class.return_value = mock_ctx

    backend = SmtpGmailBackend(user="me@gmail.com", app_password="app-secret")
    result = backend.send_text_with_pdf_attachment(
        sender="me@gmail.com",
        to="jack@example.com",
        subject="Invoice test",
        body="Please see attached.\n",
        pdf_path=pdf,
        attachment_name="google-ads-invoice_test.pdf",
    )

    assert result == "smtp:pdf:ok"
    mock_smtp_class.assert_called_once()
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me@gmail.com", "app-secret")
    mock_server.send_message.assert_called_once()
    sent = mock_server.send_message.call_args[0][0]
    assert sent["Subject"] == "Invoice test"
    assert sent["To"] == "jack@example.com"


def test_smtp_rejects_sender_mismatch(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    backend = SmtpGmailBackend(user="real@gmail.com", app_password="x")
    with pytest.raises(GmailTransportError, match="must match From"):
        backend.send_text_with_pdf_attachment(
            sender="other@gmail.com",
            to="a@b.com",
            subject="s",
            body="b",
            pdf_path=pdf,
            attachment_name="a.pdf",
        )


def test_smtp_list_messages_raises() -> None:
    backend = SmtpGmailBackend(user="u@gmail.com", app_password="x")
    with pytest.raises(GmailTransportError, match="does not implement list_messages"):
        backend.list_messages("q")
