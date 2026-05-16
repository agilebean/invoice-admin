#!/usr/bin/env bash
# ============================================================================
# invoice-admin  CLI  smoke‑test reference
# ============================================================================
# Copy-paste one block at a time into your terminal.  Every command is a
# one-liner; the comment block above it describes what it does, which env
# vars / credentials are needed, and what output to expect.
#
# Categories (6):
#   A.  HELP / DISCOVERABILITY          (no credentials)
#   B.  LOCAL STATE ONLY                (SQLite / filesystem)
#   C.  LLM‑POWERED INGEST              (ANTHROPIC_API_KEY + optional PDF)
#   D.  GMAIL API (READ)                (GOOGLE_OAUTH_TOKEN)
#   E.  GMAIL SMTP (SEND)               (GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE)
#   F.  IMAP (EMAIL INGEST)             (INVOICE_ADMIN_IMAP_*)
#   G.  macOS MAIL.APP                  (macOS only)
#   H.  BRAVE BROWSER DOWNLOAD          (GOOGLEADS_BROWSER_DEBUGGER_ADDRESS)
#   I.  FULL MONTHLY PIPELINE           (OAuth + SMTP + Brave)
# ============================================================================

set -euo pipefail

# ────────────────────────────────────────────────────────────────────────────
# A.  HELP / DISCOVERABILITY
# ────────────────────────────────────────────────────────────────────────────

# 1. Show all top‑level subcommands available under `invoice`.
#    No credentials, no filesystem access needed.
invoice --help

# 2. Show all Google‑Ads subcommands that the unified `invoice googleads`
#    group passes through to the (now merged) googleads_invoice engine.
#    Also proves the S6 passthrough wiring is intact.
invoice googleads --help

# 3. Show the detailed flags for a single Google‑Ads subcommand.
#    Works with *any* googleads subcommand — `dry-run` is the simplest.
invoice googleads dry-run --help

# ────────────────────────────────────────────────────────────────────────────
# B.  LOCAL STATE ONLY  (SQLite tracker + filesystem + LLM‑cost log)
# ────────────────────────────────────────────────────────────────────────────

# 4. Print LLM cost report for the last 7 and 30 days.
#    Reads `~/.local/state/invoice_admin/llm_calls.sqlite`.
invoice cost

# 5. List every row in the SQLite invoice tracker (human‑readable table).
#    Add `--type foyer_claim` or `--status failed` to filter.
invoice status

# 6. Run the follow‑up engine *once* against all tracked rows.
#    Checks overdue / stuck rows against the rule schedule and sends
#    ntfy.sh notifications for any that match.  Requires a tracker with rows.
invoice followup

# 7. Reset a `failed` tracker row back to `received` so handlers can
#    pick it up again.  Requires an existing row id from `invoice status`.
#    Replace `<id>` with the real row number.
invoice retry <id> --approve

# 8. Approve a row that was parked in `needs_review` (low classifier
#    confidence, amount over guardrail, etc.).  Restores the original
#    invoice_type from the notes JSON and sets status back to `received`.
#    Replace `<id>` with the real row number.
invoice review <id> --approve

# ────────────────────────────────────────────────────────────────────────────
# C.  LLM‑POWERED INGEST  (needs ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, …)
# ────────────────────────────────────────────────────────────────────────────

# 9. Ingest a single PDF from the local filesystem.
#    Claude extracts structured data, the classifier assigns an invoice_type,
#    and a row is written to the tracker.  The PDF is renamed and moved to
#    the appropriate directory (foyer_claims / sepa_transfers / outgoing).
#    Replace `/path/to/invoice.pdf` with a real PDF.
invoice ingest /path/to/invoice.pdf

# 10. Watch the `~/Documents/Invoices/_inbox/` folder for new PDFs.
#     Polls every 10 s; auto‑ingests each new file.  Ctrl‑C to stop.
invoice watch

# ────────────────────────────────────────────────────────────────────────────
# D.  GMAIL API (READ)  — needs GOOGLE_OAUTH_TOKEN
# ────────────────────────────────────────────────────────────────────────────

# 11. List recent Google Ads billing notification emails from Gmail.
#     Prints message‑id, thread‑id, and a snippet for each match.
#     `--max-results 3` limits output.
invoice googleads list-billing-mail --max-results 3

# 12. Search Gmail for the most recent billing notification and extract
#     the `payments.google.com` billing URL from its HTML body.
#     `--max-scan 5` controls how many messages to try before giving up.
invoice googleads billing-url-from-gmail --max-scan 5

