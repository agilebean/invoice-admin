"""Canonical mailbox addresses for this project (override via env in the CLI where documented)."""

from __future__ import annotations

# Gmail account that owns billing mail and sends Jack’s invoice.
DEFAULT_GMAIL_SENDER = "chaehan.so@gmail.com"

# First real sends / smoke tests — interview default.
DEFAULT_TEST_RECIPIENT = "chaehan.so@virtualfriend.chat"

# Monthly production recipient for the invoice email body (“Hi Jack”) and dry-run summary.
PRODUCTION_RECIPIENT_JACK = "jack.copeland@theglugglejugfactory.com"
