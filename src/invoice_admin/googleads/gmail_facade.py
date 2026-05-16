"""Gmail operations behind a pluggable backend (use mocks/fakes in tests; real HTTP later)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class GmailMessageSummary:
    """Minimal row for inbox search results."""

    id: str
    thread_id: str
    snippet: str


class GmailTransportError(RuntimeError):
    """Raised when listing or sending fails at the backend/transport layer."""


@runtime_checkable
class GmailBackend(Protocol):
    def list_messages(self, query: str, *, max_results: int = 10) -> list[GmailMessageSummary]:
        """Return lightweight messages for a Gmail search query (`q` string)."""
        ...

    def send_plain_text(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        body: str,
    ) -> str:
        """Send a plain-text message; return the provider message id."""
        ...

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
        """Send ``body`` with one PDF attachment; return an opaque send handle / id."""
        ...


class GmailFacade:
    """Thin façade: stable call shape + consistent error wrapping for orchestration code."""

    def __init__(self, backend: GmailBackend) -> None:
        self._backend = backend

    def list_messages(self, query: str, *, max_results: int = 10) -> list[GmailMessageSummary]:
        try:
            return self._backend.list_messages(query, max_results=max_results)
        except GmailTransportError:
            raise
        except Exception as e:
            raise GmailTransportError(str(e)) from e

    def send_plain_text(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        body: str,
    ) -> str:
        try:
            return self._backend.send_plain_text(
                sender=sender,
                to=to,
                subject=subject,
                body=body,
            )
        except GmailTransportError:
            raise
        except Exception as e:
            raise GmailTransportError(str(e)) from e

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
        try:
            return self._backend.send_text_with_pdf_attachment(
                sender=sender,
                to=to,
                subject=subject,
                body=body,
                pdf_path=pdf_path,
                attachment_name=attachment_name,
                cc=cc,
                bcc=bcc,
            )
        except GmailTransportError:
            raise
        except Exception as e:
            raise GmailTransportError(str(e)) from e
