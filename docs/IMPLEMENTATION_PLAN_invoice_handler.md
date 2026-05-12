# Implementation Plan — invoice-admin Refactor

> Written for a coding LLM. Every instruction is prescriptive. No ambiguity. No room for creative interpretation. Read the **Agent execution contract** (section immediately below), then the rest of this file, before writing any code.

---

## Agent execution contract (mandatory — read before §0)

This block exists so a maintainer can prompt with **only**: *“Read `docs/IMPLEMENTATION_PLAN_invoice_handler.md` and do the next step.”* The agent must obey this contract **before** writing or changing code.

### 1) Single source of truth (conflict order)

When instructions conflict, resolve in this **strict order** (higher wins):

1. **Explicit text in the user’s current chat** that names a milestone (e.g. “implement **M5.1** only”) or a file path.
2. **This file** (`IMPLEMENTATION_PLAN_invoice_handler.md`) — milestones **§2**, hard rules **§3**, tests **§4**, ordered checklist **§5**.
3. **`docs/PROJECT_BRIEF_invoice_handler.md`** — product facts; if it disagrees with **this file** on *how* `invoice_admin` should behave, **this file wins**.
4. **`PLAN.md`** — agile ritual, CI policy, **P1** (merge `googleads_invoice` into `invoice_admin`), and the **Google Ads backward plan** (`googleads_invoice` / `run-month`). Those are **mostly out of scope** for M1–M7 unless a milestone here explicitly says to touch them.
5. **`docs/BACKWARD_PLAN_AND_INTERVIEW.md`** — narrative context only; **not** an alternate task list for `invoice_admin` milestones.

**Brave / Google Ads / billing URLs:** If the task touches headed browser, debugger attach, or “does this URL work while logged in”, also obey **`.cursor/rules/brave-for-google-ads.mdc`** in the repo (source of truth for that class of work).

### 2) Vocabulary — words that confuse LLMs

| Term | **Means in this repo** | **Does not mean** | **Primary code / docs** |
|------|------------------------|-------------------|---------------------------|
| **Follow-up / followup** | The **`invoice_admin.followup`** package: rules in `followup/schedules.py`, engine in `followup/engine.py`, driven off **tracker** row age + status; may call **`notify`**. | “Reply in Chat”, “open a GitHub follow-up”, “email the user later”. | §2 **M7**; `src/invoice_admin/followup/` |
| **Tracker** | SQLite **invoice ledger** for `invoice_admin` (idempotency, statuses, errors). | GitHub issue tracker. | §2 **M2.3**; `core/tracker.py` |
| **Handler** | `invoice_admin.handlers.*` implementing the **handler Protocol** for a concrete `invoice_type`. | Arbitrary “event handler” in UI. | §2 **M4–M6** |
| **Dry run** | Config + handler behavior that **must not** move real money (SEPA: **default dry-run**; see **§3** and Post-M7). | “pytest dry run” or “print only”. | YAML `dry_run`; §2 **M5**, **Post-M7** |
| **`googleads_invoice`** | **Separate package** under `src/googleads_invoice/` (Jack / Google Ads monthly, commission PDF, `run-month`, etc.). | Part of `invoice_admin` until **P1** is explicitly approved in `PLAN.md`. | `PLAN.md` P1; §2 **M6** wrapper only |

### 3) Canonical maintainer prompts (copy/paste)

Use **one** of these shapes; do not invent new scope sentences.

- **Next step (default):**  
  *“Read `docs/IMPLEMENTATION_PLAN_invoice_handler.md` (including the Agent execution contract). Run the full fast `pytest` suite. Implement the **next** open row in **§5 Summary — Step Order** that is not yet satisfied in the codebase. Do not start P1. Stop when tests are green and list what you changed.”*

- **Named milestone only:**  
  *“Read the implementation plan. Implement **M4.2** exactly as written in §2. No other milestones. Tests must stay green.”*

- **Bugfix / regression:**  
  *“Read §3 Hard Rules and §4 Test Strategy. Add a **failing** test that reproduces [symptom], then minimal production fix. Do not change milestones not listed: [Mx.y].”*

If the user’s message is vague and **does not** select a milestone, the agent asks **exactly one** clarifying question: *“Should I continue from §5 next open step, or implement milestone **M\_\_.\_**?”* — then **stop** until answered.

### 4) Permissions, environment, and “what to run”

| Requirement | Rule |
|-------------|------|
| **Python** | **3.12+** (`requires-python` / CI). |
| **Env** | **`mamba`** env from repo **`environment.yml`** (name **`invoice-admin`**). Install app + dev deps: **`pip install -e ".[dev]"`**. |
| **Tests (definition of done)** | Full fast suite: **`python -m pytest`** at repo root after install. Must match **`.github/workflows/ci.yml`** (`pip install -e ".[dev]"` then **`pytest`**). |
| **Markers** | **`@pytest.mark.e2e`**, **`live_brave`**, **`live_spark`**, etc. — **skipped by default** in CI and locally unless env vars documented in **`PLAN.md`** / **`tests/conftest.py`**. Do **not** turn them on in CI without maintainer decision. |
| **Network / live APIs** | **Not** part of default “green”. No milestone may require live Gmail, live Brave, or real FinTS **for the default pytest run** unless that milestone explicitly says so **and** uses markers/skips. |
| **Secrets** | **Never** commit secrets. **Never** put FinTS PIN, IMAP password, API keys, or real IBANs in YAML or code. Only **`/.env.example`**-style placeholders + env var names. Real values live in **`.env`** (gitignored) or OS keychain — see **§3 Security**. |

### 5) Caveats matrix (non-exhaustive — if touched, read the row’s “read” cell)

| Topic | Hard rule | If you violate it |
|-------|-----------|-------------------|
| **SEPA / money** | **Dry-run** until Post-M7 checklist; **`MAX_AUTO_AMOUNT_EUR`**; no silent money failures | Re-read **§3 Money safety** + **M5** warnings |
| **Brave / Google Ads** | Do **not** validate logged-in billing URLs in Cursor’s embedded browser; use **debugger attach** workflow | Read **`.cursor/rules/brave-for-google-ads.mdc`** + **`docs/REAL_WORKFLOW_AND_PREFLIGHT.md`** |
| **Spark / IMAP** | Spark URL format may change; IMAP is provider-specific | **M2.8** warning; **`.env.example`** for `INVOICE_ADMIN_IMAP_*` |
| **Idempotency** | Same file hash / same `message_id` → no duplicate tracker rows | **§3 Idempotency** |
| **Scope** | Implement **only** the named milestone (or §5 next step). No drive-by refactors, no “while we’re here” | Repo **CLAUDE.md** scope discipline |

### 6) How to phrase *caveats* back to the human (required closing block)

After every slice, end with this **fixed skeleton** (fill brackets; omit lines that are N/A):

```text
## Slice summary
- Milestone: [e.g. M4.2]
- Files touched: [list]

## Verification
- Command: python -m pytest
- Result: [N passed, M skipped]

## Caveats / follow-ups for the maintainer
- **Follow-up (code):** [tracker tickets / next milestone ids — or “none”]
- **Follow-up (ops):** [env vars to set / Brave port / manual smoke — or “none”]
- **Risks:** [money / PII / provider drift — or “none”]
```

Use **“Follow-up (code)”** only for **the next milestone or a concrete bug** — not generic advice. Use **“Follow-up (ops)”** for anything requiring **human credentials or a real browser**.

### 7) What this plan does **not** automate

- **P1** (merge `googleads_invoice` into `invoice_admin`) — see **`PLAN.md`**. **Do not start** unless the user explicitly overrides this contract in chat.
- **Production SEPA go-live** — only after **Post-M7** human checklist in §2; config flip, not new code.
- **Changing Jack’s Google Ads mail/send pipeline** beyond what **M6** wrapper needs — that is **`googleads_invoice`** + **`PLAN.md`** backward plan, not M3 file ingest.

### 8) Navigation map (for search / skimming)

| Need | Go to |
|------|--------|
| Milestone steps, warnings, patterns | **§2 Implementation Steps — By Milestone** |
| Non-negotiables | **§3 Hard Rules** |
| What tests to add / markers | **§4 Test Strategy** |
| Ordered checklist for dumb execution | **§5 Summary — Step Order for the Coding LLM** |
| File naming nitpicks | **§6 File Naming Convention Reference** |
| External refs | **§7 References** |

---

## 0. Prerequisite Knowledge (Read First)

### 0a. What you inherit

The current repo at `/Users/chaehan/Software/Prototypes/invoice-admin/` is working, tested software. It automates sending Google Ads invoices to one client (Jack at The Gluggle Jug Factory) and saving his commission PDFs. The **PyPI / distribution name** is `invoice-admin` (import `invoice_admin`); unified CLI is **`invoice`**. The Google Ads flows live in package **`googleads_invoice`** (sources under **`src/googleads_invoice/`**), invoked as **`googleads-invoice`** (console) or `python -m googleads_invoice`.

