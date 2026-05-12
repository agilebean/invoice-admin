# Project Brief — invoice-admin

You are refactoring `invoice-admin` (formerly `billing-glugglejug`, recently renamed on GitHub) from a single-purpose outgoing-invoice sender into a generic invoice handler. The new scope: ingest invoices from email or filesystem, classify them, route each to a type-specific handler (Foyer health-insurance claim, SEPA transfer for German tradesman bills, outgoing invoice to clients, future types), track status to completion, and remind Chaehan of pending actions.

This is an **in-place refactor**, not a greenfield rewrite. All current functionality must continue to work — it becomes the `OutgoingInvoiceHandler`. Read this brief fully before any action.

---

## 0. First Action — Study Two Codebases (mandatory)

The "prototypes folder" in this brief refers to `/Users/chaehan/Software/Prototypes/`, a directory on Chaehan's machine containing multiple sibling repos. This refactor has two non-equivalent dependencies:

### 0a. The current code in this repo — preserve and wrap

Read the entire current `invoice-admin` repo (locally at `/Users/chaehan/Software/Prototypes/invoice-admin/`, formerly `billing-glugglejug/`) recursively. It is working software handling outgoing invoices for Chaehan's Google Ads side gig (3% commission on gluggle-jug retail campaigns for a UK client).

In the refactored architecture, this becomes ONE handler — specifically `OutgoingInvoiceHandler`. Most existing code (PDF generation or templating, email sending, invoice numbering, persistence) should be preserved verbatim or with light refactor to fit the new `Handler` interface. Do not rewrite working logic to match a style guide. Do not "improve" what works.

For every meaningful function, class, or module in the current codebase, decide: **wrap as-is**, **lift into shared `core/` with light refactor**, **rewrite (justify in writing)**, or **delete (justify)**.

### 0b. The `swim` repo — mirror the architecture

Read `/Users/chaehan/Software/Prototypes/swim/` recursively. Chaehan considers it a model of clean, modular Python architecture. Study and mirror:

- Folder structure and module boundaries
- Naming conventions (modules, functions, classes, constants)
- How configuration is loaded
- Error handling style (exceptions, logging, recovery)
- Test layout and fixture patterns
- CLI structure
- How concerns are separated (no God objects, no hidden state)
- Type-hint and docstring style

After the refactor, this repo should feel like a sibling to `swim`, not like the pre-refactor `billing-glugglejug`. The current code is the source of *behavior*; `swim` is the source of *form*.

### 0c. Deliverable from M1

Generate `REFACTOR_PLAN.md` in the repo root with two sections:

1. **Current code disposition** — every file/function in the current repo, its classification (wrap / lift / rewrite / delete), and its destination module in the refactored structure.
2. **`swim` patterns adopted** — list specific conventions being mirrored, with one-line justification each (e.g. "config loader pattern from `swim/config/loader.py` — separates schema validation from file I/O").

Surface this to Chaehan before milestone M2 begins. If you would diverge from `swim`'s conventions, ask before doing so.

This is the most important instruction in the brief. Skipping it wastes Chaehan's prior work.

---

## 1. What We're Building

A generic invoice handler with this flow:

```
Input (email or file)
   → Extract structured data (LLM with PDF)
   → Classify invoice type (LLM)
   → Route to type-specific handler (Strategy pattern)
       ├── FoyerClaim          : Playwright submission to Foyer Global Health portal
       ├── SepaTransfer        : python-fints prep against VR Landau → phone TAN approval
       ├── OutgoingInvoice     : current repo functionality, wrapped behind Handler interface
       └── (extensible: utilities, tax, subscriptions, …)
   → Persist to SQLite tracker
   → Followup engine watches tracker state, sends push notifications
```

Input modes:

- **Email** — Spark deep-link to a specific message containing an invoice as attachment or body.
- **File** — PDF dropped into a watched folder (`~/Documents/Invoices/_inbox/` or similar).

Two new handlers must work end-to-end: `FoyerClaim` and `SepaTransfer`. `OutgoingInvoice` is the existing functionality wrapped — it validates that the architecture genuinely generalizes, and must produce byte-identical (or deliberately-and-documented-differently) output compared to the current code.

Adding a fourth handler later must be: one class implementing the `Handler` interface + one YAML config + a classifier example. Not a refactor.

---

## 2. User Context

