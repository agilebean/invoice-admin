# Real workflow, preflight checks, plain vocabulary

This file captures **your** monthly flow (Spark, Brave, Google Drive), **manual tests** you run before trusting automation, and words we use in **`PLAN.md`** / **`README.md`** without jargon.

**Runtime limits and how we still ship real integration (agents, CI, your Mac):** see **[`CONSTRAINTS_AND_WORKAROUNDS.md`](CONSTRAINTS_AND_WORKAROUNDS.md)**.

---

## Plain vocabulary

**Files in git for tests (“fixtures”)**  
Tiny **sample** HTML and PDF files live under `tests/fixtures/`. They are **only** there so `pytest` can run on every commit and prove things like: “we still find the billing link in HTML” and “we still read the invoice date and euros from a PDF.”

- They are **not** your real invoices.
- They are **not** your Google Drive files.
- Passing CI means **the code still understands that shape of file** — not that your live Google Ads account or this month’s mail succeeded.

**“Simulate the real thing” in tests**  
To get closer to production without putting secrets in git, you can point **local-only** env vars at **redacted** or **copy-pasted** exports on disk (see **`.env.example`**). CI keeps using the small samples in `tests/fixtures/`.

**Using *your* Brave — not the IDE browser**  
For **Google Ads billing / Documents / anything with your login**, automation and manual checks **must** use **your Brave** window (your cookies, your profile).

- **Do not** use Cursor’s **embedded / Glass** browser for those URLs. It is a **separate** browser instance **without** your Brave profile — you will usually see **sign-in** even when Brave is already logged in.
- **Do** attach **Selenium** to **Brave you already started with remote debugging**, or control Brave via **`user_data_dir`** only when Brave is **not** holding that profile (see **`src/googleads_invoice/browser_download.py`**: `build_chrome_options_for_remote_debugging`, `chrome_driver_attach`).

**One-time Brave setup (macOS, typical)**  
Quit Brave, then start it with a debug port (keep this window open for scripts/tests):

```bash
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  --remote-debugging-port=9222
```

Use **`127.0.0.1:9222`** as **`debuggerAddress`** (env **`GOOGLEADS_BROWSER_DEBUGGER_ADDRESS`** in **`.env.example`**).

For a **small automated real check** over plain HTTP (no browser, **no** your cookies), use **Iteration 9.1**: **`GOOGLEADS_BILLING_DEEPLINK`** + **`pytest -m integration tests/test_billing_deeplink_integration.py`**.

## Live pytest on your Mac (`live_brave`, `live_spark`)

See **`README.md`**. **`pytest -m live_brave`** attaches Selenium to **your** Brave (**`--remote-debugging-port`**) and asserts the URL reaches **`billing/documents`**. **`pytest -m live_spark`** runs AppleScript **`tell application "Spark" to get version`** and, if **`GOOGLEADS_SPARK_MAIL_HTML`** is set, runs **`extract_billing_url`** on that export. **CI always skips** these markers.

**Permissions:** macOS may prompt for **Automation** access for **Terminal** / your IDE when **`osascript`** talks to Spark.

---

## Your billing document flow (Brave)

From the billing email:

1. Use **“View your documents”** (or equivalent). The mail often contains a **short link** (`https://c.gle/...`) that **redirects** in the browser to Google Ads, e.g.  
   `https://ads.google.com/aw/billing/documents?viaDeeplink=VIEW_DOCUMENT&...`  
   (exact query parameters come from Google; **copy from the email** — do not commit live tracking URLs to the repo.)

2. On **Billing → Documents**, tab **TAX AND STATUTORY DOCUMENTS** (and filters like document type **Tax invoice / Invoice**), use **Download** on the **top row** (most recent issue date).

3. The browser typically saves the **raw** PDF to **`~/Downloads`** first. You may later **rename** and move it — for example into the Google Drive GluggleJug folder (see below).

**Schedule target (later slice, after real checks are green)**  
Aim for **2nd of each month at 05:00 GMT** — only after **9.1–9.x** integration tests and/or Brave-profile automation are proven. Do not schedule **launchd** before the smallest real-world slices pass.

**UI reference**  
Screenshot of the Documents table (top row + Download): [`images/google-ads-billing-documents.png`](images/google-ads-billing-documents.png) in this folder.

---

## Example renamed PDF (not the raw download name)

After you organize files, a **renamed** example path looks like:

`/Users/chaehan/Library/CloudStorage/GoogleDrive-chaehan.so@virtualfriend.chat/My Drive/2 Areas/GluggleJug/GluggleJug GoogleAds/2026-04-02 Glugglejug GoogleAds Invoice March €6,600.98.pdf`

Notes:

- That file is **already renamed**; Google’s default download filename in `~/Downloads` will differ.
- **`dry-run` / `parse_invoice_pdf`** must work on **either** the raw downloaded PDF **or** the renamed copy, as long as the **content** is still the invoice PDF.

---

## `dry-run` env vars (real paths)

The CLI-level file dry-run (`googleads-invoice dry-run`) is removed. The remaining dry-run is
the full `invoice send --dry-run` (Gmail search → Brave download → parse → print fields, no
email). For parser-only checks, use `pytest` with the committed fixtures or `parse_invoice_pdf`
from a Python shell.

Month/year in Jack’s email copy come **only** from the billing clock rule in code — no manual month flag.

---

## Manual preflight checklist (you perform these)

The repo **does not** drive Spark or send mail yet. Use this list before/after changing automation.

### A. Billing deeplink and documents page (**Brave only**)

1. Start **Brave** with **`--remote-debugging-port=9222`** (see **Using *your* Brave** above), **or** use the Brave window you already use daily **after** restarting it once with that flag when you need automation.

2. Open the **`c.gle`** link (or resolved `ads.google.com/aw/billing/documents?...`) **in that Brave**.

3. Confirm **Billing → Documents** and **Download** on the top row.

**Do not** use Cursor’s in-IDE browser to judge whether your session works.

*Pretest from an agent without your Brave: not valid for “am I logged in?” — only your Brave window counts.*

### B. Spark test message (real send)

In **Spark**:

1. Compose from **chaehan.so@gmail.com**.

2. Send a **test** message to **chaehan.so@virtualfriend.chat** (subject/body arbitrary).

3. Confirm delivery in the recipient mailbox.

*There is no Spark API in this repo yet; this step is manual until a later iteration chooses Gmail API, AppleScript, or another path.*

### C. Find the billing notification mail

Search mail (Spark or Gmail) for:

- **From:** `payments-noreply@google.com`
- **Subject contains:** `Google Ads: Your billing document is ready`

Open the latest matching thread and confirm it contains the **documents** deeplink you use in step A.

---

## Next iteration (backlog)

- **launchd** (or equivalent) for **2nd @ 05:00 GMT**.
- Browser automation (already-skipped **`e2e`** pattern) extended to: follow deeplink, **Documents**, **Download** top row, optional move/rename toward the Google Drive convention.
- Optional: read/search mail via **Gmail API** instead of Spark export, when OAuth is in scope.

See **`PLAN.md`** — **Iteration 9 (backlog)**.