**Current source tree** (`src/googleads_invoice/` — import name `googleads_invoice`):
```
__init__.py              # __version__ = "0.0.0"
__main__.py              # python -m googleads_invoice
cli.py                   # argparse CLI (689 lines, 8 subcommands)
pipeline.py              # DryRunReport dataclass + run_dry_run()
run_month.py             # run_month() orchestrates full Gmail→Brave→parse→SMTP flow
addresses.py             # Hardcoded email addresses + Dropbox path
billing_period.py        # billing_month_label_for_previous_calendar_month()
billing_url.py           # extract_billing_url(html) from Gmail HTML
browser_download.py      # Selenium/Brave helpers for PDF download
commission_pdf.py        # parse_commission_pdf_amount(source)
gmail_api_backend.py     # GmailApiReadBackend (OAuth, list_messages, get HTML, get PDF attachment)
gmail_facade.py          # GmailBackend Protocol + GmailFacade + GmailTransportError
gmail_smtp.py            # SmtpGmailBackend (SMTP send with app password)
invoice_artifacts.py     # InvoiceOutputFields, build_renamed_pdf_filename/email_subject/body
invoice_pdf.py           # parse_invoice_pdf(source) → (date, amount) via pypdf
live_brave_download.py   # Attach to Brave, navigate billing URL, download PDF
live_brave_trace.py      # Save HTML + PNG traces from Brave
mail_app_draft.py        # Open Mail.app draft via AppleScript
save_commission_pdf.py   # Gmail search → download commission PDF → parse → move to Dropbox
```

**Tests**: 22+ test files in `tests/`, using pytest, with HTML/PDF fixtures in `tests/fixtures/`.

**Persistence:** The **`googleads_invoice`** monthly/commission flows described in the tree above are largely **stateless** (no first-class invoice ledger there). The **`invoice_admin`** package introduced by this plan **adds** a SQLite **tracker** (`core/tracker.py`) for ingest/handler/follow-up state — see **§2 M2.3** and the project brief. Do not claim “no database” when editing `invoice_admin` code.

### 0b. What you mirror (the `swim` repo at `/Users/chaehan/Software/Prototypes/swim/`)

These are the patterns you MUST replicate. Deviating from these requires explicit justification.

| Pattern | Location in swim | How to mirror |
|---------|-----------------|---------------|
| **PyPA `src` layout** | `src/swim/` | Put everything under `src/invoice_admin/` |
| **Frozen dataclass config** | `swim/config/__init__.py`, `config/paths.py` | `InvoiceConfig` frozen dataclass loaded from YAML via `repo_root()` discovery |
| **Runtime root detection** | `swim/common.py:repo_root()` | Walk up from CWD looking for `pyproject.toml`, then from `__file__` |
| **Thin `__main__.py`** | `swim/__main__.py` (6 lines) | Just import and call `main()` from `cli/` |
| **argparse with subcommands** | `swim/cli/analyze.py` | Positional action arg, dispatch to `_run_*()` functions |
| **`conftest.py` fixture functions** | `swim/tests/conftest.py` | Shared fixtures: `repo_root`, `data_dir`, `config_dir`, artifact fixtures |
| **Mini test fixtures** | `swim/tests/fixtures/` | Small YAML/CSV/PDF files for isolated handler tests |
| **Defensive `_safe_float` pattern** | `swim/common.py` | Return `None` on parse failure; never raise from data parsing |
| **YAML for data, not code** | `swim/config/*.yaml` | Handler configs are pure data; behavior lives in Python |
| **`__all__` in `__init__.py`** | `swim/drills/__init__.py` | Explicit public API via `__all__` |
| **`from __future__ import annotations`** | Every `.py` file in swim | Put at the top of every new `.py` file |
| **Union types with `\|`** | Throughout swim | `Path \| None`, `str \| None`, not `Optional[str]` |
| **Module-level docstrings** | Every module in swim | Single-line description of what the module does |

### 0c. Decisions already made (do not re-litigate)

1. **Handler interface = Protocol**, not ABC. The current code already uses Protocols (`GmailBackend`). Match that.
2. **Keep pytest**, not unittest. 22 tests already written. Do not rewrite them.
3. **Project B does not exist.** Build `core/llm.py`, `core/imap.py`, `core/spark_link.py` from scratch.
4. **OutgoingInvoiceHandler wraps BOTH flows**: send invoice to client AND save commission PDF. They are the same client, same handler.
5. **No `scripts/migrate.py`**. There is no existing ledger to migrate.
6. **Package name**: `invoice_admin` (underscore, importable). **CLI command**: `invoice` (what the user types).

---

## 1. Target Structure (Build This)

After implementation, the repo will look like:

```
invoice-admin/
├── README.md
├── REFACTOR_PLAN.md                    # Only if M1 was asked for
├── pyproject.toml                      # Updated: package name, CLI entry point, deps
├── .env.example                        # Updated: new vars for ntfy.sh, FinTS, Foyer
├── .gitignore                          # Updated: SQLite files, encrypted sessions
├── config/
│   ├── default.yaml                    # Global defaults: paths, thresholds, model aliases
│   └── handlers/
│       ├── outgoing_gluggle.yaml       # All gluggle-jug-specific config (migrated from addresses.py + hardcoded strings)
│       ├── foyer.yaml                  # Foyer portal URL, credential paths, locator timeouts
│       └── sepa_vr_landau.yaml         # VR Landau FinTS endpoint, BLZ, IBAN, guardrails
├── src/
│   └── invoice_admin/
│       ├── __init__.py                 # __version__, __all__
│       ├── __main__.py                 # Thin: calls cli.main()
│       ├── cli.py                      # New unified CLI: invoice ingest|watch|status|followup|send|retry|review|cost
│       ├── core/
│       │   ├── __init__.py
│       │   ├── llm.py                  # litellm LLM provider + MODEL_ALIASES + llm_calls logger
│       │   ├── pdf.py                  # Claude native PDF → structured data
│       │   ├── imap.py                 # IMAP email collection (not Gmail API — IMAP is generic)
│       │   ├── spark_link.py           # Spark deep-link generator
│       │   ├── tracker.py              # SQLite invoice tracker (full schema from brief §6)
│       │   ├── notify.py               # ntfy.sh + Pushover abstraction
│       │   ├── config.py               # Frozen dataclass config loader (swim pattern)
│       │   └── errors.py              # Domain exceptions
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── email_source.py         # Watches IMAP for invoice-bearing emails
│       │   └── file_source.py          # Watches filesystem folder for new PDFs
│       ├── classify/
│       │   ├── __init__.py
│       │   ├── classifier.py           # LLM classification: invoice_type + confidence
│       │   └── prompts.py             # Classification + extraction prompts
│       ├── handlers/
│       │   ├── __init__.py
│       │   ├── base.py                 # Handler Protocol; common helpers
│       │   ├── foyer_claim.py          # Playwright automation against Foyer portal
│       │   ├── sepa_transfer.py        # python-fints SEPA transfer prep against VR Landau
│       │   └── outgoing_invoice.py     # Wraps `googleads_invoice` (sibling under `src/`) for Gluggle flows
│       └── followup/
│           ├── __init__.py
│           ├── engine.py               # Status transitions, overdue detection, notifications
│           └── schedules.py            # Cron expressions per status
│   └── googleads_invoice/              # Google Ads flows (`import googleads_invoice`)
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── invoices/                   # PDF fixtures for classifier + extraction tests
│   │   └── emails/                     # EML fixtures for email source tests
│   ├── test_core/
│   ├── test_handlers/
│   └── ... (existing 22 test files preserved in-place)
├── scripts/
│   └── seed_examples.py               # Seed classifier_examples.jsonl from real invoices
```

---

## 2. Implementation Steps — By Milestone

Each step specifies:
- **Action**: What to do
- **Files**: Exact paths to create or modify
- **Pattern**: Code to write (or pattern to follow)
- **Warning**: What NOT to do

---

### M1 — Study + Scaffolding (NO code changes to existing source)

**Step M1.1**: Create the target directory structure as empty modules.

**Files to create** (empty or with minimal content):

```
src/invoice_admin/__init__.py
src/invoice_admin/__main__.py
src/invoice_admin/cli.py
src/invoice_admin/core/__init__.py
src/invoice_admin/core/llm.py
src/invoice_admin/core/pdf.py
src/invoice_admin/core/imap.py
src/invoice_admin/core/spark_link.py
src/invoice_admin/core/tracker.py
src/invoice_admin/core/notify.py
src/invoice_admin/core/config.py
src/invoice_admin/core/errors.py
src/invoice_admin/sources/__init__.py
src/invoice_admin/sources/email_source.py
src/invoice_admin/sources/file_source.py
src/invoice_admin/classify/__init__.py
src/invoice_admin/classify/classifier.py
src/invoice_admin/classify/prompts.py
src/invoice_admin/handlers/__init__.py
src/invoice_admin/handlers/base.py
src/invoice_admin/handlers/foyer_claim.py
src/invoice_admin/handlers/sepa_transfer.py
src/invoice_admin/handlers/outgoing_invoice.py
src/invoice_admin/followup/__init__.py
src/invoice_admin/followup/engine.py
src/invoice_admin/followup/schedules.py
tests/test_core/__init__.py
tests/test_handlers/__init__.py
config/default.yaml
config/handlers/outgoing_gluggle.yaml
config/handlers/foyer.yaml
config/handlers/sepa_vr_landau.yaml
scripts/seed_examples.py
```

