# googleads-invoice-glugglejug

Skeleton repository for Gmail → billed Google Ads UI (headed Brave/Chromium) → PDF handling → emailing **[jack.copeland@theglugglejugfactory.com](mailto:jack.copeland@theglugglejugfactory.com)** from **`chaehan.so@gmail.com`**.

Iteration 1 adds a **`src/`** package layout and **pytest** baseline; further slices (Gmail, Selenium, PDF, CLI) live in **[`PLAN.md`](PLAN.md)**.

**Real Mac workflow + manual preflight (Spark, Brave, Dropbox):** **[`docs/REAL_WORKFLOW_AND_PREFLIGHT.md`](docs/REAL_WORKFLOW_AND_PREFLIGHT.md)**.  
**Monthly flow (steps 1 → 4):** **[`docs/BACKWARD_PLAN_AND_INTERVIEW.md`](docs/BACKWARD_PLAN_AND_INTERVIEW.md)**.  
**Constraints & workarounds (why CI ≠ Brave, how we still ship real integration):** **[`docs/CONSTRAINTS_AND_WORKAROUNDS.md`](docs/CONSTRAINTS_AND_WORKAROUNDS.md)**.  
**Fixtures:** small sample HTML/PDF files **in git** under `tests/fixtures/` so CI can test parsers—they are **not** your live invoices (explained in that doc).

**Delivery:** Only **`PLAN.md`** iterations—strict TDD (**failing test → minimal pass → refactor**); no new behavior without a red **`pytest`** first.  
**Merge bar:** fast suite green in CI; headed browser / live mail only where **`PLAN`** and **`pytest` markers** allow.

## Development

