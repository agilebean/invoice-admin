"""Send mail via Gmail SMTP (app password). Listing/search requires a Gmail API backend later."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from googleads_invoice.gmail_facade import GmailMessageSummary, GmailTransportError


class SmtpGmailBackend:
    """``GmailBackend`` for **send only** using Gmail SMTP and an **app password**.

    Create an app password: Google Account → Security → 2-Step Verification → App passwords.

    **CLI:** ``googleads-invoice send-test-pdf`` loads the secret from
    ``GOOGLEADS_GMAIL_SMTP_APP_PASSWORD`` or the first line of
    ``GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE``, then constructs this backend (never commit secrets).
    """

    def __init__(
        self,
        *,
        user: str,
        app_password: str,
        host: str = "smtp.gmail.com",
        port: int = 587,
    ) -> None:
        self._user = user.strip()
        self._app_password = app_password
        self._host = host
        self._port = port

    def list_messages(self, query: str, *, max_results: int = 10) -> list[GmailMessageSummary]:
        raise GmailTransportError(
            "SmtpGmailBackend does not implement list_messages; use a Gmail API backend or Spark export."
        )

    def send_plain_text(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        body: str,
    ) -> str:
        if sender.strip() != self._user:
            raise GmailTransportError(
                f"SMTP login user {self._user!r} must match From address {sender!r} for Gmail."
            )
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        self._send_message(msg)
        return "smtp:plain:ok"

    def send_text_with_pdf_attachment(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        body: str,
        pdf_path: Path,
        attachment_name: str,
    ) -> str:
        if sender.strip() != self._user:
            raise GmailTransportError(
                f"SMTP login user {self._user!r} must match From address {sender!r} for Gmail."
            )
        path = pdf_path.expanduser()
        if not path.is_file():
            raise GmailTransportError(f"PDF attachment not a file: {path}")
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        msg.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=attachment_name,
        )
        self._send_message(msg)
        return "smtp:pdf:ok"

    def _send_message(self, msg: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self._host, self._port, timeout=60) as server:
                server.starttls()
                server.login(self._user, self._app_password)
                server.send_message(msg)
        except smtplib.SMTPException as e:
            raise GmailTransportError(str(e)) from e
        except OSError as e:
            raise GmailTransportError(str(e)) from e