Every `.py` file starts with:
```python
"""Single-line module docstring."""
from __future__ import annotations
```

**Warning** (M1 historical): Do NOT move or modify any file in `googleads_invoice` during scaffolding-only steps. The tree lives under `src/googleads_invoice/`.

---

### M2 — Core Infrastructure (no handlers yet)

#### Step M2.1: `core/config.py` — Config loader

Follow swim's `swim/config/__init__.py` and `swim/config/paths.py`.

```python
"""Config loader — frozen dataclass from YAML."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PathsConfig:
    """Resolved filesystem paths for all invoice operations."""
    invoices_root: Path          # ~/Documents/Invoices/
    inbox_dir: Path              # invoices_root / "_inbox"
    foyer_claims_dir: Path       # invoices_root / "foyer_claims"
    sepa_transfers_dir: Path     # invoices_root / "sepa_transfers"
    outgoing_dir: Path           # invoices_root / "outgoing"
    failures_dir: Path           # invoices_root / "_failures"
    tracker_path: Path           # ~/.local/state/invoice_admin/tracker.sqlite
    log_path: Path               # ~/.local/state/invoice_admin/log.jsonl
    llm_calls_path: Path         # ~/.local/state/invoice_admin/llm_calls.sqlite


@dataclass(frozen=True)
class ModelConfig:
    """LLM model aliases."""
    fast: str
    smart: str
    cheap: str
    local: str


@dataclass(frozen=True)
class NotifyConfig:
    """Notification channel settings."""
    ntfy_topic: str | None
    pushover_user: str | None
    pushover_token: str | None


@dataclass(frozen=True)
class InvoiceConfig:
    """Full resolved config."""
    paths: PathsConfig
    models: ModelConfig
    notify: NotifyConfig
    dry_run: bool           # default True
    max_auto_amount_eur: int  # default 2000
    classifier_min_confidence: float  # default 0.7
    raw: dict[str, Any]     # raw YAML for handler-specific configs


def repo_root() -> Path:
    """Find repository root. Mirrors swim/common.py:repo_root()."""
    # 1. Check INVOICE_ADMIN_REPO_ROOT env var
    # 2. Walk up from CWD looking for pyproject.toml
    # 3. Walk up from __file__ looking for pyproject.toml
    # 4. Raise RuntimeError if not found
    ...


def load_config(root: Path | None = None) -> InvoiceConfig:
    """Load default.yaml, overlay env vars, return frozen InvoiceConfig."""
    ...
```

**Warning**: `PathsConfig.invoices_root` defaults to `~/Documents/Invoices/` but is overridable via env `INVOICE_ADMIN_ROOT`. Do not hardcode paths. Use `Path.home()` not `/Users/chaehan/`.

**Pattern**: Root detection mirrors `swim/common.py:repo_root()` exactly — env var, CWD walk, package walk. Config is loaded once at import time in `cli.py` as a module-level variable.

#### Step M2.2: `core/errors.py` — Domain exceptions

```python
"""Domain exceptions for invoice-admin."""
from __future__ import annotations


class InvoiceError(Exception):
    """Base exception for all invoice-admin errors."""


class ConfigError(InvoiceError):
    """Configuration is missing or invalid."""

class TrackerError(InvoiceError):
    """Database operation failed."""

class ClassifierError(InvoiceError):
    """Classification or extraction failed."""

class HandlerError(InvoiceError):
    """A handler failed to process an invoice."""

class IdempotencyViolation(InvoiceError):
    """Duplicate message-ID or file hash detected."""

class ExtractionError(ClassifierError):
    """LLM could not extract structured data from invoice."""

class ClassificationLowConfidence(ClassifierError):
    """Classifier confidence below threshold."""

class SepaGuardrailError(HandlerError):
    """Transfer exceeds MAX_AUTO_AMOUNT_EUR or IBAN validation failed."""

class NotifyError(InvoiceError):
    """Notification delivery failed."""

class FoyerAuthError(HandlerError):
    """Foyer portal authentication failed."""
```

**Warning**: Do NOT create a catch-all exception hierarchy. Each error class maps to a specific failure mode. Do NOT use these in generic `except` blocks — catch only the specific type you need.

#### Step M2.3: `core/tracker.py` — SQLite invoice tracker

```python
"""SQLite invoice tracker."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingested_at     TEXT NOT NULL,
    source_type     TEXT NOT NULL CHECK(source_type IN ('email', 'file')),
    source_ref      TEXT NOT NULL UNIQUE,
    invoice_type    TEXT,
    classifier_conf REAL,
    vendor          TEXT,
    invoice_date    TEXT,
    due_date        TEXT,
    amount          REAL,
    currency        TEXT,
    iban            TEXT,
    bic             TEXT,
    verwendungszweck TEXT,
    pdf_path        TEXT,
    status          TEXT NOT NULL DEFAULT 'received',
    submitted_at    TEXT,
    approved_at     TEXT,
    paid_at         TEXT,
    reimbursed_at   TEXT,
    error           TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_type ON invoices(invoice_type);
"""


@dataclass(frozen=True)
class InvoiceRow:
    """A row from the tracker. All fields optional except id and status."""
    id: int
    status: str
    ingested_at: str
    source_type: str
    source_ref: str
    invoice_type: str | None = None
    classifier_conf: float | None = None
    vendor: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    amount: float | None = None
    currency: str | None = None
    iban: str | None = None
    bic: str | None = None
    verwendungszweck: str | None = None
    pdf_path: str | None = None
    submitted_at: str | None = None
    approved_at: str | None = None
    paid_at: str | None = None
    reimbursed_at: str | None = None
    error: str | None = None
    notes: str | None = None


class Tracker:
    """Thread-safe tracker. One instance per process. Context manager for connection lifecycle."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> Tracker:
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def exists(self, source_ref: str) -> bool:
        """Check idempotency: has this source_ref been ingested?"""
        ...

    def insert(self, source_type: str, source_ref: str, **kwargs: Any) -> int:
        """Insert a new row. Raises IdempotencyViolation if source_ref exists. Returns row id."""
        ...

    def get(self, row_id: int) -> InvoiceRow | None:
        """Fetch one row by id."""
        ...

    def update_status(self, row_id: int, status: str, **extra: Any) -> None:
        """Atomically update status and optional extra fields."""
        ...

    def list_by_status(self, status: str) -> list[InvoiceRow]:
        """List all rows with given status."""
        ...

    def list_overdue(self) -> list[InvoiceRow]:
        """Rows where due_date < today AND status NOT IN terminal states."""
        ...

    def list_by_type(self, invoice_type: str, status: str | None = None) -> list[InvoiceRow]:
        """List rows by type, optionally filtered by status."""
        ...
```

**Warning**: 
- `insert()` must raise `IdempotencyViolation` on UNIQUE constraint failure. The caller catches this and treats it as a no-op.
- `update_status()` must use `UPDATE ... WHERE id = ?` inside a transaction. No partial updates.
- All datetimes stored as ISO 8601 UTC strings (`datetime.now(timezone.utc).isoformat()`).
- The `error` column stores a JSON blob: `{"type": "ExtractionError", "message": "...", "traceback": "..."}`.
- WAL mode is required for concurrent read/write from the followup engine.

#### Step M2.4: `core/llm.py` — LLM provider abstraction

```python
"""LLM provider abstraction via litellm."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import litellm


MODEL_ALIASES: dict[str, str] = {
    "fast":  "claude-haiku-4-5",
    "smart": "claude-opus-4-7",
    "cheap": "deepseek/deepseek-chat",
    "local": "ollama/llama3.1:70b",
}


@dataclass
class LLMCallRecord:
    """Logged to llm_calls.sqlite."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_ms: int
    handler: str       # which handler triggered this call
    purpose: str       # 'classification', 'extraction', 'pdf_extraction'
    success: bool
    error: str | None


class LLMProvider:
    """Single entry point for all LLM calls. Logs every call."""

    def __init__(self, alias_map: dict[str, str] | None = None, log_path: Path | None = None) -> None:
        self._aliases = alias_map or MODEL_ALIASES
        self._log_path = log_path
        self._log_conn: sqlite3.Connection | None = None

    def _init_log(self) -> None:
        """Create llm_calls table if not exists."""
        ...

    def _log_call(self, record: LLMCallRecord) -> None:
        """Insert into llm_calls table."""
        ...

    def _resolve_model(self, alias: str) -> str:
        """'fast' → 'claude-haiku-4-5'. Raises ValueError if alias not found."""
        ...

    def complete(
        self,
        prompt: str,
        model_alias: str = "fast",
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        handler: str = "unknown",
        purpose: str = "general",
    ) -> str:
        """Call LLM, log, return completion text. Raises litellm exceptions on failure."""
        ...
```

**Warning**:
- Every call to `complete()` logs to the `llm_calls` SQLite table. No exceptions.
- `MODEL_ALIASES` are defaults. The config file can override them.
- Litellm uses the `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY` env vars. Do not pass API keys in code.
- The `log_path` default is `<state_dir>/llm_calls.sqlite` — respect the path from config.
- Do NOT import `instructor` or any structured-output library. Use plain `complete()` + `json.loads()` for parsing.

