# Refactor plan — invoice-admin

Two sections per **Project brief §0c**: (1) disposition of current code, (2) **swim**-style patterns adopted.  
**Scope:** repo at `invoice-admin` with `src/googleads_invoice/` (Jack / Google Ads) and `src/invoice_admin/` (generic handler). **P1** (merge packages) is **out of scope** here; see `PLAN.md` and `docs/IMPLEMENTATION_PLAN_invoice_handler.md` §5.1 **S7**.

---

## 1. Current code disposition

Legend: **Wrap** = call unchanged from adapter; **Lift** = move/refactor into shared `invoice_admin` with same behavior; **Keep** = stays in place until P1/S6; **New** = greenfield in `invoice_admin`.

### `src/googleads_invoice/` (outgoing-invoice automation)

| Module | Disposition | Destination / notes |
|--------|-------------|---------------------|
| `__init__.py`, `__main__.py` | Removed 2026-09-07 | Console `googleads-invoice` / `python -m googleads_invoice` retired with the `invoice googleads` group (**brief §15** sign-off). |
| `cli.py` | Removed 2026-09-07 | Full argparse surface replaced by top-level `invoice send/save` with `--client`/`--provider` registry resolution. |
| `addresses.py` | Wrap + partial lift | Client constants mirrored in `config/handlers/outgoing_gluggle.yaml`; handler and legacy CLI still import `addresses` for parity paths—**do not delete** until sign-off (**brief §14**). |
| `billing_period.py`, `billing_url.py` | Keep | Pure helpers; used by pipeline / run-month. |
| `browser_download.py`, `live_brave_download.py`, `live_brave_trace.py` | Keep | Brave/WebDriver; obey `.cursor/rules/brave-for-google-ads.mdc`. |
| `commission_pdf.py`, `invoice_pdf.py` | Keep | PDF parse; fixtures in `tests/fixtures/pdf/`. |
| `gmail_api_backend.py`, `gmail_facade.py`, `gmail_smtp.py` | Keep | Gmail protocol/façade; OAuth env per README. |
| `invoice_artifacts.py` | Keep | Filename + email copy builders. |
| `mail_app_draft.py` | Keep | macOS Mail.app integration. |
| `pipeline.py`, `run_month.py` | Wrap | `OutgoingInvoiceHandler` + parity test call `run_dry_run` / same orchestration contract. |
| `save_commission_pdf.py` | Wrap | Exposed via `OutgoingInvoiceHandler` / legacy CLI. |

### `src/invoice_admin/` (generic invoice handler)

| Area | Disposition | Notes |
|------|-------------|--------|
| `core/` (`config`, `errors`, `tracker`, `llm`, `pdf`, `notify`, `imap`, `spark_link`, `naming`) | New | Config mirrors **swim** root discovery + frozen dataclass loading. |
| `classify/` | New | LLM classification + `classifier_examples.jsonl` few-shot store. |
| `sources/` | New | File + IMAP ingest; idempotency via tracker `source_ref`. |
| `handlers/base.py`, `foyer_claim.py`, `sepa_transfer.py` | New | **Protocol** handlers; Foyer/SEPA are new behavior (Foyer live supervised per brief). |
| `handlers/outgoing_invoice.py` | **Wrap** | Imports `googleads_invoice.*`; YAML from `outgoing_gluggle.yaml`. |
| `followup/` | New | Rules data + engine; not Gmail “follow-up”. |
| `cli.py`, `__main__.py` | New | Unified `invoice` CLI; lazy imports for heavy deps. |

### Tests, config, scripts

| Path | Disposition | Notes |
|------|-------------|--------|
| `tests/test_*.py` (googleads-focused) | Keep | Preserve fast suite; parity tests for wrap. |
| `tests/test_core/`, `test_classify/`, `test_sources/`, `test_handlers/`, `test_followup/`, `test_cli.py` | New | `invoice_admin` coverage. |
| `config/default.yaml`, `config/handlers/*.yaml` | New | Global + per-handler YAML; secrets via env only. |
| `scripts/` | Mixed | e.g. `seed_examples.py` for classifier JSONL. |

---

## 2. `swim` patterns adopted (reference: `/Users/chaehan/Software/Prototypes/swim/`)

| Pattern | How it shows up here |
|---------|----------------------|
| **PyPA `src/` layout** | `src/invoice_admin/`, `src/googleads_invoice/`; wheel `packages` in `pyproject.toml` lists both roots. |
| **Thin `__main__.py`** | Delegates to `cli.main()` only. |
| **Frozen dataclass config** | `InvoiceConfig`, `PathsConfig`, etc. in `core/config.py`. |
| **`repo_root()` discovery** | Env `INVOICE_ADMIN_REPO_ROOT`, walk to `pyproject.toml` from CWD and from `__file__`. |
| **argparse subcommands** | `invoice` subparsers mirror swim-style dispatch. |
| **Protocol over ABC** | `Handler` in `handlers/base.py`; `GmailBackend` remains protocol in `googleads_invoice`. |
| **`from __future__ import annotations`** | New modules use modern typing (`X \| None`). |
| **Single-line module docstrings** | Enforced on new package modules. |
| **Explicit `__all__` where it matters** | `invoice_admin.__init__` exports `__version__` per §5.1 S2. |
| **Defensive parse helpers** | e.g. `_safe_float` / `_str_field` in `core/pdf.py` return `None` instead of raising on bad fragments. |
| **YAML for data, Python for behavior** | Handler knobs in `config/handlers/`; no secrets in YAML. |

---

## 3. Explicit non-goals (this document)

- Does not replace **`docs/PROJECT_BRIEF_invoice_handler.md`** (product spec) or **`docs/IMPLEMENTATION_PLAN_invoice_handler.md`** (milestone + agent contract).
- Does not schedule **P1**; when executed, disposition table above is superseded by the merge plan in **`PLAN.md`**.
