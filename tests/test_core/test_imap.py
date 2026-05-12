"""Tests for invoice_admin.core.imap."""
from __future__ import annotations

import email
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from invoice_admin.core.imap import ImapCollector, fetch_email_by_message_id


def _sample_invoice_email() -> bytes:
    msg = EmailMessage()
    msg["Subject"] = "Your March invoice"
    msg["From"] = "vendor@example.com"
    msg["Message-ID"] = "<inv-1@example.com>"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.add_attachment(
        b"%PDF-1.4",
        maintype="application",
        subtype="pdf",
        filename="bill.pdf",
    )
    return msg.as_bytes()


def test_imap_collector_collect_unseen_parses_pdf() -> None:
    raw = _sample_invoice_email()

    class FakeIMAP:
        def __init__(self, host: str) -> None:
            self.host = host

        def __enter__(self) -> FakeIMAP:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def login(self, user: str, password: str) -> tuple[str, None]:
            return "OK", None

        def select(self, mailbox: str) -> tuple[str, list]:
            return "OK", [b"0"]

        def search(self, charset: str | None, criterion: str) -> tuple[str, list]:
            return "OK", [b"41"]

        def fetch(self, num: bytes, parts: str) -> tuple[str, tuple]:
            return "OK", ((None, raw),)

    with patch("invoice_admin.core.imap.imaplib.IMAP4_SSL", FakeIMAP):
        col = ImapCollector("imap.example.com", "u", "p")
        msgs = list(col.collect_unseen())

    assert len(msgs) == 1
    m = msgs[0]
    assert m.message_id.startswith("<")
    assert m.pdf_attachments
    assert b"%PDF" in m.pdf_attachments[0]


def test_fetch_email_by_message_id_returns_parsed_message() -> None:
    raw = _sample_invoice_email()
    mock_imap = MagicMock()
    mock_imap.login = MagicMock()
    mock_imap.select = MagicMock()
    mock_imap.search.return_value = ("OK", [b"1"])
    mock_imap.fetch.return_value = ("OK", [(None, raw)])

    with patch("invoice_admin.core.imap.imaplib.IMAP4_SSL") as m_ssl:
        m_ssl.return_value.__enter__.return_value = mock_imap
        em = fetch_email_by_message_id("h", "u", "p", "<inv-1@example.com>")

    assert em is not None
    assert em.message_id == "<inv-1@example.com>"
    mock_imap.search.assert_called()
    mock_imap.fetch.assert_called_once()