#### Step M2.5: `core/pdf.py` — PDF extraction via Claude

```python
"""PDF → structured data via Claude native PDF support."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedInvoiceData:
    """Structured data extracted from an invoice PDF."""
    vendor: str | None
    invoice_date: str | None      # ISO 8601
    due_date: str | None          # ISO 8601
    amount: float | None
    currency: str | None
    iban: str | None
    bic: str | None
    verwendungszweck: str | None
    raw_json: str                 # Full LLM response for debugging


def extract_pdf_data(pdf_path: Path, llm_provider, model_alias: str = "smart") -> ExtractedInvoiceData:
    """Send PDF to Claude, get structured data back.

    Uses Claude's native PDF support: pass the PDF bytes as a document part.
    The prompt asks for JSON output. Parse with json.loads().

    Raises ExtractionError on parse failure or empty fields.
    """
    ...
```

**Warning**:
- Do NOT use `pypdf`, `pdfplumber`, or OCR. Send raw PDF bytes to Claude.
- The extraction prompt lives in `classify/prompts.py`, not in this module. Import it.
- This module is about the MECHANISM of sending a PDF to the LLM. The prompt is separate.

#### Step M2.6: `core/notify.py` — Push notifications

```python
"""Push notifications via ntfy.sh (primary) and Pushover (optional)."""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    priority: str   # 'min', 'low', 'default', 'high', 'urgent'
    click_url: str | None   # Spark deep-link or None


class Notifier:
    """Sends push notifications. Falls back gracefully."""

    def __init__(self, ntfy_topic: str | None = None, pushover_user: str | None = None, pushover_token: str | None = None) -> None:
        ...

    def send(self, notification: Notification) -> bool:
        """Send to ntfy.sh. Returns True if 2xx, False otherwise. Never raises."""
        # Use urllib (no requests dependency). POST to https://ntfy.sh/{topic}
        # Headers: Title, Priority, Click (if click_url set)
        # Body: plain text
        # On failure: log warning, return False. Never raise.
        ...
```

**Warning**:
- Do NOT use the `requests` library. Use `urllib.request` only (stdlib). Minimize dependencies.
- `send()` must NEVER raise. It logs a warning on failure and returns `False`.
- The `.env` file contains `NTFY_TOPIC` (required) and optionally `PUSHOVER_USER` + `PUSHOVER_TOKEN`.
- Priority mapping: `needs_review` → `high`, `awaiting_tan` → `high`, `failed` → `urgent`, overdue digest → `default`.

#### Step M2.7: `core/imap.py` — IMAP email collection

```python
"""IMAP email collection for invoice ingestion."""
from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class EmailMessage:
    """Parsed email ready for invoice processing."""
    message_id: str             # RFC822 Message-ID (with angle brackets)
    sender: str
    subject: str
    date: datetime
    html_body: str | None
    pdf_attachments: list[bytes]  # Raw PDF bytes (for Claude extraction)


class ImapCollector:
    """Connects to IMAP, searches for invoice-bearing emails, yields EmailMessage objects.

    Uses IMAP IDLE or periodic polling. Credentials from env: IMAP_HOST, IMAP_USER, IMAP_PASS.
    """

    def __init__(self, host: str, user: str, password: str, mailbox: str = "INBOX") -> None:
        ...

    def collect_unseen(self) -> Iterator[EmailMessage]:
        """Yield unseen emails with PDF attachments or invoice-like subjects."""
        ...
```

**Warning**:
- Use `imaplib` from stdlib (not `imapclient` or `aioimaplib`). Minimize dependencies.
- The `message_id` is the RFC822 `Message-ID` header value (with `<` and `>`). This becomes `source_ref` in the tracker.
- The IMAP collector is for the EMAIL SOURCE only. The existing Gmail API backend (`GmailApiReadBackend`) is preserved for the OutgoingInvoiceHandler's specific needs (different auth, different search queries).
- Do NOT try to unify Gmail API and IMAP into one interface. They serve different purposes.

#### Step M2.8: `core/spark_link.py` — Spark deep-link generator

```python
"""Spark deep-link generator."""
from __future__ import annotations

from urllib.parse import quote


def spark_deep_link(message_id: str) -> str:
    """Generate a readdle-spark:// deep-link for a given RFC822 Message-ID.

    Format (verify at build time): readdle-spark://openmessage?messageId=<URL-encoded message_id>
    The message_id should include angle brackets, e.g. <abc123@mail.gmail.com>.
    """
    encoded = quote(message_id, safe="")
    return f"readdle-spark://openmessage?messageId={encoded}"


def spark_link_with_fallback(message_id: str, sender: str, subject: str, date_str: str) -> str:
    """Return Spark deep-link + plain text fallback for when the scheme doesn't fire."""
    deep_link = spark_deep_link(message_id)
    return f"[Open in Spark]({deep_link})\n\n{sender} — {subject} — {date_str}"
```

**Warning**: The URL scheme may have changed. Readdle has changed it before. The format `readdle-spark://openmessage?messageId=<encoded>` is the LATEST KNOWN format. Verify with a real test before M3.

---

### M3 — Classification + Sources (end-to-end ingest pipeline)

#### Step M3.1: `classify/prompts.py`

```python
"""Classification and extraction prompts."""
from __future__ import annotations


CLASSIFICATION_PROMPT = """\
You are an invoice classifier. Given the following extracted data from an invoice PDF, determine the invoice type.

Data:
{extracted_data}

Classify as ONE of:
- "foyer_claim" — health insurance claim for Foyer Global Health (medical bill, doctor visit, hospital)
- "sepa_transfer" — tradesman/handwerker bill requiring SEPA bank transfer (plumber, electrician, repair, craftsman)
- "outgoing_invoice" — an invoice that Chaehan needs to SEND to a client (not one he received)
- "unknown" — cannot confidently classify

Respond with ONLY a JSON object:
{{"invoice_type": "<type>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}
"""


EXTRACTION_PROMPT = """\
Extract structured data from this invoice PDF. Return ONLY a JSON object.

{{
    "vendor": "Company or person who issued this invoice",
    "invoice_date": "YYYY-MM-DD or null",
    "due_date": "YYYY-MM-DD or null",
    "amount": <number or null>,
    "currency": "EUR/USD/etc or null",
    "iban": "IBAN string or null",
    "bic": "BIC/SWIFT string or null",
    "verwendungszweck": "Payment reference/purpose or null"
}}

Do not include any text outside the JSON object.
"""
```

**Warning**: The JSON templates use double-braces `{{` because these are formatted as Python f-strings at call time. The classification prompt receives `{extracted_data}` injected at runtime.

#### Step M3.2: `classify/classifier.py`

```python
"""Invoice classifier using LLM."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from invoice_admin.core.errors import ClassificationLowConfidence, ExtractionError
from invoice_admin.core.pdf import ExtractedInvoiceData
from invoice_admin.classify.prompts import CLASSIFICATION_PROMPT


@dataclass(frozen=True)
class ClassificationResult:
    invoice_type: str          # 'foyer_claim' | 'sepa_transfer' | 'outgoing_invoice' | 'unknown'
    confidence: float          # 0.0–1.0
    reasoning: str
    extracted_data: ExtractedInvoiceData


def classify_invoice(
    extracted: ExtractedInvoiceData,
    llm_provider,
    min_confidence: float = 0.7,
) -> ClassificationResult:
    """Classify extracted invoice data. Raises ClassificationLowConfidence if below threshold.

    1. Format CLASSIFICATION_PROMPT with extracted_data
    2. Call llm_provider.complete() with model_alias="fast"
    3. Parse JSON response
    4. If confidence < min_confidence → type becomes 'needs_review' and confidence retained
    5. Return ClassificationResult
    """
    ...


def extract_and_classify(
    pdf_path,
    llm_provider,
    min_confidence: float = 0.7,
) -> ClassificationResult:
    """Full pipeline: extract PDF data, then classify. Single call for convenience."""
    extracted = extract_pdf_data(pdf_path, llm_provider)
    return classify_invoice(extracted, llm_provider, min_confidence)
```

**Warning**: `classify_invoice()` does NOT insert into the tracker. That's the caller's job (in `sources/`). This function is pure: PDF bytes in, ClassificationResult out.

#### Step M3.3: `sources/file_source.py`

```python
"""Filesystem watcher for invoice PDFs."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    ...


def ingest_pdf_file(
    pdf_path: Path,
    tracker,
    llm_provider,
    config,
) -> int | None:
    """Ingest a single PDF file from the filesystem.

    1. Compute SHA-256 hash of the file
    2. Check tracker.exists(hash) → if True, return None (idempotent)
    3. Call extract_and_classify(pdf_path, llm_provider, config.classifier_min_confidence)
    4. Insert into tracker with source_type='file', source_ref=hash, invoice_type, etc.
    5. Rename and move file to destination based on invoice_type:
       - foyer_claim → config.paths.foyer_claims_dir / YYYY / renamed_file
       - sepa_transfer → config.paths.sepa_transfers_dir / YYYY / renamed_file
       - outgoing_invoice → config.paths.outgoing_dir / YYYY / renamed_file
       - unknown/failed → config.paths.failures_dir / YYYY-MM-DD / renamed_file
    6. Return row id

    Rename convention: YYYY-MM-DD_<vendor-slug>_<amount><CCY>.pdf
    Slugify vendor: lowercase, ASCII, hyphens, no special chars.
    """
    ...


def watch_inbox(
    inbox_dir: Path,
    tracker,
    llm_provider,
    config,
    poll_interval: int = 10,
) -> None:
    """Poll inbox_dir every poll_interval seconds for new PDFs. Process each."""
    ...
```

