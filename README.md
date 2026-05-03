# googleads-invoice-glugglejug

Automates: Gmail billing email → Brave PDF download → parse → email to Jack + Sophie/Rudi → Dropbox.

## Setup

```bash
mamba env create -f environment.yml
mamba activate googleads-invoice-glugglejug
pip install -e ".[dev,oauth]"
```

**Credentials (one-time, stored in `~/.gmail/`):**

| What | How | Env var |
|------|-----|---------|
| Gmail API token (read-only) | `python scripts/get_gmail_token.py` | `GOOGLEADS_GMAIL_OAUTH_TOKEN` |
| SMTP app password | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → save to `~/.gmail/gmail-smtp-app-password` | `GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE` |

> **Send Email:** the VPN must unblock the sender address as bypasser website: `https://smtp.gmail.com`

## CLI

```
googleads-invoice
  run-month              Full flow: Gmail → Brave download → parse → email → Dropbox
  run-month --test-run   Same but sends to test inbox, no CC/BCC
  dry-run                Print fields from local files (no network)
  billing-url-from-gmail Print billing URL from latest Gmail notification
  list-billing-mail      List matching Gmail messages
  live-brave-download    Download PDF from Brave billing page
  send-test-pdf          Send one test PDF via SMTP
  mail-app-draft         Open Mail.app draft (macOS)
```

### Quick start

```bash
# Set env vars once per terminal:
export GOOGLEADS_GMAIL_OAUTH_TOKEN="$HOME/.gmail/gmail_readonly_token.json"
export GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE="$HOME/.gmail/gmail-smtp-app-password"
export GOOGLEADS_GMAIL_SMTP_USER="chaehan.so@gmail.com"

# Test run (sends to your test inbox, no CC):
GOOGLEADS_CONFIRM_RUN_MONTH=1 \
  GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222 \
  googleads-invoice run-month --test-run
```

For production, Brave must be running with `--remote-debugging-port=9222` (or use launchd — see below).

## Monthly scheduling (launchd)

Runs automatically on the 2nd at 05:00 (starts and stops Brave):

```bash
mkdir -p ~/.gmail/logs
ln -sf ~/Software/Prototypes/googleads-invoice-glugglejug/scripts/com.googleads-invoice.monthly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.googleads-invoice.monthly.plist
```

Logs: `~/.gmail/logs/`. Test: `launchctl start com.googleads-invoice.monthly`.

## Tests

```bash
pytest        # 105 pass, 5 skipped (e2e/live markers)
```

## Docs

- [`PLAN.md`](PLAN.md) — backlog, status, pre-flight ritual
- [`docs/`](docs/) — real workflow, constraints, interview

## Contents

| Item | Purpose |
|------|---------|
| `src/googleads_invoice/` | Application package |
| `tests/` | Fast pytest suite |
| `scripts/` | OAuth bootstrapper, launchd plist, wrapper script |
| `docs/` | Workflow docs, constraints, interview |
| `PLAN.md` | Backlog and status |
