# Google Ads invoice → Jack

Repo: https://github.com/SoHu-Labs/googleads-invoice-glugglejug

## Goal

Monthly: read billing mail on `chaehan.so@gmail.com` (Gmail API), open invoice link via **headed** Brave/Chromium + WebDriver + saved profile, download PDF, parse date + EUR, rename file, reply-path email to `jack.copeland@theglugglejugfactory.com` from the same Gmail account.

## Flow

`Gmail (find payments-noreply) → extract URL → WebDriver downloads PDF → parse → rename → Gmail send`

## Stack

Python 3.12+, pytest, Gmail API SDK, Selenium 4 (+ driver), PDF lib (pdfplumber or PyMuPDF), GitHub Actions, `launchd` when stable.

## Delivery (agile, strict TDD)

- Thin vertical slices (~½–2 days), one logical PR per slice.
- Strict TDD: failing test → minimum code → green → refactor — no new behavior without a red test first.
- CI (`pytest`) on every push + PR — full fast suite must pass.

## Regression tests

- **Fast path (CI):** unit + adapters on committed fixtures (`tests/fixtures`): redacted Gmail HTML, tiny synthetic PDFs.
- **`@pytest.mark.e2e`:** headed WebDriver; default skip in CI, run locally (`pytest -m e2e`) unless you later add a runner.
- Bugs: reproduce with a failing fixture/test before fixing.

## Story map (summary)

**Themes → stories (1:n):** each **theme** can span **several rows**; each **row** is **exactly one story** and matches **one iteration** in the sections below (one slice = one story). Read **Iteration** for the slice label, **Story** for the maintainer outcome only.

| Theme | Iteration | Story |
|--|--|--|
| **Merge safety & ergonomics** | **1** · Green pipeline | I can **clone, install, and run `pytest`** locally knowing **CI runs the same checks**, so I’m not guessing whether packaging or the workflow is broken before real integrations land. |
| **From inbox to PDF on disk** | **2** · Billing link from mail body | I can feed **saved Gmail-style HTML** to **`extract_billing_url`** and get the **billing URL or a clear error**, instead of hand-searching anchors or pasting links blindly each month. |
| **From inbox to PDF on disk** | **6** · PDF download glue | I can run a **local `@pytest.mark.e2e`** path with a **real browser profile** to **download the invoice PDF** while **CI stays fast**, when a straight HTTP fetch isn’t enough. |
| **What the invoice says** | **3** · Money + invoice date in PDF | I can run **`parse_invoice_pdf`** on **tiny synthetic PDFs** in git and get **issue date + EUR**, so rename and email logic stay **tests-first** without Acrobat or live Ads for every case. |
| **What Jack receives** | **4** · Filename + email helpers | I can derive **filename and email fragments** from **structured date / month / €** with **pure helpers**, so naming and Jack’s message stay **repeatable** instead of hand-edited each run. |
| **Send from your mailbox** | **5** · Gmail-send adapter | I can drive **list/send** through a **small adapter** backed by **mocks in CI**, so Gmail integration is **shaped and regressable** **without OAuth in tests**. |
| **Run the month** | **7** · CLI orchestration | I can drive the **full sequence from one CLI** (with **fakes in unit tests**), so I **operate** the monthly flow **end-to-end** instead of chaining one-off scripts. |

*Row order here follows **user journey** (inbox → file → meaning → outputs → send → operate). **Delivery order** for slices remains **1 → 2 → 3 → … → 7** in **Early iterations** (e.g. PDF parse before filename helpers).*

## Early iterations — agile scope (first sprints)

**Implementation status:** an iteration heading ends with **✅** when that slice is merged and **CI is green**; leave unrated until then. Each table’s **Retrospective** row captures lessons for later slices.

Each iteration closes with merged code, **pytest green in CI**, and **no OAuth/real Gmail/real Ads** unless stated.

---

### Iteration 1 — “Green pipeline” ✅