# 13. Search Gmail for Jack Copeland's commission email, download the
#     attached PDF, parse the EUR amount, rename the file, and save it.
#     `--test-run` skips the confirmation prompt and saves under ~/Downloads.
invoice googleads save-commission-pdf --test-run

# ────────────────────────────────────────────────────────────────────────────
# E.  GMAIL SMTP (SEND)  — needs GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE
# ────────────────────────────────────────────────────────────────────────────

# 14. Send *one* test email with a fixture PDF attached via Gmail SMTP.
#     Requires GOOGLEADS_CONFIRM_TEST_SEND=1 in the environment.
#     Optionally pass `--pdf /path/to/invoice.pdf` to use your own PDF,
#     or `--to someone@example.com` to override the recipient.
GOOGLEADS_CONFIRM_TEST_SEND=1 invoice googleads send-test-pdf

# ────────────────────────────────────────────────────────────────────────────
# F.  macOS MAIL.APP DRAFT  — macOS only
# ────────────────────────────────────────────────────────────────────────────

# 15. Open Mail.app with a new compose window.  Subject, body, and PDF
#     attachment are pre‑filled from the fixture invoice PDF.
#     Requires GOOGLEADS_CONFIRM_MAIL_APP_DRAFT=1.
GOOGLEADS_CONFIRM_MAIL_APP_DRAFT=1 invoice googleads mail-app-draft

# ────────────────────────────────────────────────────────────────────────────
# G.  IMAP EMAIL INGEST  — needs INVOICE_ADMIN_IMAP_HOST / _USER / _PASSWORD
# ────────────────────────────────────────────────────────────────────────────

# 16. Fetch a *single* email by its Spark `readdle-spark://` deep‑link.
#     The URL encodes the RFC‑822 Message‑ID; the command fetches the email
#     over IMAP, extracts any PDF attachment, classifies it, and writes a
#     tracker row.  Replace `<spark-url>` with a real Spark deep‑link.
invoice ingest --email '<spark-url>'

# 17. Poll IMAP UNSEEN for invoice‑bearing emails (those with PDF
#     attachments or invoice‑like subjects).  Auto‑ingests each new
#     message.  Ctrl‑C to stop.  Poll interval defaults to 60 s;
#     override with INVOICE_ADMIN_IMAP_POLL_SECONDS.
invoice watch --source imap

# ────────────────────────────────────────────────────────────────────────────
# H.  BRAVE BROWSER DOWNLOAD  — needs GOOGLEADS_BROWSER_DEBUGGER_ADDRESS
# ────────────────────────────────────────────────────────────────────────────

# 18. Attach to a running Brave (must be started with
#     `--remote-debugging-port=9222`), navigate to the billing deeplink
#     stored in GOOGLEADS_BILLING_DEEPLINK, click the Download button on
#     the top row of the billing documents table, and save the resulting
#     PDF.  Requires GOOGLEADS_CONFIRM_LIVE_BRAVE=1.
GOOGLEADS_CONFIRM_LIVE_BRAVE=1 \
  GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  invoice googleads live-brave-download

# ────────────────────────────────────────────────────────────────────────────
# I.  FULL MONTHLY PIPELINE  — needs OAuth + SMTP + Brave
# ────────────────────────────────────────────────────────────────────────────

# 19. Run the complete monthly send end‑to‑end: Gmail search → Brave PDF
#     download → parse date + EUR → rename → SMTP send to Jack Copeland
#     (with Sophie/Rudi CC, self BCC for Evernote archive).
#     Production mode asks for interactive confirmation.
#     Requires GOOGLEADS_CONFIRM_RUN_MONTH=1 + OAuth + SMTP + Brave.
GOOGLEADS_CONFIRM_RUN_MONTH=1 \
  GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  invoice googleads run-month

# 20. Same as above, but sends to your *test inbox* (no CC/BCC, no
#     Dropbox copy).  Safe for wiring checks.
GOOGLEADS_CONFIRM_RUN_MONTH=1 \
  GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  invoice googleads run-month --test-run

# 21. Same monthly send, but through the `invoice send` handler
#     (unified entry point).  `--client gluggle` is currently the only
#     supported client.  `--month YYYY-MM` overrides the default
#     "previous calendar month" behaviour.
GOOGLEADS_CONFIRM_RUN_MONTH=1 \
  GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  invoice send --client gluggle