**Warning**: 
- File hash is SHA-256 of FULL file contents (not filename). This is the idempotency key for file sources.
- The rename-and-move step happens BEFORE handler execution. The handler receives the new path.
- Do NOT delete the original file. Move it (with rename). The inbox should empty as files are processed.
- Slugify: `re.sub(r'[^a-z0-9-]', '', vendor.lower().replace(' ', '-').replace('_', '-'))` — strip all non-ASCII first via `unicodedata.normalize('NFKD')`.
- If extraction fails entirely (ExtractionError), move to `_failures/<YYYY-MM-DD>/` with an error log alongside it: `<original_name>.error.json`.

#### Step M3.4: `sources/email_source.py`

```python
"""IMAP email watcher for invoice-bearing emails."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone


def ingest_email(
    email_msg,    # EmailMessage from core/imap.py
    tracker,
    llm_provider,
    config,
) -> int | None:
    """Ingest an invoice from an email.

    1. Use email_msg.message_id as source_ref
    2. Check tracker.exists(message_id) → if True, return None (idempotent)
    3. If email has PDF attachments, save first PDF to temp file, run extract_and_classify()
    4. If email has no PDF but has HTML body, send HTML to Claude for extraction (treat body as invoice content)
    5. Insert into tracker with source_type='email', source_ref=message_id
    6. Save PDF (if any) to appropriate directory tree
    7. Return row id
    """
    ...


def watch_imap(
    imap_collector,
    tracker,
    llm_provider,
    config,
    poll_interval: int = 60,
) -> None:
    """Poll IMAP every poll_interval seconds for new invoice emails. Process each."""
    ...
```

**Warning**:
- The `message_id` is the RFC822 Message-ID header (with `<` and `>` brackets). Do not strip the brackets.
- The email_source does NOT use the Gmail API. It uses IMAP (stdlib `imaplib`). The Gmail API is preserved in the OutgoingInvoiceHandler for its specific needs.
- If an email has multiple PDFs, process ONLY the first one. Log a note about additional attachments.
- If extraction fails, mark the tracker row `status='failed'` with the error blob. Do NOT move the email.

---

### M4 — FoyerClaim Handler

#### Step M4.1: `handlers/base.py` — Handler Protocol

```python
"""Handler Protocol and common helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from invoice_admin.core.tracker import InvoiceRow


@runtime_checkable
class Handler(Protocol):
    """Protocol for all invoice handlers."""

    @property
    def invoice_type(self) -> str:
        """The invoice_type string this handler processes (e.g. 'foyer_claim')."""
        ...

    def execute(self, row: InvoiceRow, tracker, llm_provider, config, notifier) -> None:
        """Process an invoice row.

        The handler reads the row, performs its action, and updates the row's status
        in the tracker. Must handle idempotency: if the row is already at a terminal
        status, do nothing.

        On failure: update row.status = 'failed', row.error = error_json_blob,
        then send a notification via notifier. Never silently swallow errors.
        """
        ...


def prepare_invoice_pdf(row: InvoiceRow, config) -> Path:
    """Locate the PDF file for a given tracker row. Returns absolute path or raises FileNotFoundError."""
    ...


def rename_invoice_pdf(row: InvoiceRow, config, vendor_slug: str) -> Path:
    """Rename stored PDF to YYYY-MM-DD_<vendor-slug>_<amount><CCY>.pdf."""
    ...
```

**Warning**: The Protocol uses `@runtime_checkable` so callers can use `isinstance(handler, Handler)`. No ABC, no `@abstractmethod`.

#### Step M4.2: `handlers/foyer_claim.py`

```python
"""Foyer Global Health claim submission via Playwright."""
from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime, timezone

from invoice_admin.core.tracker import InvoiceRow
from invoice_admin.core.errors import FoyerAuthError


class FoyerClaimHandler:
    """Submits health insurance claims to Foyer Global Health portal."""

    invoice_type = "foyer_claim"

    def __init__(self, config: dict) -> None:
        """config is the raw YAML from foyer.yaml."""
        self._portal_url = config["portal_url"]       # https://portal.foyerglobalhealth.com
        self._session_path = config.get("session_path")  # Path to storage_state JSON
        self._timeout_ms = config.get("timeout_ms", 30000)

    def execute(self, row: InvoiceRow, tracker, llm_provider, config, notifier) -> None:
        """Submit claim to Foyer portal.

        1. Check row.status — if already 'submitted' or 'reimbursed', return (idempotent)
        2. Update status to 'submitting'
        3. Launch Playwright, load storage_state if exists
        4. Navigate to portal_url
        5. If login page detected (no valid session), authenticate:
           - Fill username/password from env vars FOYER_USERNAME, FOYER_PASSWORD
           - Handle 2FA if prompted (log and notify Chaehan — may need manual intervention)
           - Save storage_state to session_path
        6. Navigate to claims submission page
        7. Fill form: date from row.invoice_date, vendor from row.vendor, amount from row.amount
        8. Upload PDF from row.pdf_path
        9. Submit claim
        10. Capture confirmation number from success page
        11. Screenshot confirmation to _artifacts/<row.id>.png (if artifacts dir configured)
        12. Update tracker: status='submitted', submitted_at=now, notes+=confirmation_number
        13. Save storage_state if updated

        On any failure:
        - Update status='failed', set error blob
        - Screenshot error page if possible
        - Send notification
        - Re-raise as FoyerAuthError or HandlerError
        """
        ...

    def _authenticate(self, page, storage_state_path: Path | None) -> bool:
        """Returns True if authenticated, False if manual 2FA required."""
        ...

    def _fill_claim_form(self, page, row: InvoiceRow) -> None:
        """Fill the Foyer claim form. Prefer ARIA roles and label text over CSS classes."""
        ...

    def _capture_confirmation(self, page) -> str:
        """Extract confirmation number from post-submission page. Returns empty string if not found."""
        ...
```

**Warning**:
- **Selector strategy**: Prefer `page.get_by_role(...)` and `page.get_by_label(...)`. NEVER rely on CSS classes or IDs.
- **2FA handling**: If the portal requires 2FA (SMS, authenticator app), the handler sets status to `needs_review` with a note "2FA required — please complete login manually" and sends a notification. Do NOT attempt to bypass 2FA.
- **Session persistence**: After successful login, save `page.context.storage_state()` to `session_path`. On next run, load it with `browser.new_context(storage_state=...)`. This avoids re-login each time.
- **Timeout**: Use `expect(...).to_be_visible(timeout=self._timeout_ms)` for all critical elements. Selectors break monthly.
- **No PII in screenshots**: If capturing a screenshot for debugging, redact any visible passwords or 2FA codes before saving. Consider saving to an encrypted directory.
- Credentials come from env vars `FOYER_USERNAME` and `FOYER_PASSWORD`, NOT from the YAML config. Never write credentials to YAML.

#### Step M4.3: `config/handlers/foyer.yaml`

```yaml
# Foyer Global Health claim handler config
portal_url: "https://portal.foyerglobalhealth.com"
session_path: "~/.local/state/invoice_admin/foyer_session.json"
artifacts_dir: "~/.local/state/invoice_admin/artifacts"
timeout_ms: 30000

# Locator hints (updated when portal changes)
locators:
  login_username: "input[name='username']"
  login_password: "input[name='password']"
  login_submit: "button[type='submit']"
  claims_tab: "text=Claims"
  new_claim_button: "text=Submit New Claim"
  claim_form_date: "input[name='service_date']"
  claim_form_vendor: "input[name='provider_name']"
  claim_form_amount: "input[name='claim_amount']"
  claim_form_upload: "input[type='file']"
  claim_submit: "button:has-text('Submit')"
  confirmation_number: ".confirmation-number"
```

**Warning**: The `locators` section is a HINT, not guaranteed to work. The handler code should fall back to ARIA roles and label text if CSS selectors fail. Update this YAML as the portal changes.

---

### M5 — SepaTransfer Handler (DRY RUN ONLY)

#### Step M5.1: `handlers/sepa_transfer.py`

