"""Gmail API read backend (``build`` and OAuth file I/O mocked or temp files)."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from googleads_invoice.billing_url import extract_billing_url
from googleads_invoice.gmail_api_backend import (
    DEFAULT_BILLING_MAIL_QUERY,
    GmailApiReadBackend,
    billing_mail_query_from_env,
    html_from_gmail_message_payload,
)
from googleads_invoice.gmail_facade import GmailMessageSummary, GmailTransportError


def test_billing_mail_query_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLEADS_GMAIL_BILLING_QUERY", raising=False)
    assert billing_mail_query_from_env() == DEFAULT_BILLING_MAIL_QUERY


def test_billing_mail_query_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLEADS_GMAIL_BILLING_QUERY", "from:custom")
    assert billing_mail_query_from_env() == "from:custom"


def test_from_token_path_rejects_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="not a file"):
        GmailApiReadBackend.from_token_path(p)


@patch("googleads_invoice.gmail_api_backend.Credentials.from_authorized_user_file")
def test_from_token_path_wraps_refresh_failure(
    mock_from_file: MagicMock, tmp_path: Path
) -> None:
    p = tmp_path / "tok.json"
    p.write_text("{}", encoding="utf-8")
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "rt"
    mock_from_file.return_value = creds

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("offline")

    creds.refresh = MagicMock(side_effect=boom)
    with pytest.raises(ValueError, match="Could not refresh"):
        GmailApiReadBackend.from_token_path(p)


def test_html_from_gmail_payload_multipart_alternative() -> None:
    html = '<a href="https://payments.google.com/inv">pay</a>'
    b64 = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": "cGk="}},
            {"mimeType": "text/html", "body": {"data": b64}},
        ],
    }
    raw = html_from_gmail_message_payload(payload)
    assert raw is not None
    assert extract_billing_url(raw) == "https://payments.google.com/inv"


@patch("googleads_invoice.gmail_api_backend.build")
def test_get_message_html_uses_full_format(mock_build: MagicMock) -> None:
    html = '<a href="https://pay.google.com/x">y</a>'
    b64 = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    get_chain = mock_service.users.return_value.messages.return_value.get.return_value
    get_chain.execute.return_value = {
        "id": "m2",
        "payload": {"mimeType": "text/html", "body": {"data": b64}},
    }
    backend = GmailApiReadBackend(credentials=MagicMock())
    out = backend.get_message_html("m2")
    assert extract_billing_url(out) == "https://pay.google.com/x"
    mock_service.users.return_value.messages.return_value.get.assert_called_once_with(
        userId="me",
        id="m2",
        format="full",
    )


@patch("googleads_invoice.gmail_api_backend.build")
def test_list_messages_maps_api_response(mock_build: MagicMock) -> None:
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    list_exec = mock_service.users.return_value.messages.return_value.list.return_value.execute
    list_exec.return_value = {"messages": [{"id": "m1", "threadId": "t1"}]}
    get_exec = mock_service.users.return_value.messages.return_value.get.return_value.execute
    get_exec.return_value = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "Billing document",
    }

    backend = GmailApiReadBackend(credentials=MagicMock())
    out = backend.list_messages("from:test", max_results=5)

    assert out == [
        GmailMessageSummary(
            id="m1",
            thread_id="t1",
            snippet="Billing document",
        )
    ]
    list_call = mock_service.users.return_value.messages.return_value.list
    list_call.assert_called_once_with(userId="me", q="from:test", maxResults=5)


@patch("googleads_invoice.gmail_api_backend.build")
def test_list_messages_empty_inbox(mock_build: MagicMock) -> None:
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {}

    backend = GmailApiReadBackend(credentials=MagicMock())
    assert backend.list_messages("none") == []


def test_send_methods_raise() -> None:
    b = GmailApiReadBackend(credentials=MagicMock())
    pdf = Path("x.pdf")
    with pytest.raises(GmailTransportError, match="does not send"):
        b.send_plain_text(
            sender="a@gmail.com",
            to="b@gmail.com",
            subject="s",
            body="x",
        )
    with pytest.raises(GmailTransportError, match="does not send"):
        b.send_text_with_pdf_attachment(
            sender="a@gmail.com",
            to="b@gmail.com",
            subject="s",
            body="x",
            pdf_path=pdf,
            attachment_name="i.pdf",
        )