Chaehan is a 54-year-old Korean-German founder of Virtual Friend (Delaware C-corp). He lives in 1–3 month rotations across countries (Germany, Korea, US, Mexico, Australia). His bank for SEPA transfers is **VR Landau** (Volksbank Raiffeisenbank, BLZ 54061170). His health insurance is **Foyer Global Health** (expat policy, customer portal at `portal.foyerglobalhealth.com` — verify at build time).

He explicitly calls Foyer claims and Handwerker bills his "scarrends" (scary errands). Anxiety-reduction is a primary goal, not just time savings. The system should fail safely and predictably; surprise behavior on money-moving paths is the worst possible outcome.

He pays for software with a credit card; he does not pay for SaaS automation tools. This is a personal repo, single-user, run from his laptop or a small VPS.

---

## 3. Hard Constraints

- **PSD2 SCA wall (regulatory).** Every outgoing SEPA transfer triggers a SecureGo+ TAN on Chaehan's phone. There is no software workaround — this is EU Directive 2015/2366 RTS Art. 4. The `SepaTransfer` handler prepares the transfer fully (IBAN, amount, Verwendungszweck) and stops at `status='awaiting_tan'`. A push notification reminds him to tap-approve on his phone.
- **Money safety guardrails.** `MAX_AUTO_AMOUNT_EUR = 2000` enforced in code (configurable but conspicuous). Transfers above the threshold prepare to status `needs_review`, do not dispatch to FinTS, and notify Chaehan. **Dry-run mode is the default for the first 14 days** — `SepaTransfer` logs what it would do without calling `python-fints` dispatch. Switching off dry-run is a deliberate config edit, not a CLI flag with a default of False.
- **Preserve outgoing-invoice behavior.** Whatever the current `googleads_invoice` code does for the gluggle-jug client must continue to work identically through the new `OutgoingInvoiceHandler`. Any behavioral change is intentional, justified in a commit message, and surfaced to Chaehan.
- **Idempotency.** Same email Message-ID or same file hash must never produce a duplicate tracker row. The classifier and handlers must be safe to retry.
- **No silent failures on money paths.** Any error in `SepaTransfer` or `FoyerClaim` writes to the tracker with `status='failed'`, a structured error blob, and triggers a push notification. The pipeline does not catch-and-continue silently for these handlers.

---

## 4. Architecture — Modules

Mirror `swim`'s layout conventions. The structure below is a starting sketch; adjust to match `swim`'s patterns where they differ.

```
core/
  llm.py                # LLM provider abstraction (reuse from Project B if available)
  pdf.py                # PDF → structured data via Claude native PDF support
  imap.py               # Email collection (reuse from Project B)
  spark_link.py         # Spark deep-link generator (reuse from Project B)
  tracker.py            # SQLite-backed invoice tracker
  notify.py             # Push notifications (ntfy.sh default, Pushover optional)
  config.py             # YAML config loader (mirror swim's pattern)
  errors.py             # Domain exceptions

sources/
  email_source.py       # Watches IMAP for invoice-bearing emails
  file_source.py        # Watches a filesystem folder for new PDFs

classify/
  classifier.py         # LLM classification: invoice type + confidence
  prompts.py            # Classification + extraction prompts

handlers/
  base.py               # Handler protocol/ABC; common helpers
  foyer_claim.py        # Playwright automation against Foyer portal
  sepa_transfer.py      # python-fints SEPA transfer prep against VR Landau
  outgoing_invoice.py   # Existing repo functionality, wrapped

followup/
  engine.py             # Status transitions, overdue detection, notifications
  schedules.py          # Cron expressions per status

cli.py                  # invoice ingest <path|message-id> | watch | status | followup
```

Each module:

- Standalone importable, no circular imports.
- No module-level network or I/O.
- Pure functions where possible; side effects pushed to edges.
- Type-hinted (`mypy --strict` clean on `core/`, `classify/`, `handlers/`).
- Tested in isolation with fixtures, not live network.

---

## 5. LLM Provider Layer

Reuse the `core/llm.py` from Project B (the Topic Summary engine) if that repo is present and stable. If not, build the same abstraction here using `litellm`. Aliases:

```python
MODEL_ALIASES = {
    "fast":  "claude-haiku-4-5",       # classification, simple extraction
    "smart": "claude-opus-4-7",        # PDF extraction with ambiguity, edge cases
    "cheap": "deepseek/deepseek-chat", # bulk fallback
    "local": "ollama/llama3.1:70b",    # offline fallback
}
```