| Field | Detail |
|--|--|
| **Story** | As the repo maintainer, I can clone a clean copy, follow the README setup, and run **`pytest`** locally while **CI runs the same checks on push/PR**, so I no longer wonder whether packaging, imports, or the workflow are miswired before I add real Gmail/PDF logic. |
| **In scope** | `pyproject.toml` (+ optional `uv`/`pip` ergonomics doc), runnable `pytest` baseline, trivial package layout (`src/…`), one smoke test asserting `True`, GitHub Action `pytest` on push/PR, `.gitignore` for Python/OS cruft |
| **Out of scope** | Gmail, Selenium, PDF parsing, PDF fixtures, OAuth, Brave |
| **Acceptance criteria** | Fresh checkout → documented `venv`/`uv sync` + `pytest` → pass locally; GH Actions completes green on repo default branch |
| **Retrospective** | **Smoke vs `assert True`:** import + `__version__` gives a stronger “package wired correctly” signal without extra deps.<br><br>**Pytest + `src/`:** `[tool.pytest.ini_options] pythonpath = ["src"]` keeps `pytest` working without an editable install; CI still uses `pip install -e ".[dev]"` so packaging stays exercised.<br><br>**Hatchling:** wheel `packages = ["src/googleads_invoice"]` matches the layout—if package name or paths move, update wheel config and pytest `pythonpath` together.<br><br>**uv:** README documents `uv pip install -e ".[dev]"` because there is no lockfile yet; consider `[dependency-groups]` + `uv sync` later if the team standardizes on lockfiles.<br><br>**CI:** workflow pins push to `main`; rename default branch or use multiple protected branches → adjust `on.push.branches`. |

---

### Iteration 2 — “Billing link from mail body” ✅

| Field | Detail |
|--|--|
| **Story** | As the repo maintainer, I can pass saved **Gmail-style HTML** (fixtures or redacted exports) through **`extract_billing_url`** and get the **invoice billing URL**—or a **clear, typed failure** when there isn’t one—so I’m not hand-searching `<a href>` tags or copying links blind every month. |
| **In scope** | Pure module e.g. `extract_billing_url(html: str) -> str`; fixtures under `tests/fixtures/gmail/` (min. 2: happy path + “no URL fails clearly”); error type(s) finalized in tests |
| **Out of scope** | Gmail API/network, redirect resolution, HEAD/GET probes, Selenium |
| **Acceptance criteria** | `pytest -q` exercises only fixtures; missing/malformed mail → stable exception + actionable message |
| **Retrospective** | **stdlib only:** `html.parser.HTMLParser` plus `urllib.parse` avoids a third-party HTML dependency for simple `href` collection; revisit if mail uses heavy obfuscation or non-`<a>` links.<br><br>**Host allowlist:** billing detection is `_BILLING_NETLOCS` (`payments.google.com`, `pay.google.com`)—add hosts in one place and lock each with a fixture when real mail differs.<br><br>**First match:** the first qualifying anchor wins; if product later needs a tie-break (e.g. “View invoice” vs footer), encode that in tests before changing selection.<br><br>**Errors:** `BillingUrlNotFoundError` subclasses `ValueError` for a stable, specific catch while staying compatible with broad `ValueError` handlers. |

---

### Iteration 3 — “Money + invoice date inside PDF bytes” ✅

