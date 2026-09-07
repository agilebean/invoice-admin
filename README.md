# invoice-admin

PyPI / installable project name: **`invoice-admin`** (import package: `invoice_admin`). The Google Ads flows live under `invoice_admin.googleads`. The legacy `googleads-invoice` console entry and the `invoice googleads` group are removed; everything is one `invoice` CLI.

**Rename:** this repo was **`billing-glugglejug`** on GitHub; it is now **`invoice-admin`**.

Automates two related flows:

1. **Monthly Google Ads invoice:** Gmail billing email → Brave PDF download → parse → email to Jack + Sophie/Rudi → Google Drive.
2. **Jack commission PDF:** Gmail (commission mail) → PDF attachment staged under **Downloads** (visible in Finder) → parse EUR amount → rename and move to the **commissions** folder. No Brave, no SMTP. Optional Gmail query override: `GOOGLEADS_COMMISSION_QUERY`.

## Setup

```bash
mamba env create -f environment.yml
mamba activate invoice-admin
pip install -e ".[dev,oauth]"
```

**Credentials (one-time, stored in `~/.gmail/` or `~/.google/`):**

| What | How | Env var |
|------|-----|---------|
| `client_secret.json` (OAuth client) | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → Clients → download Desktop app JSON to `~/.google/client_secret.json` | *(only during `python scripts/get_oauth_token.py`)* |
| Google API OAuth token (Gmail + Ads) | `python scripts/get_oauth_token.py` | `GOOGLE_OAUTH_TOKEN` |
| SMTP app password | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → save to `~/.gmail/gmail-smtp-app-password` | `GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE` |

`save` needs **only** `GOOGLE_OAUTH_TOKEN`. `send` also needs SMTP and Brave with `--remote-debugging-port`.

> **Send Email:** the VPN must unblock the sender address as bypasser website: `https://smtp.gmail.com`

## CLI

Client and provider keys come from `config/handlers/*.yaml` (`client.key` + `commission.provider`).
Entity flags are optional while exactly one candidate exists; with several, the CLI refuses and
lists the choices. `--client gluggle` is still accepted as an alias of `glugglejug`.

```
invoice                 # unified entry point → invoice_admin.cli
  ingest <path>                 Classify + move PDF + tracker row
  ingest --email <spark-url>    Fetch by Message-ID over IMAP (see .env.example)
  watch [--source inbox|imap]   Poll local _inbox PDFs (default) or IMAP UNSEEN
  status [--type] [--status]    Tracker listing
  followup                      Run follow-up rules once
  send [--client KEY] [--month YYYY-MM] [--dry-run] [--yes]
  save [--provider KEY] [--client KEY] [--month YYYY-MM] [--dry-run]
  retry <id> --approve          failed → received, clear error
  review <id> --approve         needs_review → received + restore type from notes
```

- `send` = monthly invoice to a client (Gmail → Brave download → parse → email → Google Drive).
- `save` = commission PDF from a provider (Gmail → Downloads staging → commissions folder).
- `send --dry-run` downloads and prints the invoice fields, no email. `send --yes` skips the
  confirmation prompt for automated runs. `save --dry-run` skips the prompt and leaves the
  renamed PDF under `~/Downloads` only.
- `save --month YYYY-MM` targets one commission month: narrows the Gmail search to that month's
  subject and verifies the found mail derives the same month, failing loudly otherwise.

Renamed commission files look like: `2026-03 Commission € 1755.73.pdf` (month from the email subject + year from Gmail `internalDate`; amount from the PDF).

### Quick start