Verify current Anthropic model strings at build time. Log every call to a SQLite `llm_calls` table.

**PDF extraction**: send the PDF directly to Claude (native PDF support) rather than OCR-then-text. Handles scanned handwerker bills better than `pdfplumber` for messy real-world inputs.

---

## 6. Tracker Schema (SQLite)

```sql
CREATE TABLE invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingested_at     TEXT NOT NULL,
    source_type     TEXT NOT NULL,           -- 'email' | 'file'
    source_ref      TEXT NOT NULL UNIQUE,    -- message-id or file SHA256
    invoice_type    TEXT,                    -- 'foyer_claim' | 'sepa_transfer' | 'outgoing_invoice' | …
    classifier_conf REAL,                    -- 0..1
    vendor          TEXT,
    invoice_date    TEXT,                    -- ISO 8601
    due_date        TEXT,
    amount          REAL,
    currency        TEXT,                    -- 'EUR', 'USD', …
    iban            TEXT,
    bic             TEXT,
    verwendungszweck TEXT,
    pdf_path        TEXT,                    -- post-rename absolute path
    status          TEXT NOT NULL,           -- see status machine below
    submitted_at    TEXT,
    approved_at     TEXT,                    -- TAN approval moment (best-effort)
    paid_at         TEXT,
    reimbursed_at   TEXT,
    error           TEXT,                    -- JSON blob if status='failed'
    notes           TEXT
);

CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_type ON invoices(invoice_type);
```

If the current repo already maintains a sent-invoices ledger or numbering store, integrate it INTO this tracker rather than running a parallel store. Migrate existing rows in M6.

Status machine (per handler):

- **FoyerClaim**: `received → classified → submitting → submitted → reimbursed | failed | needs_review`
- **SepaTransfer**: `received → classified → prepared → awaiting_tan → paid | failed | needs_review`
- **OutgoingInvoice**: map current repo's existing semantics onto this vocabulary; do not invent new statuses.

`needs_review` is the human-in-loop bucket: low classifier confidence, amount over guardrail, IBAN validation fail, etc.

---

## 7. File Handling

- **Ingest format**: any PDF; Claude does the extraction.
- **Rename convention**: `YYYY-MM-DD_<vendor-slug>_<amount><CCY>.pdf`. Example: `2026-05-12_Klempner-Mueller_487EUR.pdf`. Slugify aggressively (ASCII, lowercase, hyphens).
- **Storage tree**:
  ```
  ~/Documents/Invoices/
    _inbox/              # file_source watches this
    foyer_claims/<YYYY>/
    sepa_transfers/<YYYY>/
    outgoing/<YYYY>/
    _failures/<YYYY-MM-DD>/   # failed extractions, with error log
  ```
- The root path is config-driven. Chaehan rotates machines; the path must be portable.

---

## 8. Handler Specifics

### 8a. FoyerClaim

- Playwright against `portal.foyerglobalhealth.com` (verify current URL).
- Persist session with `storage_state` to a config-driven path, encrypted at rest if feasible.
- Expect login to need 2FA the first run; subsequent runs ride the stored state until it expires.
- Fill claim form fields from tracker row: date, doctor/vendor, amount, currency. Upload the renamed PDF.
- Capture confirmation number; write to tracker `notes` and screenshot to `_artifacts/<id>.png`.
- Selector breakage is expected ~monthly. Locator strategy: prefer ARIA roles and label text over CSS classes. Wrap critical actions in `expect(...).to_be_visible()` with generous timeouts.

### 8b. SepaTransfer

- `python-fints` against VR Landau:
  - FinTS endpoint: `https://hbci-pintan.gad.de/cgi-bin/hbciservlet` (verify at build time)
  - BLZ: `54061170`
  - Credentials and PIN in `.env`, never logged
  - TAN mechanism: `decoupledTAN` (SecureGo+ push to phone)
- Validate IBAN structurally (`schwifty` library or manual mod-97 check) BEFORE submitting to FinTS.
- Prepare transfer → set status `awaiting_tan` → push notification: "Tap to approve €X to <vendor> in SecureGo+".
- Followup checks `awaiting_tan` rows older than 4 hours and re-notifies.
- After detection of incoming statement matching the transfer (best-effort via FinTS account-statement query), mark `paid`.

### 8c. OutgoingInvoice (wraps current repo functionality)