```python
"""SEPA transfer preparation via python-fints against VR Landau."""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone

from invoice_admin.core.tracker import InvoiceRow
from invoice_admin.core.errors import SepaGuardrailError


# Mod-97 IBAN validation (implement inline, do not import schwifty)
def validate_iban(iban: str) -> bool:
    """Validate IBAN using mod-97 check. Returns True if structurally valid."""
    # Strip spaces, move first 4 chars to end, convert letters to digits (A=10..Z=35), mod 97 == 1
    ...


class SepaTransferHandler:
    """Prepares SEPA transfers via FinTS against VR Landau. Dry-run is default."""

    invoice_type = "sepa_transfer"

    def __init__(self, config: dict) -> None:
        """config is the raw YAML from sepa_vr_landau.yaml."""
        self._blz = config["blz"]                        # 54061170
        self._endpoint = config["fints_endpoint"]         # https://hbci-pintan.gad.de/cgi-bin/hbciservlet
        self._iban_self = config["iban_self"]             # Chaehan's IBAN (from env)
        self._account_holder = config["account_holder"]
        self._max_auto_amount = config.get("max_auto_amount_eur", 2000)
        self._dry_run = config.get("dry_run", True)       # MUST be True initially

    def execute(self, row: InvoiceRow, tracker, llm_provider, config, notifier) -> None:
        """Prepare SEPA transfer.

        1. Check row.status — if already 'paid' or 'failed', return (idempotent)
        2. Validate IBAN structurally (mod-97). If invalid → status='needs_review', notify, return.
        3. Check amount against MAX_AUTO_AMOUNT_EUR. If exceeded → status='needs_review', notify, return.
        4. If dry_run is True:
           - Log the full SEPA payload that WOULD be sent
           - Update status='prepared' (NOT 'awaiting_tan' in dry run)
           - Log to structured log: amount, iban, verwendungszweck, vendor
           - Send notification: "[DRY RUN] Would transfer €{amount} to {vendor}"
        5. If dry_run is False (production):
           - Build FinTS dialog: HKCCS (SEPA transfer) with IBAN, BIC, amount, purpose
           - Submit to FinTS endpoint
           - Update status='awaiting_tan'
           - Send notification: "Tap to approve €{amount} to {vendor} in SecureGo+"
        6. On failure: status='failed', error blob, notification

        DRY RUN is the DEFAULT. To enable live transfers, Chaehan must edit
        sepa_vr_landau.yaml and set dry_run: false. No CLI flag overrides this.
        """
        ...

    def _build_sepa_payload(self, row: InvoiceRow) -> dict:
        """Build the SEPA transfer payload dict. Does NOT call FinTS."""
        ...

    def _dispatch_fints(self, payload: dict, pin: str) -> str | None:
        """Call python-fints to submit the transfer. Returns transaction ID or None.

        NOT CALLED in dry-run mode. Requires FinTS PIN from env var FINTS_PIN.
        """
        ...
```

