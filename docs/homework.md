# Homework

Pending work and setup instructions for `invoice-admin`.

---

## IMAP watch setup

`invoice watch --source imap` polls an IMAP mailbox for unseen invoice emails and auto-ingests their PDF attachments or HTML bodies.

### Required env vars

| Variable | Description |
|---|---|
| `INVOICE_ADMIN_IMAP_HOST` | IMAP server hostname (e.g. `imap.gmail.com` for Gmail, `imap.mail.me.com` for iCloud) |
| `INVOICE_ADMIN_IMAP_USER` | IMAP login username (usually full email address) |
| `INVOICE_ADMIN_IMAP_PASSWORD` | IMAP password. For Gmail: use an [App Password](https://myaccount.google.com/apppasswords) (requires 2FA enabled). Never use your account password. |

### Optional env vars

| Variable | Default | Description |
|---|---|---|
| `INVOICE_ADMIN_IMAP_MAILBOX` | `INBOX` | Mailbox to watch (e.g. `[Gmail]/All Mail`) |
| `INVOICE_ADMIN_IMAP_POLL_SECONDS` | `60` | Polling interval in seconds (minimum 10) |

### How it works

1. Connects via IMAPS (SSL) to `INVOICE_ADMIN_IMAP_HOST`
2. Logs in with `INVOICE_ADMIN_IMAP_USER` / `INVOICE_ADMIN_IMAP_PASSWORD`
3. Selects `INVOICE_ADMIN_IMAP_MAILBOX`
4. Searches for `UNSEEN` messages
5. For each unseen message, checks for:
   - PDF attachments (takes first one, logs warning if multiple)
   - HTML body with invoice-like subject (`invoice`, `rechnung`, `bill`, `facture`, `payment due`)
6. Ingests each matching email via the normal pipeline: PDF extraction → classification → tracker row
7. Sleeps `INVOICE_ADMIN_IMAP_POLL_SECONDS`, then repeats

### Idempotency

Each email's `Message-ID` header is used as the `source_ref` in the tracker. Re-processing the same email is a no-op (UNIQUE constraint).

### Providers

**Gmail** — enable 2FA, generate an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), use:
```
INVOICE_ADMIN_IMAP_HOST=imap.gmail.com
```

**iCloud** — generate an app-specific password at [appleid.apple.com](https://appleid.apple.com), use:
```
INVOICE_ADMIN_IMAP_HOST=imap.mail.me.com
```

**Fastmail** — generate an app password in Settings → Privacy & Security, use:
```
INVOICE_ADMIN_IMAP_HOST=imap.fastmail.com
```
