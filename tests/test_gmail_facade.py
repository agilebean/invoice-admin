from unittest.mock import MagicMock

import pytest

from googleads_invoice.gmail_facade import (
    GmailFacade,
    GmailMessageSummary,
    GmailTransportError,
)


def test_facade_list_messages_delegates_to_backend() -> None:
    backend = MagicMock()
    backend.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t1", snippet="invoice"),
        GmailMessageSummary(id="m2", thread_id="t2", snippet="other"),
    ]
    facade = GmailFacade(backend)
    out = facade.list_messages("from:payments-noreply", max_results=3)
    backend.list_messages.assert_called_once_with("from:payments-noreply", max_results=3)
    assert [m.id for m in out] == ["m1", "m2"]


def test_facade_send_plain_text_delegates_to_backend() -> None:
    backend = MagicMock()
    backend.send_plain_text.return_value = "msg-sent-99"
    facade = GmailFacade(backend)
    mid = facade.send_plain_text(
        sender="me@gmail.com", to="jack@example.com", subject="Hi", body="Body\n"
    )
    assert mid == "msg-sent-99"
    backend.send_plain_text.assert_called_once_with(
        sender="me@gmail.com",
        to="jack@example.com",
        subject="Hi",
        body="Body\n",
    )


def test_facade_wraps_unexpected_backend_errors_as_transport_error() -> None:
    backend = MagicMock()
    backend.list_messages.side_effect = OSError("nope")
    facade = GmailFacade(backend)
    with pytest.raises(GmailTransportError) as excinfo:
        facade.list_messages("q")
    assert "nope" in str(excinfo.value)


def test_facade_does_not_double_wrap_gmail_transport_error() -> None:
    backend = MagicMock()
    backend.send_plain_text.side_effect = GmailTransportError("already")
    facade = GmailFacade(backend)
    with pytest.raises(GmailTransportError, match="already"):
        facade.send_plain_text(
            sender="a@b.com", to="c@d.com", subject="s", body="b"
        )