**Warning**:
- **DRY RUN IS DEFAULT.** This is enforced by the YAML config `dry_run: true`. There is NO CLI flag to override it. Switching to live requires a deliberate config edit. See brief §3.
- **MAX_AUTO_AMOUNT_EUR = 2000.** Transfers above this go to `needs_review`. The threshold is configurable in YAML but CONSPICUOUS — put a comment above it in the YAML file.
- **IBAN validation is standalone.** Do NOT depend on `schwifty` or any external IBAN library. Implement mod-97 in ~10 lines. If the IBAN is invalid, the row goes to `needs_review`, NOT `failed`. Invalid IBAN is a human decision, not a system error.
- **FinTS PIN** comes from env var `FINTS_PIN`, never from YAML or code.
- **TAN mechanism**: `decoupledTAN` (SecureGo+ push to Chaehan's phone). The handler prepares the transfer fully, sets status to `awaiting_tan`, and stops. It does NOT wait for TAN approval. See brief §3 (PSD2 SCA wall).
- **No silent failures.** Any error in FinTS dispatch writes to tracker with `status='failed'`, a structured error blob, and a push notification. No catch-and-continue.

#### Step M5.2: `config/handlers/sepa_vr_landau.yaml`

```yaml
# VR Landau SEPA transfer handler config
# WARNING: dry_run must be true for the first 14 days. Change only after review with Chaehan.
dry_run: true                      # ← SET TO FALSE ONLY AFTER 14-DAY DRY-RUN REVIEW
max_auto_amount_eur: 2000          # ← Transfers above this go to needs_review

blz: "54061170"
fints_endpoint: "https://hbci-pintan.gad.de/cgi-bin/hbciservlet"
code: "54061170"                   # Bank code (same as BLZ for VR Landau)

# Account holder details (from env, NOT hardcoded here)
# IBAN: INVOICE_ADMIN_IBAN_SELF
# Account holder: INVOICE_ADMIN_ACCOUNT_HOLDER

tan_mechanism: "decoupledTAN"      # SecureGo+ push to phone
```

**Warning**: The `dry_run: true` flag is the safety mechanism. Do NOT add a `--live` CLI flag. The brief is explicit: "Switching off dry-run is a deliberate config edit, not a CLI flag with a default of False."

---

### M6 — Wrap Existing Code as OutgoingInvoiceHandler

**Critical constraint**: The code in `src/googleads_invoice/` must keep working identically for parity. Hatch wheel **`packages`** must include **`src/googleads_invoice`** so `import googleads_invoice` works from installs and from pytest (`pythonpath` includes **`src`**).

#### Step M6.1: Extract gluggle-jug config to YAML

Move all gluggle-jug-specific constants from `addresses.py` into a YAML file.

**`config/handlers/outgoing_gluggle.yaml`**:
```yaml
# Outgoing invoice handler for Gluggle Jug client
client:
  name: "The Gluggle Jug Factory"
  contact: "Jack Copeland"
  email: "jack.copeland@theglugglejugfactory.com"

email:
  sender: "chaehan.so@gmail.com"
  cc:
    - "sophie.mahlo@theglugglejugfactory.com"
    - "rudi.mahlo@theglugglejugfactory.com"
  bcc:
    - "chaehan.so@gmail.com"         # Evernote archive
  test_recipient: "chaehan.so@virtualfriend.chat"

commission:
  rate: 0.03                         # 3% commission
  sender_email: "jack.copeland@theglugglejugfactory.com"
  query: "commission"                # Gmail search query for commission PDFs

paths:
  dropbox_invoice_dir: "~/Library/CloudStorage/Dropbox/Finance/GluggleJug/GluggleJug Commissions"
  dropbox_commission_dir: "~/Library/CloudStorage/Dropbox/Finance/GluggleJug/Commissions"

billing:
  query: 'from:payments-noreply@google.com subject:"Google Ads: Your billing document is ready"'
  brave_debug_port: 9222

pdf_naming:
  invoice_pattern: "google-ads-invoice_{date}_{amount}-EUR.pdf"
  commission_pattern: "{month} Commission {month_name} €{amount}.pdf"
```

**Warning**: The `addresses.py` module IS NOT DELETED yet. The YAML is a new file. The original code still reads from `addresses.py`. The handler wrapper (Step M6.2) reads from YAML.

#### Step M6.2: `handlers/outgoing_invoice.py` — Wrapper

```python
"""Outgoing invoice handler — wraps existing googleads_invoice functionality."""
from __future__ import annotations

from pathlib import Path

from invoice_admin.core.tracker import InvoiceRow


class OutgoingInvoiceHandler:
    """Wraps the existing googleads_invoice package for sending invoices to clients
    and saving commission PDFs.

    This handler covers TWO sub-actions:
    1. 'send_invoice' — the monthly Google Ads invoice flow (Gmail → Brave → parse → SMTP)
    2. 'save_commission' — download and save commission PDFs

    Both are triggered manually via CLI, not auto-classified from inbound emails.
    """

    invoice_type = "outgoing_invoice"

    def __init__(self, handler_config: dict) -> None:
        """handler_config is the raw YAML from outgoing_gluggle.yaml."""
        self._config = handler_config

    def execute(self, row: InvoiceRow, tracker, llm_provider, config, notifier) -> None:
        """Dispatch based on row.notes or row status to the right sub-action.

        For 'send_invoice' flow:
        - Calls googleads_invoice.run_month.run_month() with config mapped from YAML
        - Inserts result into tracker

        For 'save_commission' flow:
        - Calls googleads_invoice.save_commission_pdf.save_commission_pdf()
        - Inserts result into tracker
        """
        ...

    def send_monthly_invoice(self, month: str | None = None, tracker=None, config=None, notifier=None) -> InvoiceRow:
        """Manual trigger: send Google Ads invoice for given month (defaults to previous month).

        This is the CLI entry point for `invoice send --client gluggle --month 2026-04`.
        It wraps googleads_invoice.run_month.run_month() with YAML config injection.
        """
        ...

    def save_commission(self, tracker=None, config=None, notifier=None) -> InvoiceRow:
        """Manual trigger: download latest commission PDF and save to Dropbox.

        This wraps googleads_invoice.save_commission_pdf.save_commission_pdf().
        """
        ...
```

**Warning**:
- This handler does NOT use the LLM classifier. Outgoing invoices are manually triggered. The handler only processes rows that were created by the CLI `invoice send` command.
- The handler imports from `googleads_invoice` (the old package). This is intentional — the old code is wrapped, not rewritten.
- Do NOT copy-paste old code into this file. Import it. The `import googleads_invoice.run_month` statement is the correct approach.
- All gluggle-jug-specific values are in the YAML config. The handler reads from `self._config`, not from `googleads_invoice.addresses`.

#### Step M6.3: Create the parity test

```python
# In tests/test_handlers/test_outgoing_invoice_parity.py

"""Parity test: new handler output must match current code output."""
from __future__ import annotations


def test_dry_run_output_matches_current():
    """A test invoice sent through the new pipeline must match current output.

    This test:
    1. Runs the current googleads_invoice.pipeline.run_dry_run() with a fixture
    2. Runs the new OutgoingInvoiceHandler with the same input
    3. Compares byte-for-byte (or with documented differences)
    """
    ...
```

**Warning**: This test initially FAILS because the old code uses `addresses.py` constants and the new code uses YAML. That's fine. The test documents the equivalence. Once the test passes, the wrap is verified.

#### Step M6.4: Update `pyproject.toml`

```toml
[project]
name = "invoice_admin"
version = "0.0.1"
description = "Generic invoice handler — ingest, classify, route, track"
requires-python = ">=3.12"
dependencies = [
    "litellm",
    "playwright",
    "python-fints",
    "pypdf",
    "pyyaml",
    "selenium",
    "google-api-python-client",
    "google-auth-oauthlib",
]

[project.scripts]
invoice = "invoice_admin.cli:main"
googleads-invoice = "googleads_invoice.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "mypy>=1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Warning**: 
- The package name is `invoice_admin` (underscore). The CLI command is `invoice`. They are different.
- The Google Ads flows use console script **`googleads-invoice`** (same code as the former `billing-glugglejug` entry point).
- Add `python-fints`, `playwright`, `pyyaml` to dependencies. They were not in the old project.

#### Step M6.5: Console + packaging for Google Ads flows

Use console script **`googleads-invoice`** → `googleads_invoice.cli:main`. Keep **`src/googleads_invoice/`** on the wheel (`packages` in `pyproject.toml`) and on pytest’s **`pythonpath`**. **`OutgoingInvoiceHandler`** imports **`googleads_invoice`**; no separate `archive/` tree.

---

### M7 — Followup Engine + CLI Polish

#### Step M7.1: `followup/schedules.py`

```python
"""Cron schedule definitions for followup checks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FollowupRule:
    """A rule that triggers when a row has been in a status for too long."""
    status: str
    max_age_hours: int
    new_status: str             # What to transition to, or None
    notification_priority: str   # 'default', 'high', 'urgent'
    message_template: str       # "Invoice {id} for €{amount} to {vendor} has been awaiting TAN for {hours}h"


FOLLOWUP_RULES: list[FollowupRule] = [
    FollowupRule(
        status="awaiting_tan",
        max_age_hours=4,
        new_status=None,                    # Don't auto-transition, just re-nag
        notification_priority="high",
        message_template="⏰ Reminder: Approve €{amount} to {vendor} in SecureGo+ (waiting {hours}h)",
    ),
    FollowupRule(
        status="awaiting_tan",
        max_age_hours=24,
        new_status="needs_review",          # Escalate after 24h
        notification_priority="urgent",
        message_template="⚠️ Overdue TAN: €{amount} to {vendor} has been waiting 24h. Transferred to needs_review.",
    ),
    FollowupRule(
        status="needs_review",
        max_age_hours=72,
        new_status=None,
        notification_priority="high",
        message_template="📋 Still needs review: {vendor} invoice for €{amount} (row {id})",
    ),
    FollowupRule(
        status="submitting",
        max_age_hours=2,
        new_status="failed",
        notification_priority="urgent",
        message_template="❌ Foyer submission stuck: {vendor} for €{amount} (row {id})",
    ),
]
```

**Warning**: Rules are data, not code. The followup engine reads these rules and applies them. Adding a new reminder is adding a `FollowupRule` entry, not editing engine code.

#### Step M7.2: `followup/engine.py`

```python
"""Followup engine — monitors tracker state and sends notifications."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from invoice_admin.followup.schedules import FOLLOWUP_RULES


class FollowupEngine:
    """Checks tracker for overdue items and sends notifications."""

    def __init__(self, tracker, notifier, config) -> None:
        ...

    def run_once(self) -> list[str]:
        """One pass of followup checks. Returns list of actions taken.

        1. For each FollowupRule:
           a. Query tracker for rows with matching status
           b. Filter for rows where status has been unchanged for > max_age_hours
           c. If new_status is set, transition the row
           d. Send notification with formatted message

        2. Daily digest (only if current hour is 09:00 local):
           - Query for overdue rows (due_date < today, status not terminal)
           - Send one summary notification
        """
        ...

    def run_forever(self, interval_minutes: int = 30) -> None:
        """Loop: run_once() every interval_minutes. Handle KeyboardInterrupt gracefully."""
        ...
```

**Warning**:
- The followup engine does NOT accept a `--daemon` flag. It runs as a foreground process. Use `launchd` or `cron` to schedule it — match the existing `scripts/com.invoice-admin.monthly.plist` pattern.
- Overdue detection uses `due_date` from the tracker. If `due_date` is NULL, the row is never considered overdue.
- The daily digest fires at 09:00 LOCAL TIME. Use `datetime.now().astimezone().hour == 9`, not UTC.

#### Step M7.3: `cli.py` — Unified CLI

```python
"""CLI entry point for invoice-admin."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from invoice_admin.core.config import repo_root, load_config


# Module-level config (swim pattern)
ROOT = repo_root()
CONFIG = load_config(ROOT)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point. Dispatches to subcommands."""
    parser = argparse.ArgumentParser(
        prog="invoice",
        description="Generic invoice handler — ingest, classify, route, track",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # invoice ingest <path>
    p_ingest = sub.add_parser("ingest", help="Ingest an invoice from a PDF file")
    p_ingest.add_argument("path", type=Path, help="Path to PDF file")

    # invoice ingest --email <spark-link>
    p_ingest.add_argument("--email", dest="spark_link", help="Spark deep-link to email (alternative to path)")

    # invoice watch
    p_watch = sub.add_parser("watch", help="Watch inbox folder for new PDFs")

    # invoice status [--type X] [--status Y]
    p_status = sub.add_parser("status", help="Show invoice tracker status")
    p_status.add_argument("--type", dest="invoice_type", help="Filter by invoice type")
    p_status.add_argument("--status", dest="status", help="Filter by status")

    # invoice followup
    sub.add_parser("followup", help="Run followup engine once")

    # invoice send --client gluggle --month 2026-04
    p_send = sub.add_parser("send", help="Send outgoing invoice manually")
    p_send.add_argument("--client", required=True, help="Client identifier (currently: gluggle)")
    p_send.add_argument("--month", help="Billing month (YYYY-MM, defaults to previous month)")

    # invoice retry <id>
    p_retry = sub.add_parser("retry", help="Retry a failed invoice")
    p_retry.add_argument("id", type=int, help="Tracker row ID")

    # invoice review <id>
    p_review = sub.add_parser("review", help="Review and approve a needs_review invoice")
    p_review.add_argument("id", type=int, help="Tracker row ID")

    # invoice cost
    sub.add_parser("cost", help="Show LLM cost dashboard (last 7/30 days)")

    args = parser.parse_args(argv)
    return _dispatch(args)


def _dispatch(args) -> int:
    """Route to the correct subcommand handler."""
    if args.command == "ingest":
        return _cmd_ingest(args)
    elif args.command == "watch":
        return _cmd_watch(args)
    elif args.command == "status":
        return _cmd_status(args)
    elif args.command == "followup":
        return _cmd_followup(args)
    elif args.command == "send":
        return _cmd_send(args)
    elif args.command == "retry":
        return _cmd_retry(args)
    elif args.command == "review":
        return _cmd_review(args)
    elif args.command == "cost":
        return _cmd_cost(args)
    return 1


def _cmd_ingest(args) -> int:
    """Handle `invoice ingest <path>` or `invoice ingest --email <link>`."""
    ...


# ... etc for each subcommand
```

**Warning**:
- CLI prints to stdout, errors to stderr. Follow swim's pattern: 2-space indented status lines, plain text output.
- Exit codes: 0 for success, 1 for general error, 2 for config error.
- The CLI module imports handlers lazily (inside `_cmd_*` functions), not at module level. This avoids importing Playwright or FinTS until needed.
- All `_cmd_*` functions return `int` (exit code). They do not call `sys.exit()` — that's `main()`'s job.

#### Step M7.4: `__main__.py`

```python
"""Entry point for python -m invoice_admin."""
from __future__ import annotations

import sys

from invoice_admin.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

**Warning**: Exactly 6 lines. Match swim's `src/swim/__main__.py` pattern. Do not add logic here.

#### Step M7.5: `__init__.py`

```python
"""invoice-admin — generic invoice handler."""
from __future__ import annotations

__version__ = "0.0.1"
__all__: list[str] = []
```

#### Step M7.6: Cost dashboard

The `invoice cost` subcommand queries the `llm_calls` SQLite table and prints:

```
LLM Cost Report — last 7 days
  classification:  23 calls, $0.12
  extraction:       8 calls, $0.89
  pdf_extraction:   8 calls, $1.44
  Total:          39 calls, $2.45

LLM Cost Report — last 30 days
  classification:  87 calls, $0.51
  extraction:      31 calls, $3.20
  pdf_extraction:  31 calls, $5.02
  Total:         149 calls, $8.73
```

**Warning**: Cost data comes from `litellm`'s cost tracking (enabled by default). If litellm doesn't provide cost, estimate from token counts. Format output as above — no fancy tables, just aligned text.

---

### Post-M7 — Live SepaTransfer

After 14 days of dry-run operation and review with Chaehan:

1. Review all dry-run log entries together
2. Confirm every SEPA payload would have been correct
3. Chaehan edits `config/handlers/sepa_vr_landau.yaml` and sets `dry_run: false`
4. Restart the followup engine

No code changes required for this step. The handler reads `dry_run` from config.

---

## 3. Hard Rules (NEVER Break These)

### Preserve existing behavior
- The `googleads_invoice` package (under `src/googleads_invoice/`) must remain installable and importable for as long as handlers and tests depend on it.
- Any behavioral change to outgoing invoice output must be documented and approved.

### Money safety
- `SepaTransfer` is dry-run for the first 14 days. No exceptions.
- `MAX_AUTO_AMOUNT_EUR = 2000`. Transfers above go to `needs_review`.
- No silent failures on money paths. Error → tracker `status='failed'` + notification.
- TAN is a PSD2 SCA wall. The handler stops at `awaiting_tan`. It does NOT wait for TAN.

### Idempotency
- Same `message_id` → no duplicate tracker row.
- Same file hash → no duplicate tracker row.
- Handlers check status before executing: if already terminal, return immediately.

### Security
- Credentials in `.env`, NEVER in YAML or code.
- `.env` is in `.gitignore`.
- No PII in test fixtures. Use clearly fake values: `DE00 0000 0000 0000 0000 00`, `John Doe`, `Test Clinic`.
- `FinTS PIN` from env var. Never logged.
- Session state files (Foyer) excluded from git.

### Architecture
- No web UI. CLI only.
- No multi-user. No auth beyond env-sourced credentials.
- No frameworks for their own sake. SQLite + cron + litellm is the stack.
- No catch-all `except Exception: pass`. Especially never in `handlers/`.
- No circular imports.
- No module-level network or I/O.

### Style
- `from __future__ import annotations` in every `.py` file.
- Union types with `|`, not `Optional`.
- Frozen dataclasses for config, record types.
- Protocols for interfaces (not ABCs).
- Defensive parsing: return `None`, never raise.
- Module-level docstrings (single line).
- Explicit `__all__` in `__init__.py`.

---

## 4. Test Strategy

### Existing tests (preserve)
All 22 test files in `tests/` remain in place and must continue passing. Do not modify them unless a behavioral change is approved.

### New tests (add)
- **`tests/test_core/test_config.py`** — config loading, root detection, path resolution
- **`tests/test_core/test_tracker.py`** — CRUD, idempotency, status transitions, overdue queries
- **`tests/test_core/test_llm.py`** — model resolution, alias mapping, call logging (mock litellm)
- **`tests/test_core/test_pdf.py`** — extraction from fixture PDFs (mock LLM responses)
- **`tests/test_core/test_errors.py`** — exception hierarchy, error serialization
- **`tests/test_core/test_notify.py`** — notification formatting, ntfy.sh URL construction (mock urllib)
- **`tests/test_core/test_imap.py`** — IMAP message parsing (mock imaplib)
- **`tests/test_core/test_spark_link.py`** — deep-link generation, URL encoding
- **`tests/test_classify/test_classifier.py`** — classification with mock LLM, confidence thresholds
- **`tests/test_classify/test_prompts.py`** — prompt formatting, JSON output parsing
- **`tests/test_sources/test_file_source.py`** — file hashing, rename convention, idempotency
- **`tests/test_sources/test_email_source.py`** — email ingestion, PDF attachment handling
- **`tests/test_handlers/test_base.py`** — Protocol compliance checks
- **`tests/test_handlers/test_foyer_claim.py`** — form filling, session persistence (mock Playwright)
- **`tests/test_handlers/test_sepa_transfer.py`** — dry-run logging, guardrails, IBAN validation
- **`tests/test_handlers/test_outgoing_invoice.py`** — YAML config injection, sub-action dispatch
- **`tests/test_handlers/test_outgoing_invoice_parity.py`** — byte-for-byte parity with current code
- **`tests/test_followup/test_engine.py`** — rule matching, overdue detection, daily digest
- **`tests/test_followup/test_schedules.py`** — rule definitions, message formatting
- **`tests/test_cli.py`** — (new) CLI subcommand dispatch, exit codes

### Fixture strategy
- PDF fixtures: create small, valid PDFs with `reportlab` or `fpdf`. Content: fake invoice data. No real invoices.
- EML fixtures: create synthetic emails with `email` stdlib. Attach PDF fixtures.
- Mock LLM responses: JSON strings matching the expected output schema. Store in `tests/fixtures/llm_responses/`.

### Test markers
```python
# In conftest.py (extend existing)
pytest.mark.e2e       # Requires live Foyer portal or FinTS endpoint (skip in CI)
pytest.mark.live      # Requires real browser or network (skip in CI)
pytest.mark.slow      # LLM calls or large file processing (skip in CI)
```

---

## 5. Summary — Step Order for the Coding LLM

Execute in this order. Each step depends on the previous. Do not skip ahead.

| Step | What to do | Key output |
|------|-----------|-----------|
| **M1.1** | Create empty module files (target structure) | Skeleton tree |
| **M2.1** | `core/config.py` | Config loader + frozen dataclass |
| **M2.2** | `core/errors.py` | Exception hierarchy |
| **M2.3** | `core/tracker.py` | SQLite tracker with schema |
| **M2.4** | `core/llm.py` | litellm provider + call logging |
| **M2.6** | `core/notify.py` | ntfy.sh notifier |
| **M2.5** | `core/pdf.py` | Claude PDF extraction |
| **M2.7** | `core/imap.py` | IMAP email collector |
| **M2.8** | `core/spark_link.py` | Spark deep-link generator |
| **M3.1** | `classify/prompts.py` | Classification + extraction prompts |
| **M3.2** | `classify/classifier.py` | Classifier + confidence threshold |
| **M3.3** | `sources/file_source.py` | File watcher + ingest pipeline |
| **M3.4** | `sources/email_source.py` | Email watcher + ingest pipeline |
| **M4.1** | `handlers/base.py` | Handler Protocol |
| **M4.2** | `handlers/foyer_claim.py` | Foyer claim handler (Playwright) |
| **M4.3** | `config/handlers/foyer.yaml` | Foyer config |
| **M5.1** | `handlers/sepa_transfer.py` | SEPA handler (dry-run only) |
| **M5.2** | `config/handlers/sepa_vr_landau.yaml` | VR Landau config |
| **M6.1** | `config/handlers/outgoing_gluggle.yaml` | Gluggle Jug config |
| **M6.2** | `handlers/outgoing_invoice.py` | Outgoing invoice wrapper |
| **M6.3** | Parity test | Prove output equivalence |
| **M6.4** | Update `pyproject.toml` | New package name, deps, entry point |
| **M6.5** | `googleads-invoice` + wheel includes `src/googleads_invoice` | Console rename; no `archive/` layout |
| **M7.1** | `followup/schedules.py` | Followup rules |
| **M7.2** | `followup/engine.py` | Followup engine |
| **M7.3** | `cli.py` | Unified CLI |
| **M7.4** | `__main__.py` | Thin entry point |
| **M7.6** | Cost dashboard | `invoice cost` subcommand |
| **Post** | YAML configs for all handlers | Default + handler configs |

---

## 6. File Naming Convention Reference

These conventions come from the brief §7. Implement them EXACTLY as specified.

### Rename convention
```
YYYY-MM-DD_<vendor-slug>_<amount><CCY>.pdf
```

Examples:
- `2026-05-12_Klempner-Mueller_487EUR.pdf`
- `2026-04-30_Google-Ads_6496-EUR.pdf`
- `2026-03-15_Dr-Schmidt_120USD.pdf`

### Slugify rules
1. Normalize to NFKD (strip diacritics)
2. Lowercase
3. Replace spaces and underscores with hyphens
4. Strip all non-`[a-z0-9-]` characters
5. Collapse multiple hyphens to one
6. Strip leading/trailing hyphens

```python
import unicodedata
import re

def slugify_vendor(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace(" ", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")
```

### Storage tree
```
~/Documents/Invoices/
  _inbox/                          # file_source watches this
  foyer_claims/<YYYY>/             # claims PDFs by year
  sepa_transfers/<YYYY>/           # tradesman bills by year
  outgoing/<YYYY>/                 # sent invoices by year
  _failures/<YYYY-MM-DD>/          # failed extractions, dated
```

### Path portability
- Root is configurable via env `INVOICE_ADMIN_ROOT`.
- Default: `~/Documents/Invoices/`.
- State (SQLite, logs) goes to `~/.local/state/invoice_admin/` (XDG spec).
- The `invoice_admin` subdirectory in `~/.local/state/` is auto-created if missing.

---

## 7. References

- Project brief: `docs/PROJECT_BRIEF_invoice_handler.md` (authoritative spec)
- Current codebase: `src/googleads_invoice/` (import `googleads_invoice`; optional merge into `invoice_admin` per PLAN P1)
- Swim repo: `/Users/chaehan/Software/Prototypes/swim/` (architecture reference)
- Test fixtures: `tests/fixtures/` (use as patterns for new fixtures)
