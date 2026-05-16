"""Gmail API read path (``users.messages.list`` / ``get``) using OAuth token file from disk.

Send still uses :class:`~googleads_invoice.gmail_smtp.SmtpGmailBackend` — this backend only implements
:class:`~googleads_invoice.gmail_facade.GmailBackend` ``list_messages``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from invoice_admin.googleads.gmail_facade import GmailMessageSummary, GmailTransportError

_ENV_OAUTH_TOKEN = "GOOGLE_OAUTH_TOKEN"

# Gmail search for the monthly billing notification (tune in one place).
DEFAULT_BILLING_MAIL_QUERY = (
    'from:payments-noreply@google.com subject:"Google Ads: Your billing document is ready"'
)

_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/adwords",
)


def _urlsafe_b64decode(data: str) -> bytes:
    pad = (4 - len(data) % 4) % 4
    return base64.urlsafe_b64decode(data + ("=" * pad))


def _html_from_part_body(part: dict) -> str | None:
    body = part.get("body") or {}
    raw = body.get("data")
    if not raw:
        return None
    try:
        return _urlsafe_b64decode(raw).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return None


def html_from_gmail_message_payload(payload: dict) -> str | None:
    """First ``text/html`` body in a Gmail API ``payload`` tree, or ``None``."""
    if (payload.get("mimeType") or "").lower() == "text/html":
        h = _html_from_part_body(payload)
        if h:
            return h
    for part in payload.get("parts") or []:
        mt = (part.get("mimeType") or "").lower()
        if mt == "text/html":
            html = _html_from_part_body(part)
            if html:
                return html
        nested = html_from_gmail_message_payload(part)
        if nested:
            return nested
    return None


# Gmail search for Jack's commission emails (override via env in CLI).
DEFAULT_COMMISSION_MAIL_QUERY = (
    "from:jack.copeland@theglugglejugfactory.com commission"
)


def billing_mail_query_from_env() -> str:
    """Return ``GOOGLEADS_GMAIL_BILLING_QUERY`` if set, else :data:`DEFAULT_BILLING_MAIL_QUERY`."""
    raw = os.environ.get("GOOGLEADS_GMAIL_BILLING_QUERY", "").strip()
    return raw if raw else DEFAULT_BILLING_MAIL_QUERY


def commission_mail_query_from_env() -> str:
    """Return ``GOOGLEADS_COMMISSION_QUERY`` if set, else :data:`DEFAULT_COMMISSION_MAIL_QUERY`."""
    raw = os.environ.get("GOOGLEADS_COMMISSION_QUERY", "").strip()
    return raw if raw else DEFAULT_COMMISSION_MAIL_QUERY


def _subject_header_value(full_message: dict) -> str:
    for h in (full_message.get("payload") or {}).get("headers") or []:
        if str(h.get("name") or "").lower() == "subject":
            return str(h.get("value") or "")
    return ""


def _internal_date_ms(full_message: dict) -> int:
    raw = full_message.get("internalDate")
    if raw is None or raw == "" or raw == "0" or raw == 0:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _find_pdf_attachment_part(part: dict) -> dict | None:
    """First PDF attachment part with a non-empty ``attachmentId``, or ``None``."""
    mime = (part.get("mimeType") or "").lower()
    filename = part.get("filename") or ""
    attachment_id = (part.get("body") or {}).get("attachmentId") or ""
    pdf_name = filename.lower().endswith(".pdf")
    is_pdf_mime = mime == "application/pdf"
    octet_pdf = mime == "application/octet-stream" and pdf_name
    if attachment_id and (pdf_name or is_pdf_mime or octet_pdf):
        return part

    for sub in part.get("parts") or []:
        found = _find_pdf_attachment_part(sub)
        if found is not None:
            return found
    return None


class GmailApiReadBackend:
    """Gmail API backend: **read** via OAuth token file; **send** is not supported (use SMTP)."""

    def __init__(self, *, credentials: Credentials) -> None:
        self._credentials = credentials

    @classmethod
    def from_token_path(cls, path: Path) -> GmailApiReadBackend:
        p = path.expanduser()
        if not p.is_file():
            raise ValueError(f"OAuth token path is not a file: {p}")
        creds = Credentials.from_authorized_user_file(str(p), scopes=_SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    from google.auth.transport.requests import Request

                    creds.refresh(Request())
                except Exception as e:
                    raise ValueError(
                        f"Could not refresh OAuth token ({p}): {e}"
                    ) from e
            else:
                raise ValueError(
                    f"OAuth token missing or invalid ({p}); re-authorize with gmail.readonly scope."
                )
        return cls(credentials=creds)

    @classmethod
    def from_env(cls) -> GmailApiReadBackend:
        raw = os.environ.get(_ENV_OAUTH_TOKEN, "").strip()
        if not raw:
            raise ValueError(
                f"Set {_ENV_OAUTH_TOKEN} to the authorized-user JSON file from your OAuth flow "
                "(must include gmail.readonly)."
            )
        return cls.from_token_path(Path(raw))

    def _service(self):
        return build("gmail", "v1", credentials=self._credentials, cache_discovery=False)

    def list_messages(self, query: str, *, max_results: int = 10) -> list[GmailMessageSummary]:
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        try:
            service = self._service()
            list_resp = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            raw_msgs = list_resp.get("messages") or []
            out: list[GmailMessageSummary] = []
            for m in raw_msgs:
                mid = m["id"]
                tid = m.get("threadId", "")
                detail = (
                    service.users()
                    .messages()
                    .get(userId="me", id=mid, format="minimal")
                    .execute()
                )
                out.append(
                    GmailMessageSummary(
                        id=detail.get("id", mid),
                        thread_id=detail.get("threadId", tid),
                        snippet=detail.get("snippet", ""),
                    )
                )
            return out
        except HttpError as e:
            raise GmailTransportError(f"Gmail API error: {e}") from e

    def get_message_html(self, message_id: str) -> str:
        """Fetch ``format=full`` and return the first ``text/html`` body."""
        try:
            service = self._service()
            full = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            payload = full.get("payload") or {}
            html = html_from_gmail_message_payload(payload)
            if not html:
                raise GmailTransportError(
                    f"No text/html part in Gmail message {message_id!r}."
                )
            return html
        except HttpError as e:
            raise GmailTransportError(f"Gmail API error: {e}") from e

    def get_message_pdf_with_metadata(
        self, message_id: str
    ) -> tuple[bytes, str, int] | None:
        """Return ``(pdf_bytes, subject, internal_date_ms)`` or ``None`` if no PDF attachment."""
        try:
            service = self._service()
            full = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            subject = _subject_header_value(full)
            internal_ms = _internal_date_ms(full)
            payload = full.get("payload") or {}
            part = _find_pdf_attachment_part(payload)
            if part is None:
                return None
            attachment_id = (part.get("body") or {}).get("attachmentId")
            if not attachment_id:
                return None
            att = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
            raw = att.get("data") or ""
            if not raw:
                return None
            return (_urlsafe_b64decode(raw), subject, internal_ms)
        except HttpError as e:
            raise GmailTransportError(f"Gmail API error: {e}") from e

    def get_message_pdf_attachment(self, message_id: str) -> bytes | None:
        """Return first PDF attachment body as bytes, or ``None`` if none match."""
        trio = self.get_message_pdf_with_metadata(message_id)
        return None if trio is None else trio[0]

    def find_by_rfc822_message_id(self, message_id: str) -> str | None:
        """Search Gmail for a message by its RFC822 Message-ID header.

        Returns the Gmail message id (``msg_id`` usable with ``get_message_html`` /
        ``get_message_pdf_with_metadata``) or ``None`` if not found.
        """
        results = self.list_messages(f"rfc822msgid:{message_id}", max_results=1)
        return results[0].id if results else None

    def send_plain_text(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        body: str,
    ) -> str:
        raise GmailTransportError(
            "GmailApiReadBackend does not send mail; use SmtpGmailBackend (send-test-pdf)."
        )

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
        raise GmailTransportError(
            "GmailApiReadBackend does not send mail; use SmtpGmailBackend (send-test-pdf)."
        )