| Field | Detail |
|--|--|
| **Story** | As the repo maintainer, I can point **`parse_invoice_pdf`** at **small synthetic invoice PDFs** in git and read **issue date + EUR total** as structured values, so I can reason about rename rules and email copy **without opening Acrobat for every edge case** and **without live Google Ads**. |
| **In scope** | Pure functions e.g. `parse_invoice_pdf(path \| bytes)` returning date + Decimal amount; smallest **synthetic** PDFs checked in-repo (later add **redacted** real sample if layout differs) |
| **Out of scope** | OCR, Gmail, renaming template, Brave, mail send |
| **Acceptance criteria** | ≥3 fixtures covering: normal EUR “amount due”, European decimal commas if Google emits them; wrong file type → loud failure |
| **Retrospective** | **Library:** **`pypdf`** covers text extraction for tiny synthetic PDFs; **pdfplumber / PyMuPDF** remain options if layout/encoding gets harder—swap behind the same `parse_invoice_pdf` contract and keep fixtures assertive.<br><br>**How fixtures were made:** PDFs were generated **once** with **reportlab** in a dev venv and **committed**; **reportlab is not** a declared project dependency so CI stays lean—regenerate only when fixture content must change.<br><br>**Parsing contract:** implementation keys off **`Invoice date: YYYY-MM-DD`** and **`Amount due:`** plus EUR normalization (**`1,234.56`** vs **`1.234,56`**); real Google invoices may use different copy—add a **redacted real PDF** fixture before trusting production mail PDFs.<br><br>**Errors:** **`InvoicePdfError`** subclasses **`ValueError`**; non-PDF / corrupt bytes surface as **`InvoicePdfError`** wrapping **`PdfReadError`** so callers get one family for “can’t read / can’t parse”. |

---

### Iteration 4 — “Filename + email helpers” ✅

| Field | Detail |
|--|--|
| **Story** | As the repo maintainer, I can turn **parsed date + euros (+ month label)** into **filename and email-body fragments** via pure helpers, so each run’s naming and Jack’s message stay **repeatable and test-covered** instead of hand-edited strings. |
| **In scope** | Frozen struct **`InvoiceOutputFields`**; pure builders **`build_renamed_pdf_filename`**, **`build_email_subject`**, **`build_email_body`**; unit tests only |
| **Out of scope** | Gmail send, actual rename on disk, HTML email, localization beyond provided **`month_label`**, Jack’s real address in constants |
| **Acceptance criteria** | **`pytest -q`** locks strings for representative dates/amounts (incl. whole-euro filename stem); changing copy requires updating tests deliberately |
| **Retrospective** | **Single struct:** **`InvoiceOutputFields`** keeps PDF output + mail copy aligned—add fields in one place if CC/subject templates grow.<br><br>**`month_label`:** callers supply the human month string (e.g. “March 2026”); **no locale guessing** in the library—derive in the CLI/orchestrator when you add **`babel`** or a simple map if needed.<br><br>**Amount formatting:** filenames use a **trimmed plain** amount (**`1000`** not **`1000.00`**); email uses **two decimal places**—if you need one style everywhere, pick one and adjust tests.<br><br>**Copy is a contract:** greeting and em dash in subject/body are **frozen by tests**; tweak wording only when Jack agrees and you update assertions. |

---

### Iterations 5+ (thin slices, keep order)

| # | Story | Rough scope |
|--|----------------|-------------|
| 5 | As the repo maintainer, I can exercise **“list / send mail”** through a **small adapter** with **mocks in CI**, so I can integrate Gmail later **without OAuth in tests** and still catch API-shape mistakes early. | mocked API only in CI (`send`, optional `messages.list` façade); typed errors |
| 6 | As the repo maintainer, I can run an **`@pytest.mark.e2e`** path locally that uses a **headed browser profile** to **download the invoice PDF**, with CI staying fast/skipped—so I’m not blocked when pure HTTP won’t suffice, and there’s an honest place for “real browser” behavior. | `@pytest.mark.e2e`; optional manual fallback doc |
| 7 | As the repo maintainer, I can drive the **full monthly sequence from one CLI entrypoint** (pure steps + injected fakes in tests), so I can actually **operate** the flow end-to-end instead of stitching one-off scripts together. | one entrypoint invoking pure steps; smoke with fakes |
| **Retrospective** | *Add a short note per row (or per PR) when #5–#7 ship—patterns for fakes vs live, e2e skips, CLI UX.* | |

---

## Watch-outs

- One process per Chromium `user-data-dir` → quit Brave or use a login-once automation profile.
- Zero secrets/redacted fixtures only in git.
