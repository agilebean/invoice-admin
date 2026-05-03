# Constraints and workarounds (agile)

This repo **exists to automate a real monthly flow**: **Spark** (mail), **Brave** (Google Ads Documents / PDF), **`dry-run`**, and eventually **Gmail** send. Some runtimes **cannot** attach to your desktop apps “for free.” We treat that as **known constraints**, not as a reason to stop. Each row is **one problem → one workaround → how we know it works** (tests, markers, or iteration).

**How to use this doc:** When something blocks (agent in cloud, CI, no cookies), find the row, apply the workaround, run the ** cited command**, and only then mark the related **PLAN** slice done for **real** verification.

---

## Table (constraint → workaround → verification)

| # | **Constraint** | **Impact** | **Workaround (what we do)** | **Verify (Definition of Done)** |
|---|----------------|------------|-----------------------------|----------------------------------|
| C1 | **Remote agent / IDE** often has **no access** to **your** Brave process, Spark app, or macOS Automation permissions. | An agent cannot *by itself* complete `pytest -m live_brave` or `live_spark` on *your* session; it still **writes and maintains** the same tests you run locally. | Ship **`live_brave`** / **`live_spark`** as **opt-in** tests; **you** (or **`launchd`** on your Mac later) run them with env vars. Agent work = **code + docs + CI green on everything skippable**. | On **your Mac**: `RUN_LIVE_BRAVE=1` … `pytest -m live_brave` **passes**; `RUN_LIVE_SPARK=1` … `pytest -m live_spark` **passes** (see **README**). |
| C2 | **CI (GitHub Actions)** has **no** Google Ads login, **no** Spark, **no** Brave profile. | CI will **never** be the source of truth for “I see Documents logged-in.” | **Fast suite** uses **fixtures**; **skip in CI** for **`live_*`**, **`e2e`** (unless you later add a self-hosted Mac runner). Keep **one** thin HTTP check (**`integration`** + `GOOGLEADS_BILLING_DEEPLINK`) optional for redirect sanity. | **`pytest`** green on PRs; **`live_*`** **skipped** in CI, not failed. |
| C3 | **Embedded IDE browser** ≠ **Brave** (different cookie jar). | Opening Ads URLs there **misreports** login state. | **Never** treat IDE browser as acceptance for billing; use **`ChromeDriver` attach** to Brave (**`--remote-debugging-port`**) or manual Brave checklist — see **`.cursor/rules/brave-for-google-ads.mdc`**. | **`live_brave`** passes against **your** Brave only. |
| C4 | **Spark** exposes **no** stable public API in this repo for “search `payments-noreply` / subject line.” | We cannot programmatically pull the thread from Spark in CI. | **Now:** AppleScript **`get version`** + optional **`GOOGLEADS_SPARK_MAIL_HTML`** (**file you exported** from Spark). **Gmail API:** **`list-billing-mail`** with **`GOOGLEADS_OAUTH_TOKEN`** (read-only OAuth JSON) when you want search without Spark export — see **README**. **Later:** deeper macOS UI automation — **new story** in **PLAN** when you prioritise it. | **`live_spark`** passes; export test passes when path set. |
| C5 | **`mail-app-draft`** depends on **Mail.app** + **osascript** (macOS). | Linux/CI cannot exercise real Mail UI. | **`GOOGLEADS_CONFIRM_MAIL_APP_DRAFT`** gate; **pytest** mocks **`subprocess.run`**; you accept the visible draft on **your Mac**. | Draft opens locally; CI stays green on mocks. |
| C6 | **Gmail send** from automation needs **credentials** on the maintainer machine only. | CI cannot hold app passwords. | **SMTP + app password:** **`GOOGLEADS_GMAIL_SMTP_USER`** and **`GOOGLEADS_GMAIL_SMTP_APP_PASSWORD`** *or* (**preferred**) **`GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE`** (first line; **`chmod 600`**) + **`send-test-pdf`**; **never** commit secrets; **`GOOGLEADS_CONFIRM_TEST_SEND`** gate. | **`pytest`** mocks SMTP; **you** confirm real inbox with one manual send. |

---

## Agile sequencing (how this fits **PLAN**)

- **Iteration 8:** Real **paths** + **`dry-run`** (files on disk) — **no** requirement that CI touches Spark/Brave.
- **Iteration 9.1:** Optional **`integration`** HTTP deeplink (no UI).
- **Iteration 9.2+:** **`live_brave`** / **`live_spark`** = **maintainer-run** acceptance for **real** UI; each follow-up slice **narrows** the gap (Download click, schedule, Gmail read).
- **Retrospective habit:** When a limitation bites, **add or update a row** in the table above (constraint → workaround → verify), then add the **smallest** test or doc change — **same PR** if possible.

---

## Agent instruction (short)

- **Do** implement, extend, and fix **`live_brave`**, **`live_spark`**, **`dry-run`**, and browser helpers.
- **Do not** claim “real stack passed” until **`live_*`** has been run on a **maintainer Mac** (or you have a green log from **`launchd`** + log capture — future).
- **Do** document new limitations in **this file** + **PLAN** in the same agile spirit.
