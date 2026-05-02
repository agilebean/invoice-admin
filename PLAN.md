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

## Early iterations — agile scope (first sprints)

Each iteration closes with merged code, **pytest green in CI**, and **no OAuth/real Gmail/real Ads** unless stated.

---

### Iteration 1 — “Green pipeline”

| Field | Detail |
|--|--|
| **Story** | As a contributor, I can clone the repo and get an automated sanity check so future work stays safe to merge. |
| **In scope** | `pyproject.toml` (+ optional `uv`/`pip` ergonomics doc), runnable `pytest` baseline, trivial package layout (`src/…`), one smoke test asserting `True`, GitHub Action `pytest` on push/PR, `.gitignore` for Python/OS cruft |
| **Out of scope** | Gmail, Selenium, PDF parsing, PDF fixtures, OAuth, Brave |
| **Acceptance criteria** | Fresh checkout → documented `venv`/`uv sync` + `pytest` → pass locally; GH Actions completes green on repo default branch |

---

### Iteration 2 — “Billing link from mail body”

| Field | Detail |
|--|--|
| **Story** | As the pipeline, I can extract the invoice billing URL from a Gmail-style HTML snippet so downstream steps don’t scrape raw mail in tests. |
| **In scope** | Pure module e.g. `extract_billing_url(html: str) -> str`; fixtures under `tests/fixtures/gmail/` (min. 2: happy path + “no URL fails clearly”); error type(s) finalized in tests |
| **Out of scope** | Gmail API/network, redirect resolution, HEAD/GET probes, Selenium |
| **Acceptance criteria** | `pytest -q` exercises only fixtures; missing/malformed mail → stable exception + actionable message |

---

### Iteration 3 — “Money + invoice date inside PDF bytes”

| Field | Detail |
|--|--|
| **Story** | As automation, I can read invoice issue date + EUR total from PDF fixtures so renaming + templated email stay deterministic. |
| **In scope** | Pure functions e.g. `parse_invoice_pdf(path \| bytes)` returning date + Decimal amount; smallest **synthetic** PDFs checked in-repo (later add **redacted** real sample if layout differs) |
| **Out of scope** | OCR, Gmail, renaming template, Brave, mail send |
| **Acceptance criteria** | ≥3 fixtures covering: normal EUR “amount due”, European decimal commas if Google emits them; wrong file type → loud failure |

---

### Iterations 4+ (thin slices, keep order)

| # | Story headline | Rough scope |
|--|----------------|-------------|
| 4 | Filename + email body helpers | deterministic string builders from structs (date/month/€), unit tests |
| 5 | Gmail-send adapter façade | mocked API only in CI (`send`, optional `messages.list` façade); typed errors |
| 6 | PDF download glue | `@pytest.mark.e2e`; optional manual fallback doc |
| 7 | CLI orchestration | one entrypoint invoking pure steps; smoke with fakes |

---

## Watch-outs

- One process per Chromium `user-data-dir` → quit Brave or use a login-once automation profile.
- Zero secrets/redacted fixtures only in git.
