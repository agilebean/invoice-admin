# Monthly flow plan + interview (steps 1 → 4)

**Implementation order** is always Step **1** through **4** below. When *designing* slices, it can help to reason *outcomes-first* from step 4 back to 1—but the repo ships and documents work in **forward** order.

Each slice has **acceptance on your Mac** where apps are involved; CI keeps **fast mocks + fixtures**.

**How this file uses Markdown:** Use **double asterisks** only *outside* of ``backticks`` for bold. Inside ``...``, text is monospace and **not** parsed for bold—so ``**foo**`` would show the stars literally (that was the bug). *Triple asterisks* (`***text**`*) mean **bold and italic** together in normal prose; avoid mixing them with ``code`` spans.

---

## Implementation order (do steps in this sequence)


| Step  | Outcome (what “done” looks like)                                                                                                                                                                                          | Likely slice / tech                                                                                                                                  |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | Send **one** email from `chaehan.so@gmail.com` with **PDF attachment** (bytes from `tests/fixtures/pdf/invoice_eur_dot_decimal.pdf`); subject/body from `build_email_*` + billing month.                                  | **Shipped:** `googleads-invoice send-test-pdf` + `SmtpGmailBackend` (`GOOGLEADS_GMAIL_SMTP_*`, `GOOGLEADS_CONFIRM_TEST_SEND=1`). See **PLAN §10.1**. |
| **2** | **Same** test email (subject/body + PDF) in **Mail.app** (visible draft) so you can **Send** from the Mac MUA or duplicate into **Spark**—matching how Jack sees it.                                                      | **Shipped:** `googleads-invoice mail-app-draft` (`GOOGLEADS_CONFIRM_MAIL_APP_DRAFT=1`, macOS + Mail.app).                                            |
| **3** | Find **Google Ads billing notification** in mail: `payments-noreply@google.com`, subject contains “Google Ads: Your billing document is ready” — **Gmail API** `q=` search (and/or Spark export + `extract_billing_url`). | **Shipped:** `list-billing-mail`, `**billing-url-from-gmail`** (fetch HTML → print billing URL).                                                     |
| **4** | Open billing **Documents** in **real Brave**, identify URLs/UI (what Selenium must target).                                                                                                                               | `**live_brave`** + optional `**RUN_LIVE_BRAVE_TRACE=1**` (HTML + PNG under `~/Downloads` or `**GOOGLEADS_LIVE_BRAVE_TRACE_DIR**`).                   |


---

## Interview — please answer (copy/paste under each)

### A. Email send (slice 1 — Gmail)

- **A1.** Confirm **From** address: still `chaehan.so@gmail.com` for all automated sends?
- **A2.** For **SMTP** (first implementation): can you create a **Gmail app password** for this account and use env `GMAIL_APP_PASSWORD` (never commit)? **Yes / No / Prefer OAuth later only**
- **A3.** **Test recipient** for the first real send: `chaehan.so@virtualfriend.chat` only, or also `jack.copeland@theglugglejugfactory.com`, or another?
- **A4.** Should the **PDF** attach as the **raw fixture file** only, or **renamed** to match `build_renamed_pdf_filename` from `dry-run` output (same bytes, different filename)?
- **A5.** Subject/body: use a fixed “[TEST] Google Ads invoice attachment” line, or mirror `build_email_subject` / `build_email_body` with `billing_month_label_for_previous_calendar_month()`?

### B. Spark / Mac mail (slice 2)

- **B1.** For “send **via Spark**”: is **manual** “duplicate this message in Spark” after SMTP send OK for this iteration, or must it be **scripted** (AppleScript/UI)?
- **B2.** If scripted Spark: **Spark** menu path you’d accept for “New message / Send” (or are you OK with **Mail.app** AppleScript first because it’s scriptable)?
- **B3.** Any **corporate / 2FA** constraint that blocks AppleScript controlling Spark?

### C. Find notification (slice 3)

- **C1.** Exact **Gmail search** you want codified: e.g. `from:payments-noreply@google.com subject:"Google Ads: Your billing document is ready"` — confirm or paste yours.
- **C2.** **Spark:** do you already **export** that thread to HTML for `dry-run`, or do you want **Gmail API** search first (no Spark dependency)?
- **C3.** How many **recent** messages to list (default **10**)?

### D. Brave / Documents (slice 4)

- **D1.** Confirm Brave starts with `--remote-debugging-port=9222` when you run `live_brave` tests.
- **D2.** After **“View your documents”**, does the URL **always** land on `…/billing/documents` or sometimes intermediate pages?
- **D3.** Should we **save** HTML + screenshot to `./artifacts/` (gitignored) when `RUN_LIVE_BRAVE_TRACE=1` for identification?

### E. Safety

- **E1.** Hard rule: **never** send to Jack’s real address without `I_CONFIRM_PROD_SEND=1` — **Yes adopt / No**?

---

## Recorded answers (2026-05-02)

Captured from the structured interview in Cursor; use this as the working default until changed.


| Topic                                   | Decision                                                                                                                                                                                                                                      |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SMTP secret**                         | Gmail **app password** via `GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE` (first line of a local file; `chmod 600`; never commit). Inline `GOOGLEADS_GMAIL_SMTP_APP_PASSWORD` remains supported; file wins when both are set.                       |
| **Attachment filename**                 | Default attachment name follows `build_renamed_pdf_filename` (same as production / dry-run naming); optional `--attachment-name` override.                                                                                                    |
| **Steps 2–3 (Mac mail + inbox search)** | **Evaluate** Mail.app, Spark UI, and Gmail API (`q=` search); **pick the simplest** path for the next slice (no fixed winner yet).                                                                                                            |
| **Brave / trace artifacts**             | Prefer `~/Downloads` for saved HTML/screenshots when tracing — **not** `./artifacts/` by default.                                                                                                                                             |
| **Jack / production guard**             | **No** separate env gate for Jack’s address beyond what `send-test-pdf` already requires `GOOGLEADS_CONFIRM_TEST_SEND=1`; treat recipient choice as manual discipline.                                                                        |
| **Canonical addresses**                 | **From:** `chaehan.so@gmail.com` (default SMTP user if unset). **Default To** when `--to` omitted: `chaehan.so@virtualfriend.chat`, overridable with `GOOGLEADS_INVOICE_TO` (e.g. `jack.copeland@theglugglejugfactory.com` for monthly send). |
| **Gmail OAuth app name**               | `chaehan-gmail-access` (Google Cloud Console OAuth client; reusable for other personal Gmail scripts). |
| **App password file path**             | `~/.gmail/gmail-smtp-app-password` (SMTP app password in the same `.gmail` directory as the OAuth token). |


---

## After answers

- Update **PLAN.md** Iteration 10+ (or expand 9.x) with **your** accepted queries and **Definition of Done** per step.
- Extend **docs/CONSTRAINTS_AND_WORKAROUNDS.md** if a new constraint row (e.g. **C4**, **B1**) appears.

---

## Google Cloud Console UI update (2026)

The **OAuth consent screen** is now at **Google Auth Platform → Data Access**:

- **Add scopes** (e.g. `https://www.googleapis.com/auth/gmail.readonly`) under **Google Auth Platform → Data Access → Add Scopes**.
- **Add test users** (e.g. `chaehan.so@gmail.com`) under **Google Auth Platform → Data Access → Audience → Test users → Add users**.
- Keep the app in **Testing** mode (no need to publish); publishing requires a security review.

**Token generation:** run `python scripts/get_oauth_token.py` after setting up scopes + test users.

