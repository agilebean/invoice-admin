"""Gmail API read path (``users.messages.list`` / ``get``) using OAuth token file from disk.

Send still uses :class:`~googleads_invoice.gmail_smtp.SmtpGmailBackend` — this backend only implements
:class:`~googleads_invoice.gmail_facade.GmailBackend` ``list_messages``.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from googleads_invoice.gmail_facade import GmailMessageSummary, GmailTransportError

_ENV_OAUTH_TOKEN = "GOOGLEADS_GMAIL_OAUTH_TOKEN"

# Gmail search for the monthly billing notification (tune in one place).
DEFAULT_BILLING_MAIL_QUERY = (
    'from:payments-noreply@google.com subject:"Google Ads: Your billing document is ready"'
)

_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)


def billing_mail_query_from_env() -> str:
    """Return ``GOOGLEADS_GMAIL_BILLING_QUERY`` if set, else :data:`DEFAULT_BILLING_MAIL_QUERY`."""
    raw = os.environ.get("GOOGLEADS_GMAIL_BILLING_QUERY", "").strip()
    return raw if raw else DEFAULT_BILLING_MAIL_QUERY


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
