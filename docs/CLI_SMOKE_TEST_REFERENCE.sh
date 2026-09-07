#!/usr/bin/env bash
# ============================================================================
# invoice-admin  CLI  smoke‑test reference
# ============================================================================
# Copy-paste one block at a time into your terminal.  Every command is a
# one-liner; the comment block above it describes what it does, which env
# vars / credentials are needed, and what output to expect.
#
# Categories (7):
#   A.  HELP / DISCOVERABILITY          (no credentials)
#   B.  LOCAL STATE ONLY                (SQLite / filesystem)
#   C.  LLM‑POWERED INGEST              (LLM keys + optional PDF)
#   D.  GMAIL API (READ)                (GOOGLE_OAUTH_TOKEN)
#   E.  GMAIL SMTP (SEND)               (GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE)
#   F.  IMAP (EMAIL INGEST)             (INVOICE_ADMIN_IMAP_*)
#   G.  BRAVE BROWSER DOWNLOAD          (GOOGLEADS_BROWSER_DEBUGGER_ADDRESS)
#   H.  FULL MONTHLY PIPELINE           (OAuth + SMTP + Brave)
# ============================================================================

set -euo pipefail

# ────────────────────────────────────────────────────────────────────────────
# A.  HELP / DISCOVERABILITY
# ────────────────────────────────────────────────────────────────────────────

# 1. Show all top‑level subcommands available under `invoice`.
#    No credentials, no filesystem access needed.
invoice --help

# 2. Show the flags for `invoice send` and `invoice save`.
#    `send` is client‑scoped (who you bill), `save` is provider‑scoped
#    (whose documents you receive).  Entity flags are optional while
#    exactly one client / one provider flow is configured.
invoice send --help
invoice save --help

# ────────────────────────────────────────────────────────────────────────────
# B.  LOCAL STATE ONLY  (SQLite tracker + filesystem + LLM‑cost log)
# ────────────────────────────────────────────────────────────────────────────

# 3. Print LLM cost report for the last 7 and 30 days.
#    Reads `~/.local/state/invoice_admin/llm_calls.sqlite`.
invoice cost

# 4. List every row in the SQLite invoice tracker (human‑readable table).
#    Add `--type foyer_claim` or `--status failed` to filter.
invoice status

# 5. Run the follow‑up engine *once* against all tracked rows.
#    Checks overdue / stuck rows against the rule schedule and sends
#    ntfy.sh notifications for any that match.  Requires a tracker with rows.
invoice followup

# 6. Reset a `failed` tracker row back to `received` so handlers can
#    pick it up again.  Requires an existing row id from `invoice status`.
#    Replace `<id>` with the real row number.
invoice retry <id> --approve

# 7. Approve a row that was parked in `needs_review` (low classifier
#    confidence, amount over guardrail, etc.).  Restores the original
#    invoice_type from the notes JSON and sets status back to `received`.
#    Replace `<id>` with the real row number.
invoice review <id> --approve

# ────────────────────────────────────────────────────────────────────────────
# C.  LLM‑POWERED INGEST  (needs LLM API keys)
# ────────────────────────────────────────────────────────────────────────────

# 8. Ingest a single PDF from the local filesystem.
#    The LLM extracts structured data, the classifier assigns an invoice_type,
#    and a row is written to the tracker.  The PDF is renamed and moved to
#    the appropriate directory (foyer_claims / sepa_transfers / outgoing).
#    Replace `/path/to/invoice.pdf` with a real PDF.
invoice ingest /path/to/invoice.pdf

# 9. Watch the `~/Documents/Invoices/_inbox/` folder for new PDFs.
#    Polls every 10 s; auto‑ingests each new file.  Ctrl‑C to stop.
invoice watch

# ────────────────────────────────────────────────────────────────────────────
# D.  GMAIL API (READ)  — needs GOOGLE_OAUTH_TOKEN
# ────────────────────────────────────────────────────────────────────────────

# 10. Save Jack Copeland's commission PDF: Gmail search → PDF attachment
#     staged under ~/Downloads → parse EUR amount → rename and move to the
#     commissions folder.  `--dry-run` skips the confirmation prompt and
#     leaves the renamed PDF under ~/Downloads only.
#     Provider key comes from the handler YAML (`commission.provider`).
invoice save --dry-run
invoice save

# ────────────────────────────────────────────────────────────────────────────
# E.  GMAIL SMTP (SEND)  — needs GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE
# ────────────────────────────────────────────────────────────────────────────

# 11. Send the monthly invoice end‑to‑end: Gmail search → Brave PDF download
#     → parse date + EUR → rename → SMTP send to the client (with CC/BCC
#     from the handler YAML).
#     `--dry-run` downloads and prints the fields without sending and does
#     not need an SMTP password.  `--yes` skips the confirmation prompt
#     (used by scripts/run-monthly.sh).
invoice send --dry-run
invoice send
invoice send --yes

# ────────────────────────────────────────────────────────────────────────────
# F.  IMAP EMAIL INGEST  — needs INVOICE_ADMIN_IMAP_HOST / _USER / _PASSWORD
# ────────────────────────────────────────────────────────────────────────────

# 12. Fetch a *single* email by its Spark `readdle-spark://` deep‑link.
#     The URL encodes the RFC‑822 Message‑ID; the command fetches the email
#     over IMAP, extracts any PDF attachment, classifies it, and writes a
#     tracker row.  Replace `<spark-url>` with a real Spark deep‑link.
invoice ingest --email '<spark-url>'

# 13. Poll IMAP UNSEEN for invoice‑bearing emails (those with PDF
#     attachments or invoice‑like subjects).  Auto‑ingests each new
#     message.  Ctrl‑C to stop.  Poll interval defaults to 60 s;
#     override with INVOICE_ADMIN_IMAP_POLL_SECONDS.
invoice watch --source imap

# ────────────────────────────────────────────────────────────────────────────
# G.  BRAVE BROWSER DOWNLOAD  — needs GOOGLEADS_BROWSER_DEBUGGER_ADDRESS
# ────────────────────────────────────────────────────────────────────────────

# 14. Full send with an explicit Brave debugger address override.  Brave
#     must be running with `--remote-debugging-port=9222` (see README
#     "Production send").  The handler reads the port from the YAML
#     (`billing.brave_debug_port`); the env var overrides the address.
GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  invoice send --dry-run

# ────────────────────────────────────────────────────────────────────────────
# H.  FULL MONTHLY PIPELINE  — needs OAuth + SMTP + Brave
# ────────────────────────────────────────────────────────────────────────────

# 15. Same as #11, production, without an interactive prompt.  This is what
#     scripts/run-monthly.sh runs on the 2nd of each month at 05:00.
invoice send --yes