"""Canonical mailbox addresses for this project (override via env in the CLI where documented)."""

from __future__ import annotations

# Gmail account that owns billing mail and sends Jack's invoice.
DEFAULT_GMAIL_SENDER = "chaehan.so@gmail.com"

# First real sends / smoke tests - interview default.
DEFAULT_TEST_RECIPIENT = "chaehan.so@virtualfriend.chat"

# Monthly production recipient for the invoice email body ("Hi Jack") and dry-run summary.
PRODUCTION_RECIPIENT_JACK = "jack.copeland@theglugglejugfactory.com"

# Default production To address for run-month without --test-run.
DEFAULT_PRODUCTION_RECIPIENT = PRODUCTION_RECIPIENT_JACK

# CC recipients for the production send.
CC_RECIPIENTS = [
    "Sophie Mahlo <sophie.mahlo@theglugglejugfactory.com>",
    "Rudi Mahlo <rudi.mahlo@theglugglejugfactory.com>",
]

# BCC recipient for the production send (Evernote archive).
BCC_RECIPIENTS = [
    "chaehan.so@gmail.com",
]

# Google Drive folder to move the downloaded invoice PDF into (send action).
GOOGLE_DRIVE_INVOICE_DIR = (
    "/Users/chaehan/Library/CloudStorage/GoogleDrive-chaehan.so@virtualfriend.chat/"
    "My Drive/2 Areas/GluggleJug/GluggleJug GoogleAds"
)

# Google Drive folder for commission PDFs (save / save_commission action).
GOOGLE_DRIVE_COMMISSION_DIR = (
    "/Users/chaehan/Library/CloudStorage/GoogleDrive-chaehan.so@virtualfriend.chat/"
    "My Drive/2 Areas/GluggleJug/GluggleJug Commissions"
)
