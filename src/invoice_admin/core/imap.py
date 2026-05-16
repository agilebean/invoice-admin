"""IMAP email collection for invoice ingestion."""
from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Iterator


def _decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _get_message_id(msg: email.message.Message) -> str:
    raw = msg.get("Message-ID", "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("<") else f"<{raw}>"


def _collect_pdf_parts(msg: email.message.Message) -> list[bytes]:
    out: list[bytes] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "application/pdf":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    out.append(payload)
    else:
        if msg.get_content_type() == "application/pdf":
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                out.append(payload)
    return out


def _html_body(msg: email.message.Message) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return None


_INVOICE_SUBJECT_HINT = re.compile(
    r"\b(invoice|rechnung|bill|facture|payment due)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EmailMessage:
    """Parsed email ready for invoice processing."""

    message_id: str
    sender: str
    subject: str
    date: datetime
    html_body: str | None
    pdf_attachments: list[bytes]


class ImapCollector:
    """Connects to IMAP, searches for invoice-bearing emails, yields EmailMessage objects."""

    def __init__(self, host: str, user: str, password: str, mailbox: str = "INBOX") -> None:
        self._host = host
        self._user = user
        self._password = password
        self._mailbox = mailbox

    def collect_unseen(self) -> Iterator[EmailMessage]:
        """Yield unseen emails with PDF attachments or invoice-like subjects."""
        with imaplib.IMAP4_SSL(self._host) as imap:
            imap.login(self._user, self._password)
            imap.select(self._mailbox)
            typ, data = imap.search(None, "UNSEEN")
            if typ != "OK" or not data or not data[0]:
                return
            for num in data[0].split():
                typ, msg_data = imap.fetch(num, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_bytes = msg_data[0][1]
                if not isinstance(raw_bytes, (bytes, bytearray)):
                    continue
                msg = email.message_from_bytes(bytes(raw_bytes))
                message_id = _get_message_id(msg)
                if not message_id:
                    continue
                sender = msg.get("From", "") or ""
                subject = _decode_header_value(msg.get("Subject", "") or "")
                date_hdr = msg.get("Date", "") or ""
                try:
                    date = parsedate_to_datetime(date_hdr)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=datetime.now().astimezone().tzinfo)
                except (TypeError, ValueError, OverflowError):
                    date = datetime.now().astimezone()
                pdfs = _collect_pdf_parts(msg)
                html = _html_body(msg)
                if pdfs or (html and _INVOICE_SUBJECT_HINT.search(subject)):
                    yield EmailMessage(
                        message_id=message_id,
                        sender=sender,
                        subject=subject,
                        date=date,
                        html_body=html,
                        pdf_attachments=pdfs,
                    )


def _parse_rfc822_to_email_message(raw_bytes: bytes) -> EmailMessage | None:
    msg = email.message_from_bytes(raw_bytes)
    message_id = _get_message_id(msg)
    if not message_id:
        return None
    sender = msg.get("From", "") or ""
    subject = _decode_header_value(msg.get("Subject", "") or "")
    date_hdr = msg.get("Date", "") or ""
    try:
        date = parsedate_to_datetime(date_hdr)
        if date.tzinfo is None:
            date = date.replace(tzinfo=datetime.now().astimezone().tzinfo)
    except (TypeError, ValueError, OverflowError):
        date = datetime.now().astimezone()
    pdfs = _collect_pdf_parts(msg)
    html = _html_body(msg)
    return EmailMessage(
        message_id=message_id,
        sender=sender,
        subject=subject,
        date=date,
        html_body=html,
        pdf_attachments=pdfs,
    )


def fetch_email_by_message_id(
    host: str,
    user: str,
    password: str,
    message_id: str,
    *,
    mailbox: str = "INBOX",
) -> EmailMessage | None:
    """Fetch one message by RFC822 ``Message-ID`` header (IMAP ``HEADER`` search)."""
    mid = message_id.strip()
    if not mid:
        return None
    with imaplib.IMAP4_SSL(host) as imap:
        imap.login(user, password)
        imap.select(mailbox)
        for candidate in (mid, mid.strip("<>")):
            typ, data = imap.search(None, "HEADER", "Message-ID", candidate)
            if typ == "OK" and data and data[0]:
                nums = data[0].split()
                if not nums:
                    continue
                num = nums[-1]
                typ, msg_data = imap.fetch(num, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, (bytes, bytearray)):
                    continue
                return _parse_rfc822_to_email_message(bytes(raw))
        return None
