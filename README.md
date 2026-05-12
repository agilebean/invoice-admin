# invoice-admin

PyPI / installable project name: **`invoice-admin`** (import package: `invoice_admin`). The Google Ads–specific CLI is **`googleads-invoice`** (`googleads_invoice.cli:main`; sources under **`src/googleads_invoice/`**); the unified handler CLI is **`invoice`**.

Automates two related flows:

1. **Monthly Google Ads invoice:** Gmail billing email → Brave PDF download → parse → email to Jack + Sophie/Rudi → Dropbox.
2. **Jack commission PDF:** Gmail (commission mail) → PDF attachment staged under **Downloads** (visible in Finder) → parse EUR amount → rename and move to the **commissions** folder (`DROPBOX_INVOICE_DIR` in `addresses.py`). No Brave, no SMTP. Optional Gmail query override: `GOOGLEADS_COMMISSION_QUERY`.

## Setup

```bash
mamba env create -f environment.yml
mamba activate invoice-admin
pip install -e ".[dev,oauth]"
```

After this rename, run **`pip install -e ".[dev,oauth]"` again** so the **`googleads-invoice`** console script is installed. If an old **`billing-glugglejug`** binary is still on your `PATH` from a prior install, remove that file under your env’s `bin/` (it is no longer defined in `pyproject.toml`).

**Credentials (one-time, stored in `~/.gmail/` or `~/.google/`):**

| What | How | Env var |
|------|-----|---------|
| `client_secret.json` (OAuth client) | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Clients → download Desktop app JSON to `~/Downloads/client_secret.json` | *(only during `python scripts/get_oauth_token.py`)* |
| Google API OAuth token (Gmail + Ads) | `python scripts/get_oauth_token.py` | `GOOGLE_OAUTH_TOKEN` |
| SMTP app password | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → save to `~/.gmail/gmail-smtp-app-password` | `GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE` |

`save-commission-pdf` needs **only** `GOOGLE_OAUTH_TOKEN`. `run-month` and `send-test-pdf` also need SMTP (and `run-month` needs Brave with `--remote-debugging-port`).

> **Send Email:** the VPN must unblock the sender address as bypasser website: `https://smtp.gmail.com`

## CLI

```
googleads-invoice      # Google Ads invoice + commission flows (same as former billing-glugglejug)
  run-month                     Full flow: Gmail → Brave download → parse → email → Dropbox
  run-month --test-run          Sends to test inbox, no CC/BCC
  save-commission-pdf           Gmail → commission PDF → Downloads staging → commissions folder (confirm prompt)
  save-commission-pdf --test-run  Skip prompt; renamed PDF lands under ~/Downloads only
  dry-run                       Print fields from local files (no network)
  billing-url-from-gmail        Print billing URL from latest Gmail notification
  list-billing-mail             List matching Gmail messages
  live-brave-download           Download PDF from Brave billing page
  send-test-pdf                 Send one test PDF via SMTP
  mail-app-draft                Open Mail.app draft (macOS)

invoice              # unified entry point → invoice_admin.cli
  ingest <path>                 Classify + move PDF + tracker row
  ingest --email <spark-url>   Fetch by Message-ID over IMAP (see .env.example)
  watch [--source inbox|imap]   Poll local _inbox PDFs (default) or IMAP UNSEEN
  status [--type] [--status]   Tracker listing
  followup                      Run follow-up rules once
  send --client gluggle [--month YYYY-MM]
  retry <id> --approve          failed → received, clear error
  review <id> --approve         needs_review → received + restore type from notes
  cost                           LLM cost report (7 + 30 days)
```

Renamed commission files look like: `2026-03 Commission € 1755.73.pdf` (month from the email subject + year from Gmail `internalDate`; amount from the PDF).

### Quick start

```bash
# Set env vars once per terminal:
export GOOGLE_OAUTH_TOKEN="$HOME/.google/oauth_token.json"
export GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE="$HOME/.gmail/gmail-smtp-app-password"
export GOOGLEADS_GMAIL_SMTP_USER="chaehan.so@gmail.com"

# Test run (sends to your test inbox, no CC):
GOOGLEADS_CONFIRM_RUN_MONTH=1 \
  GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  googleads-invoice run-month --test-run

# Commission PDF only (OAuth; no Brave, no SMTP). Test mode writes to ~/Downloads:
googleads-invoice save-commission-pdf --test-run

# Production: interactive confirm, then Dropbox commissions folder (+ staged file under Downloads first)
googleads-invoice save-commission-pdf
```

For **run-month** production, Brave must be running with `--remote-debugging-port=9222` (or use launchd — see below).

## Monthly scheduling (launchd)

Runs automatically on the 2nd at 05:00 (starts and stops Brave).

If you used the old LaunchAgent label, unload it once, then install the new plist:

```bash
launchctl bootout gui/$(id -u)/com.billing-glugglejug.monthly 2>/dev/null || true
mkdir -p ~/.gmail/logs
ln -sf ~/Software/Prototypes/invoice-admin/scripts/com.invoice-admin.monthly.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.invoice-admin.monthly.plist
```

Logs: `~/.gmail/logs/`. Test: `launchctl kickstart -k gui/$(id -u)/com.invoice-admin.monthly`.

## Tests

```bash
pytest        # fast suite; 5 skipped (e2e/live markers) unless you opt in
```

## Docs

- [`PLAN.md`](PLAN.md) — backlog, status, pre-flight ritual
- [`save_commission_pdf.md`](save_commission_pdf.md) — design for `save-commission-pdf`
- [`docs/`](docs/) — real workflow, constraints, interview

## Contents

| Item | Purpose |
|------|---------|
| `src/googleads_invoice/` | Google Ads–specific invoice flow (import `googleads_invoice`) |
| `tests/` | Fast pytest suite |
| `scripts/` | OAuth bootstrapper, launchd plist, wrapper script |
| `docs/` | Workflow docs, constraints, interview |
| `PLAN.md` | Backlog and status |