- Wrap the current `googleads_invoice` send logic behind the `Handler` interface defined in `handlers/base.py`.
- Triggered manually for now (not auto-classified from inbound emails), via `invoice send --client gluggle --month 2026-04`.
- All gluggle-jug-specific config (UK retailer, product line, 3% commission, recipient email, invoice template) lives in a single YAML (`config/handlers/outgoing_gluggle.yaml`), not scattered across code.
- Preserve current invoice numbering. If the current repo has a JSON or text-file ledger of sent invoices, migrate it into the SQLite tracker on first run via `scripts/migrate.py`, keeping the old file as a backup.
- Parity check (M6): a test invoice sent through the new pipeline must match current output byte-for-byte (or with deliberate, documented differences). Compare against a recent real sent invoice as fixture.

---

## 9. Notifications

- Default channel: **ntfy.sh** (free, no account, one topic = one secret URL). Chaehan's topic name in `.env`.
- Optional: **Pushover** (paid, more reliable). Implement behind the `notify.py` abstraction; switching is a config flag, not a code change.
- Trigger points (initial set):
  - `SepaTransfer` enters `awaiting_tan` → "Approve €X to <vendor>"
  - `awaiting_tan` older than 4 hours → re-nag
  - Any handler → `failed` → error summary
  - Any handler → `needs_review` → reason
  - Tracker contains overdue invoices (due_date passed, status not terminal) → daily digest at 09:00 local

---

## 10. Spark Deep-Links

Same scheme as Project B (verify at build time, Readdle has changed this before):

```
readdle-spark://openmessage?messageId=<URL-encoded RFC822 Message-ID with angle brackets>
```

Used in:

- Tracker UI / CLI output (`invoice status` lists pending items with clickable Spark links)
- Notification body (when the source was an email)
- Failure reports

Always include a plain fallback (sender + subject + date as text) for cases where the scheme doesn't fire.

---

## 11. Target Repo Structure

After refactor. Mirror `swim`'s top-level conventions; override the sketch below where `swim` differs.

```
.
├── README.md                   # update to reflect rename from billing-glugglejug + new scope
├── REFACTOR_PLAN.md            # M1 deliverable, see section 0c
├── pyproject.toml              # rename package to invoice_admin; bump version
├── .env.example
├── .gitignore
├── config/
│   ├── default.yaml
│   ├── handlers/
│   │   ├── foyer.yaml
│   │   ├── sepa_vr_landau.yaml
│   │   └── outgoing_gluggle.yaml
│   └── classifier_examples.jsonl
├── core/
├── sources/
├── classify/
├── handlers/
├── followup/
├── tests/
│   ├── fixtures/
│   │   ├── invoices/
│   │   └── emails/
│   └── …
├── scripts/
│   ├── migrate.py              # one-time: import existing sent-invoices ledger into tracker
│   └── seed_examples.py
├── src/
│   └── googleads_invoice/      # Google Ads–specific flow (`import googleads_invoice`; `googleads-invoice` CLI)
```

CLI surface:

```
invoice ingest <path|spark-link>
invoice watch
invoice status [--type X] [--status Y]
invoice followup
invoice send --client gluggle --month 2026-04
invoice retry <id>
invoice review <id>
```

The CLI entry point name (`invoice`) and the package name (`invoice_admin`) are intentionally different: the package is what you import, the command is what you type. Match `swim`'s convention if it differs.

---

## 12. Milestones

- **M1 (day 1)** — Read current repo + `swim`. Commit `REFACTOR_PLAN.md`. Surface to Chaehan. No code changes yet beyond scaffolding the target structure as empty modules.
- **M2 (day 2)** — Core: tracker, config, LLM abstraction (reused if Project B exists), PDF extraction working on three real invoices from `tests/fixtures/`. Existing outgoing-invoice code still runs on the old entry point — do not break it yet.
- **M3 (day 3)** — Classifier with confidence threshold. Email and file sources. End-to-end ingest writes tracker rows with `status='classified'`.
- **M4 (day 4–5)** — `FoyerClaim` handler. Real run against the actual portal with Chaehan supervising. Confirmation captured.
- **M5 (day 5–6)** — `SepaTransfer` handler in **dry-run only**. Verify it would produce the correct SEPA payload against a real Handwerker bill. Do not yet enable live dispatch.
- **M6 (day 6–7)** — Wrap existing outgoing-invoice code as `OutgoingInvoiceHandler`. Migrate ledger into tracker. Run parity check: new pipeline output vs. recent real sent invoice. Retire the old entry point only after parity passes.
- **M7 (day 7)** — Followup engine, notifications, README rewrite (including rename history note), status CLI polish.
- **Post-M7** — After 14 days of dry-run, Chaehan flips the `SepaTransfer` live flag.

