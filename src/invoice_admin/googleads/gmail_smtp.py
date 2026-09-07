"""Send mail via Gmail SMTP (app password). Listing/search requires a Gmail API backend later."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from invoice_admin.googleads.addresses import DEFAULT_GMAIL_SENDER
from invoice_admin.googleads.gmail_facade import GmailMessageSummary, GmailTransportError

_ENV_SMTP_USER = "GOOGLEADS_GMAIL_SMTP_USER"
_ENV_SMTP_PW = "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD"
_ENV_SMTP_PW_FILE = "GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE"


def _smtp_login_user() -> str:
    """SMTP login / From: ``GOOGLEADS_GMAIL_SMTP_USER`` or project Gmail default."""
    return os.environ.get(_ENV_SMTP_USER, "").strip() or DEFAULT_GMAIL_SENDER


def _smtp_app_password_from_env() -> str:
    """Return Gmail app password from env, or first line of *password file* (more secure than export)."""
    raw_path = os.environ.get(_ENV_SMTP_PW_FILE, "").strip()
    if raw_path:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise ValueError(
                f"{_ENV_SMTP_PW_FILE} is not a file: {path} "
                f"(use chmod 600; never commit this file)."
            )
        raw = path.read_text(encoding="utf-8")
        lines = raw.strip().splitlines()
        if not lines:
            raise ValueError(f"{_ENV_SMTP_PW_FILE} is empty: {path}")
        line = lines[0].strip()
        if not line:
            raise ValueError(f"{_ENV_SMTP_PW_FILE} is empty: {path}")
        return line
    return os.environ.get(_ENV_SMTP_PW, "").strip()


class SmtpGmailBackend:
    """``GmailBackend`` for **send only** using Gmail SMTP and an **app password**.

    Create an app password: Google Account → Security → 2-Step Verification → App passwords.

    **CLI:** ``invoice send`` loads the secret from
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
        # Port 465 uses direct SSL; port 587 uses STARTTLS
        self._use_ssl = (port == 465)

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
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
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
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
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
        import ssl as _ssl
        last_error: Exception | None = None
        ports_to_try = [(self._host, self._port, self._use_ssl)]
        # Fallback: if 587 fails, try 465; if 465 fails, try 587
        if self._port == 587:
            ports_to_try.append((self._host, 465, True))
        elif self._port == 465:
            ports_to_try.append((self._host, 587, False))

        for host, port, use_ssl in ports_to_try:
            try:
                if use_ssl:
                    ctx = _ssl.create_default_context()
                    with smtplib.SMTP_SSL(host, port, timeout=120, context=ctx) as server:
                        server.login(self._user, self._app_password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(host, port, timeout=120) as server:
                        server.starttls()
                        server.login(self._user, self._app_password)
                        server.send_message(msg)
                return
            except (smtplib.SMTPException, OSError) as e:
                last_error = e
                continue
        raise GmailTransportError(str(last_error or "SMTP connection failed"))