```bash
# Set env vars once per terminal:
export GOOGLE_OAUTH_TOKEN="$HOME/.google/oauth_token.json"
export GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE="$HOME/.gmail/gmail-smtp-app-password"
export GOOGLEADS_GMAIL_SMTP_USER="chaehan.so@gmail.com"

# Dry run (parse + print fields, no email, no Google Drive):
invoice send --dry-run

# Commission PDF only (OAuth; no Brave, no SMTP). Dry run writes to ~/Downloads:
invoice save --dry-run

# Production: interactive confirm, then Google Drive commissions folder (+ staged file under Downloads first)
invoice save

# Target a specific commission month (searches by subject month, verifies the match):
invoice save --month 2026-07
```

### Production send

Brave must be closed before running. Start it with:

```bash
open -a "Brave Browser" --args --remote-debugging-port=9222
sleep 3
invoice send
```

`invoice send` asks for confirmation unless you pass `--yes` (used by `scripts/run-monthly.sh`).

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
pytest        # fast suite; e2e/live markers skipped unless you opt in (see tests/conftest.py)
mypy src/invoice_admin/core src/invoice_admin/classify src/invoice_admin/handlers
```

CI runs both after `pip install -e ".[dev]"` (see `.github/workflows/ci.yml`).

## Hand-off checkpoints (product brief SS15)

Before high-risk steps, satisfy these **human** gates (details in **`docs/PROJECT_BRIEF_invoice_handler.md`** SS15):

| Before | Gate |
|--------|------|
| **Foyer** live portal run | Three real ingested invoices: extraction + classifier confidence look right. |
| **SEPA** dry-run on a real bill | Review the logged payload (IBAN, amount, Verwendungszweck) field-by-field. |
| **Retiring** `googleads-invoice` / old send path | Byte-level or documented parity on the same inputs--**explicit OK** before removing the entrypoint. | **Done 2026-09-07:** `googleads-invoice` script, `googleads_invoice` shim, and `invoice googleads` group removed; `invoice send/save --client/--provider` are the only surface. |
| **SEPA live** (`dry_run: false`) | Joint review of **14 days** of dry-run logs vs what you would have typed manually. |

## `invoice_admin` config and env

- **Global + handler YAML:** `config/default.yaml`, `config/handlers/*.yaml` (no secrets in YAML).
- **Secrets and overrides:** copy **`.env.example`** → **`.env`** (gitignored). See commented blocks for **`INVOICE_ADMIN_*`**, **`NTFY_TOPIC`**, **`FOYER_*`**, **`FINTS_PIN`**, IMAP for `invoice ingest --email`, and existing **`GOOGLEADS_*`** / **`GOOGLE_*`** keys.
- **Brave + billing URLs:** do not validate logged-in flows in the IDE browser--use **`docs/REAL_WORKFLOW_AND_PREFLIGHT.md`** and the debugger-attach workflow.

## Docs

| Doc | Role |
|-----|------|
| [`docs/IMPLEMENTATION_PLAN_invoice_handler.md`](docs/IMPLEMENTATION_PLAN_invoice_handler.md) | Milestones, hard rules, **living Implementation status** (resume any LLM here). |
| [`docs/PROJECT_BRIEF_invoice_handler.md`](docs/PROJECT_BRIEF_invoice_handler.md) | Product intent, checkpoints, quality bar. |
| [`docs/REAL_WORKFLOW_AND_PREFLIGHT.md`](docs/REAL_WORKFLOW_AND_PREFLIGHT.md) | Brave preflight, C3/C5-style troubleshooting. |
| [`REFACTOR_PLAN.md`](REFACTOR_PLAN.md) | Code disposition + **swim** patterns (brief SS0c). |
| [`save_commission_pdf.md`](save_commission_pdf.md) | Design for `save-commission-pdf`. |

## Contents

| Item | Purpose |
|------|---------|
| `src/invoice_admin/` | Generic ingest, classify, handlers, follow-up, `invoice` CLI -- includes `googleads/` subpackage |
| `tests/` | Fast pytest suite |
| `scripts/` | OAuth bootstrapper, launchd plist, wrapper script |
| `docs/` | Workflow docs, constraints, interview |
| `PLAN.md` | Backlog and status |