Total budget: aim for **under 2500 LOC of new code** (excluding preserved outgoing-invoice code, fixtures, templates, configs). The preserved code should be a substantial fraction of the `OutgoingInvoice` path.

---

## 13. Quality Bar

- **`swim`-grade architecture.** If the structure here conflicts with `swim`'s, default to `swim`. Ask Chaehan before diverging.
- **Type hints + mypy strict** on `core/`, `classify/`, `handlers/`. Best-effort elsewhere.
- **Tests for every handler** with fixtures, not live calls. Playwright tests use saved traces. FinTS tests mock the dialog.
- **No PII in fixtures.** Scrub real invoices before committing.
- **Logging.** Structured (JSON lines) to `~/.local/state/invoice_admin/log.jsonl`. One line per significant event.
- **Cost dashboard.** `invoice cost` prints last 7/30 days of LLM spend by handler.
- **Resumable.** Killing the process mid-flight and restarting must not corrupt state. Tracker writes are atomic.
- **No regression on outgoing invoices.** Until M6 parity passes, the old send path remains callable. Removing it is the last step, not the first.

---

## 14. What NOT to Do

- No web UI. CLI + push notifications + Spark links is the entire UX surface.
- No multi-user logic, no accounts, no auth (beyond the secrets Chaehan provides).
- No frameworks for their own sake. SQLite + cron + `litellm` is enough.
- No silent rewrites of existing code. Wrap, justify, preserve behavior.
- No deviation from `swim`'s conventions without asking first.
- No catch-all `except Exception: pass` anywhere. Especially not in `handlers/`.
- No fictional confirmation numbers, IBANs, or amounts in tests. Use clearly fake values (e.g. `DE00 0000 0000 0000 0000 00`).
- No enabling `SepaTransfer` live dispatch before the 14-day dry-run window has passed.
- No removing the old outgoing-invoice entry point before M6 parity passes.

---

## 15. Hand-off Checkpoints

**Before M4 (FoyerClaim live run):** show Chaehan three classified-and-extracted invoices from his real inbox/folder. Confirm extraction accuracy and classifier confidence calibration before touching the Foyer portal.

**Before M5 (SepaTransfer dry-run):** show Chaehan the SEPA payload (IBAN, amount, Verwendungszweck) the system would produce for a real Handwerker bill. Confirm field-by-field. This is the highest-risk handler; over-verify here.

**Before M6 (retire old send path):** show Chaehan the byte-diff between a current-code output and the new-pipeline output for the same input. Get explicit OK before deleting the old entry point.

**Before flipping `SepaTransfer` live:** review the 14-day dry-run log together. Identify any case where dry-run output differs from what Chaehan would have entered manually.

---

## 16. Open Questions to Resolve at Build Time

1. **`swim` repo conventions** — confirm naming, layout, config-loading pattern, test-fixture style. Do not guess; read the code.
2. **Current repo boundaries** — what is genuinely reusable vs. tightly coupled to the gluggle-jug client's specifics? The latter goes into `outgoing_gluggle.yaml`, not into shared code.
3. **Foyer portal URL and login flow** — verify by inspection. Note any captcha or 2FA quirks.
4. **VR Landau FinTS endpoint** — confirm `https://hbci-pintan.gad.de/cgi-bin/hbciservlet` is current. Test connection in M5 before building the SEPA payload logic.
5. **Spark URL scheme** — confirm current format by testing on Chaehan's device.
6. **Ollama availability** — does Chaehan run a local Ollama? If yes, which models. If no, document `local` alias as aspirational.
7. **Project B reuse** — is the Topic Summary engine repo already built? If yes, import `core/llm.py`, `core/imap.py`, `core/spark_link.py` rather than reimplementing. Confirm path with Chaehan.
8. **Existing ledger format** — what does the current repo use to track sent invoices? Plain text, JSON, SQLite, none? Determines `scripts/migrate.py` scope.

Resolve these in M1. Flag what you cannot resolve and proceed with reasonable defaults.