Requires **Python 3.12+**. **Use [mamba](https://mamba.readthedocs.io/)** (conda-forge); do **not** use a project-local **`python -m venv`**.

### mamba environment

From the repo root:

```bash
mamba env create -f environment.yml   # first time
# or refresh after editing environment.yml:
mamba env update -f environment.yml --prune

mamba activate googleads-invoice-glugglejug
pip install -e ".[dev]"
pytest
```

Python packaging dependencies stay in **`pyproject.toml`**; **`environment.yml`** only pins the **Python + pip** base from conda-forge.

### Daily use (bash)

**`gig`** = same pattern as **`swim`**: **`export gig=<this-repo>`** and **`alias gig='mamba activate googleads-invoice-glugglejug && cd "$gig"'`** in **`~/.bash_aliases`**—no separate **`.bash`** file.
The **`export`** is **`cd`**’s path; single-quoted **`alias`** so **`"$gig"`** expands when you **run** **`gig`**, not when the alias is defined. **macOS:** load **`~/.bash_aliases`** from **`~/.bash_profile`** (see **`~/.cursor/rules/shell-bash-aliases.mdc`**).

```bash
export gig=/path/to/googleads-invoice-glugglejug
alias gig='mamba activate googleads-invoice-glugglejug && cd "$gig"'
```
CI runs **GitHub Actions** **`setup-python`** + **`pip install -e ".[dev]"`** + **`pytest`** (see `.github/workflows/ci.yml`). **`@pytest.mark.e2e`** browser tests are **skipped in CI** and **skipped locally** unless you set **`RUN_E2E=1`**.

### CLI (`dry-run`)

After **one-time** **`pip install -e ".[dev]"`** in the active mamba env, print **billing URL**, **parsed PDF fields**, and **email/filename** artifacts (no browser, no Gmail). **Jack’s email copy** uses the **billing month** = **full calendar month before “today”** on your Mac (`billing_month_label_for_previous_calendar_month` in code). There is **no** `--month-label`—month and year are not retyped.

**Regression / quick check** (fixtures in repo):

```bash
googleads-invoice dry-run \
  --mail-html tests/fixtures/gmail/billing_mail_happy.html \
  --invoice-pdf tests/fixtures/pdf/invoice_eur_dot_decimal.pdf
```

**Monthly run (real workflow):** **`tests/fixtures`** are for CI only. Export billing **HTML** from **Spark** and save the **PDF** from **Brave**, then point **`dry-run`** at those files:

```bash
export GOOGLEADS_INVOICE_MAIL_HTML="$HOME/path/from/spark/export.html"
export GOOGLEADS_INVOICE_PDF="$HOME/path/from/brave/invoice.pdf"
googleads-invoice dry-run
```

Or pass **`--mail-html`** / **`--invoice-pdf`** instead of env vars. **Spark / Brave** are not automated here—you export/save manually, then run the CLI.

Equivalent: **`python -m googleads_invoice dry-run ...`** (works whenever the package is installed).

### Send test PDF (**Gmail SMTP**, Step 1)

Sends **one** message from **`GOOGLEADS_GMAIL_SMTP_USER`** with **`tests/fixtures/pdf/invoice_eur_dot_decimal.pdf`** (or **`--pdf`**) attached. Subject/body match **`build_email_subject` / `build_email_body`** and the **billing month** rule (same as production copy). **Requires** a Gmail **App password**, not your normal login password.

**Guardrail:** set **`GOOGLEADS_CONFIRM_TEST_SEND=1`** or the CLI exits **2**.

**Credential:** set **`GOOGLEADS_GMAIL_SMTP_APP_PASSWORD`** *or* (**preferred**) **`GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE`** pointing to a local file whose **first line** is the app password — use **`chmod 600`** on that file and never commit it.

```bash
export GOOGLEADS_CONFIRM_TEST_SEND=1
# Sender defaults to chaehan.so@gmail.com if GOOGLEADS_GMAIL_SMTP_USER is unset.
export GOOGLEADS_GMAIL_SMTP_USER='chaehan.so@gmail.com'
export GOOGLEADS_GMAIL_SMTP_APP_PASSWORD='xxxx xxxx xxxx xxxx'
# or: export GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE="$HOME/.gmail-app-password"
# Recipient: omit --to to use chaehan.so@virtualfriend.chat, or set:
# export GOOGLEADS_INVOICE_TO='chaehan.so@virtualfriend.chat'
# For the monthly Jack send: export GOOGLEADS_INVOICE_TO='jack.copeland@theglugglejugfactory.com'
googleads-invoice send-test-pdf
# optional: --to overrides env; --pdf /path/to/other.pdf  --attachment-name custom.pdf
```

### Mail.app draft (Step 2 — macOS)

Opens **Mail.app** with a **new outgoing message**: same **subject**, **body**, and **attachment filename** rules as **`send-test-pdf`** (production copy + **`build_renamed_pdf_filename`**). You click **Send** in Mail—or duplicate the draft into **Spark**. **Requires macOS** (`osascript` + Mail).

**Guardrail:** **`GOOGLEADS_CONFIRM_MAIL_APP_DRAFT=1`**.

```bash
export GOOGLEADS_CONFIRM_MAIL_APP_DRAFT=1
googleads-invoice mail-app-draft
# Same defaults as send-test-pdf for --to / GOOGLEADS_INVOICE_TO; optional: --pdf …
```

### List billing mail (**Gmail API**, Step 3 — READ-ONLY)

Lists recent messages matching the billing-notification search (default **`q=`** matches **`docs/BACKWARD_PLAN_AND_INTERVIEW.md`** / **`GOOGLEADS_GMAIL_BILLING_QUERY`**). Uses **Gmail API** with an OAuth **authorized-user JSON** file — same **`token.json`** style other Google CLI tools write after consent (**`gmail.readonly`** scope). **Does not send mail**; sending stays on **SMTP** (`send-test-pdf`).

```bash
export GOOGLEADS_GMAIL_OAUTH_TOKEN="$HOME/path/to/your-token.json"
googleads-invoice list-billing-mail
# optional: --query 'from:payments-noreply@google.com ...'  --max-results 5
```

**Step 4** (Brave Documents / `live_brave`) is tracked in **PLAN §10.4** and **`docs/BACKWARD_PLAN_AND_INTERVIEW.md`**.

**`googleads-invoice: command not found`:** run **`mamba activate googleads-invoice-glugglejug`**, then **`pip install -e ".[dev]"`** again if entry points changed. The script is under **`$CONDA_PREFIX/bin/googleads-invoice`** on Unix; you can call **`python -m googleads_invoice ...`** if **`PATH`** is wrong.

### Browser / e2e (optional, local)

**Google Ads / billing pages:** use **your Brave** (logged-in profile). **Do not** rely on Cursor’s embedded browser for those URLs.

- **Attach Selenium to running Brave:** start Brave with remote debugging, then use **`build_chrome_options_for_remote_debugging`** / **`chrome_driver_attach`** from **`googleads_invoice.browser_download`** (see **`docs/REAL_WORKFLOW_AND_PREFLIGHT.md`**).
- **Typical macOS one-liner** (then leave Brave open):

```bash
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222
```

- **Env:** **`GOOGLEADS_BROWSER_DEBUGGER_ADDRESS`** (e.g. `127.0.0.1:9222`) in **`.env.example`**.

**Smoke e2e** ( **`RUN_E2E=1 pytest -m e2e`** ) still uses a **fresh** Chrome instance + `file://` fixture by design; that is **not** a substitute for Brave attach on real Ads URLs.

```bash
RUN_E2E=1 pytest -m e2e
# or headless (fixture smoke only):
HEADLESS_E2E=1 RUN_E2E=1 pytest -m e2e
```

**Manual fallback:** open billing in **Brave**, download, then **`googleads-invoice dry-run --invoice-pdf ...`**.

**Live pytest — real Brave + real Spark (your Mac only, never CI)**

1. Start Brave with **`--remote-debugging-port=9222`**, export the monthly deeplink and debugger address, then:

```bash
export RUN_LIVE_BRAVE=1
export GOOGLEADS_BROWSER_DEBUGGER_ADDRESS=127.0.0.1:9222
export GOOGLEADS_BILLING_DEEPLINK='https://c.gle/...'   # from mail; do not commit
pytest -m live_brave tests/test_live_brave_billing.py -q
```

Attaches Selenium to **your** Brave and opens the deeplink in the **current tab** (use a spare tab if needed).

2. **Spark** (macOS): AppleScript checks Spark is installed; optionally point at exported mail HTML:

```bash
export RUN_LIVE_SPARK=1
export GOOGLEADS_SPARK_MAIL_HTML="$HOME/path/billing_export.html"   # optional; second test skips if unset
pytest -m live_spark tests/test_live_spark.py -q
```

Spark has **no** stable automation API in this repo — export the message to HTML yourself, then the test runs **`extract_billing_url`** on disk.

**Remote:** [`https://github.com/SoHu-Labs/googleads-invoice-glugglejug.git`](https://github.com/SoHu-Labs/googleads-invoice-glugglejug.git)

## Contents

| Item | Purpose |
|------|---------|
| `README.md` | Repo overview + local/CI run instructions |
| `docs/REAL_WORKFLOW_AND_PREFLIGHT.md` | Plain vocabulary, Brave/Dropbox flow, manual preflight, screenshot |
| `docs/BACKWARD_PLAN_AND_INTERVIEW.md` | Backward plan 4→1 + interview prompts for Spark/Gmail/Brave |
| `docs/CONSTRAINTS_AND_WORKAROUNDS.md` | Agile table: runtime limits → workarounds → tests |
| `.env.example` | Template for `GOOGLEADS_*` and live-test toggles (copy to `.env`, gitignored) |
| `environment.yml` | **mamba** env (Python 3.12 + pip); app deps via **`pip install -e ".[dev]"`** |
| `PLAN.md` | Goal, backlog, agile iterations, strict TDD + regression posture |
| `pyproject.toml` | Package + pytest config |
| `src/googleads_invoice/` | Application package |
| `tests/` | Fast pytest suite |
| `.github/workflows/ci.yml` | GitHub Actions — pytest |
| `LICENSE` | MIT (SoHu-Labs, 2026) |
| `.gitignore` | Python / env / tooling cruft |

## License

[MIT License](LICENSE) — Copyright (c) 2026 SoHu-Labs.
