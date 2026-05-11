# save-commission-pdf — Implementation Plan

This feature lets the user run a CLI command that:

1. Searches Gmail for emails from Jack Copeland containing "commission"
2. Downloads the first PDF attachment from the first matching email
3. Parses the PDF to extract the date (→ `YYYY-MM`) and EUR amount
4. Renames the PDF to `YYYY-MM Commission {FullMonthName} €{AMOUNT}.pdf` (e.g. `2026-03 Commission March €1,755.73.pdf` — full English month after “Commission”, thousands separators in the amount, no space between `€` and the digits)
5. Moves it into the commissions directory (same path as `DROPBOX_INVOICE_DIR` in `addresses.py`)
6. Leaves the email in the inbox unchanged (don't mark read, don't delete)

---

## 1. New file: `src/googleads_invoice/save_commission_pdf.py`

This is the orchestrator module, analogous to `run_month.py` but simpler (no Brave download and no SMTP send).

### 1a. Dataclass: `SaveCommissionReport`

Use `@dataclass(frozen=True)`. Fields:

| Field | Type | Description |
|---|---|---|
| `message_id` | `str` | Gmail message ID of the email that contained the PDF |
| `pdf_path` | `Path` | Where the PDF ended up in the commissions directory |
| `commission_date` | `date` | Date derived from email subject + sent date (e.g. `date(2026, 3, 1)` for "March") |
| `amount_eur` | `Decimal` | EUR amount extracted from the PDF (last row of table) |
| `renamed_filename` | `str` | Final filename, e.g. `2026-03 Commission March €1,755.73.pdf` |
| `steps` | `list[str]` | Human-readable progress log (default empty list) |

### 1b. Function: `save_commission_pdf(...) -> SaveCommissionReport`

Signature:

```python
def save_commission_pdf(
    *,
    gmail_read_backend: GmailApiReadBackend,
    commission_query: str,
    max_scan: int = 10,
    commission_dir: Path | None = None,
    test_run: bool = False,
) -> SaveCommissionReport:
```

When `test_run=True`, Step 5 saves the renamed PDF to `~/Downloads` instead of the commissions directory. The rest of the flow is identical.

Internally, it must do these steps IN ORDER. Use the step-progress logging pattern from `run_month.py:90-96` (timed prints like `[1/4] +0.5s/0.5s Doing X...`).

#### Step 1: Search Gmail for commission emails

- Call `gmail_read_backend.list_messages(commission_query, max_results=max_scan)` exactly like `run_month.py:103-105`.
- If the returned list is empty, raise `SaveCommissionPdfError("No commission emails found for query {commission_query!r}")`.
- Log the number of matches found.

#### Step 2: Get email metadata + download the first PDF attachment

- Iterate over the returned messages (in order; first match wins).
- For each message, call a **new method** on `GmailApiReadBackend` — see Section 2 below — to get the email's subject, sent date, and PDF attachment in one call.
- The new method is named `get_message_pdf_with_metadata(self, message_id: str) -> tuple[bytes, str, int] | None`.
  - It returns `(pdf_bytes, subject, internal_date_ms)` on success, or `None` if no PDF attachment.
  - The `internal_date_ms` is the Gmail `internalDate` field (epoch milliseconds), used to derive the year.
- If it returns `None` for a message, skip to the next message.
- If it returns a tuple, unpack it and break out of the loop.
- If no message has a PDF attachment, raise `SaveCommissionPdfError("No PDF attachment found in any of the {N} matching commission emails")`.

#### Step 3: Derive date from email + parse EUR from PDF

- **Month**: extract the first month name (full or abbreviated) from the email subject using a regex. Example subjects: `"Invoice March Commission (EUR)"` → `"March"`, `"April 2026 Commission.pdf"` → `"April"`. Use the same regex from `invoice_pdf.py:50-56` (`January|February|...|December|Jan|Feb|...|Dec`). If no month is found, raise `SaveCommissionPdfError("Could not find month in email subject: {subject!r}")`.
- **Year**: derive from the `internal_date_ms` timestamp using **UTC** (Gmail epoch ms): `datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc).year`. Fallback: if `internal_date_ms` is 0 or unusable, use `date.today().year`.
- **commission_date**: `date(year, month_number, 1)` — first day of that month.
- **EUR amount**: write the raw PDF bytes to a temp file using `tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)`, then call `parse_commission_pdf(temp_file_path)` (a new function — see below). This function ONLY extracts the EUR total from the last table row (ignoring invoice dates). See Section 6 for its exact contract.
  - If parsing fails, clean up the temp file with `Path(temp_file_path).unlink(missing_ok=True)` and re-raise as `SaveCommissionPdfError`.
- On parse **success**, keep the temp file — Step 4 will consume it via `shutil.move`, which removes the source.
- Store the `commission_date` and `amount_eur`.

```python
# Month-name to number helper (place in save_commission_pdf.py or commission_pdf.py)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
```

#### Step 4: Build the renamed filename

- **`month_display`**: full English month name from `commission_date` — `calendar.month_name[commission_date.month]` (e.g. `"March"`).
- **`amount_str`**: use `_eur_commission_filename_amount()` from `src/googleads_invoice/invoice_artifacts.py` (same quantize-and-strip rules as `_eur_plain_amount`, plus **comma thousands grouping** — e.g. `1755.73` → `1,755.73`, `1755.00` → `1,755`). **Reuse that helper — do NOT copy.**

Build the filename **exactly** as (note: **no space** between `€` and the amount digits):

```
f"{commission_date.year}-{commission_date.month:02d} Commission {month_display} €{amount_str}.pdf"
```

Example: `date(2026, 3, 1)` and `Decimal("1755.73")` → `"2026-03 Commission March €1,755.73.pdf"`.

If the resolved email subject used an abbreviation (e.g. “Mar”), the filename still uses the **full** month name from `commission_date` so the folder listing always shows both `YYYY-MM` and the spelled-out month.

#### Step 5: Save to destination

- If `test_run` is True: use `Path.home() / "Downloads"` as the destination directory.
- If `test_run` is False: resolve `commission_dir` — if `None`, default to `Path(DROPBOX_INVOICE_DIR).expanduser()` (import from `src/googleads_invoice/addresses.py:29-31`).
- Create the directory: `dest_dir.mkdir(parents=True, exist_ok=True)`.
- Determine the destination path: `dest = dest_dir / renamed_filename`.
- If `dest.is_file()` is True, apply versioned naming **exactly** like `run_month.py:190-197`:
  - Extract `stem = dest.stem` and `ext = dest.suffix`.
  - For `i` in `range(1, 100)`: try `dest_dir / f"{stem} ({i}){ext}"`. If it doesn't exist, use that.
- Move the file with a single call: `shutil.move(str(temp_pdf_path), str(dest))` where `temp_pdf_path` is the temp file from Step 3 and `dest` is the final destination path (with the renamed filename). No second move needed — `shutil.move` renames as it moves.
- Verify: `if not dest.is_file(): raise SaveCommissionPdfError(...)` — same guard as `run_month.py:200-201`.
- Log the final path.

### 1c. Error class

```python
class SaveCommissionPdfError(RuntimeError):
    """A step in save-commission-pdf failed."""
```

---

## 2. Modify: `src/googleads_invoice/gmail_api_backend.py`

Add a new public method to `GmailApiReadBackend`:

### `get_message_pdf_with_metadata(self, message_id: str) -> tuple[bytes, str, int] | None`

Return `(pdf_bytes, subject, internal_date_ms)` if a PDF attachment is found, else `None`.

1. Call the Gmail API `users().messages().get(userId="me", id=message_id, format="full")`.
2. Extract the **subject** from `full["payload"]["headers"]` — find the header with `name == "Subject"`, return its `value`. If not found, use `""`.
3. Extract **internalDate** from `full["internalDate"]` (epoch ms as string). Convert to `int`. If missing or `"0"`, use `0`.
4. Get the `payload` dict from `full["payload"]`.
5. Walk the MIME tree recursively to find a part where:
   - `mimeType` (case-insensitive) is `application/pdf`, or `application/octet-stream` with a `filename` ending in `.pdf`, or any part with `filename` ending in `.pdf`.
   - The part's `body` dict has a non-empty `attachmentId` string.
6. If no matching part, return `None`.
7. Call `users().messages().attachments().get(messageId=message_id, id=attachmentId).execute()`.
8. The response dict has a `data` field (base64url-encoded). Decode using the existing `_urlsafe_b64decode` helper at `gmail_api_backend.py:32-34`.
9. Return `(pdf_bytes, subject, internal_date_ms)`.
10. Wrap `HttpError` in `GmailTransportError` (same pattern as existing methods).

Guidance on the MIME tree walk:
- Start with `payload = full.get("payload") or {}`.
- If `payload.get("mimeType")` is `"multipart/*"`, recurse into `payload.get("parts", [])`.
- Create a helper `_find_pdf_attachment_part(payload: dict) -> dict | None` that returns the matching part dict or `None`.
- The check for each part: `filename = part.get("filename", "")` and `attachment_id = (part.get("body") or {}).get("attachmentId", "")`. If `filename.lower().endswith(".pdf")` or `(part.get("mimeType") or "").lower() == "application/pdf"`, and `attachment_id`, return this part.

---

## 3. Modify: `src/googleads_invoice/cli.py`

### 3a. Add a new subcommand: `save-commission-pdf`

Registration:
- After the existing `url_p` subparser (around line 329), add a new subparser.
- Use `sub.add_parser("save-commission-pdf", help="...")`.
- The help text: `"Search Gmail for commission emails from Jack Copeland, download the PDF attachment, parse it, and save to the commissions directory."`
- Add one flag: `--test-run` (`action="store_true", default=False`). Help: `"Test mode: skip confirmation prompt, save PDF to ~/Downloads instead of commissions directory."`
- **No `--to`, no `--pdf`, no env var guard.** Just `--test-run`.

No env var guard. Instead, use an interactive confirmation prompt (matching `run-month`'s `input("Confirm? (Y/n): ")` at `cli.py:387-404`).

### 3b. Add a new default search query constant

In `src/googleads_invoice/gmail_api_backend.py`, add:

```python
DEFAULT_COMMISSION_MAIL_QUERY = (
    'from:jack.copeland@theglugglejugfactory.com commission'
)
```

Write a function `commission_mail_query_from_env()` in `gmail_api_backend.py` that returns `os.environ.get("GOOGLEADS_COMMISSION_QUERY")` or `DEFAULT_COMMISSION_MAIL_QUERY`. **Pattern**: same as `billing_mail_query_from_env()` at `gmail_api_backend.py:64-67`.

### 3c. CLI handler logic (inside `main()`)

After all the `if args.command == "X":` blocks, add:

```python
if args.command == "save-commission-pdf":
    query = commission_mail_query_from_env()

    try:
        backend = GmailApiReadBackend.from_env()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not args.test_run:
        # Interactive confirmation — same pattern as run-month at cli.py:387-404
        print(
            f"About to save commission PDF:",
            file=sys.stderr,
        )
        print(f"  Query: {query}", file=sys.stderr)
        print(f"  Destination: {DROPBOX_INVOICE_DIR}", file=sys.stderr)
        try:
            confirm = input("  Confirm? (Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm not in ("", "y", "yes"):
            print("Aborted.", file=sys.stderr)
            return 2

    try:
        report = save_commission_pdf(
            gmail_read_backend=backend,
            commission_query=query,
            test_run=args.test_run,
        )
    except SaveCommissionPdfError as e:
        print(str(e), file=sys.stderr)
        return 2

    print("Commission PDF saved successfully.", file=sys.stderr)
    print(f"  Email: {report.message_id}", file=sys.stderr)
    print(f"  PDF: {report.pdf_path}", file=sys.stderr)
    print(f"  Date: {report.commission_date}, EUR {report.amount_eur}", file=sys.stderr)
    print(f"  Renamed: {report.renamed_filename}", file=sys.stderr)
    return 0
```

---

## 4. New test file: `tests/test_save_commission_pdf.py`

Follow the exact patterns from `tests/test_run_month.py`.

### 4a. Fixtures

- `mock_gmail_backend()` — similar to `test_run_month.py:20-28`, but provides `get_message_pdf_with_metadata` returning `(pdf_bytes, subject, internal_date_ms)`.
  ```python
  @pytest.fixture
  def mock_gmail_backend() -> MagicMock:
      bk = MagicMock()
      bk.list_messages.return_value = [
          GmailMessageSummary(id="msg1", thread_id="t1", snippet="commission"),
      ]
      fixture_pdf = (
          Path(__file__).resolve().parent
          / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
      )
      # Return (pdf_bytes, subject, internal_date_ms)
      # Subject contains "March" → month 3; internal date → 2026
      bk.get_message_pdf_with_metadata.return_value = (
          fixture_pdf.read_bytes(),
          "Invoice March Commission (EUR)",
          1740787200000,  # 2026-03-01 in epoch ms
      )
      return bk
  ```

### 4b. Happy-path test

```python
def test_save_commission_pdf_happy_path(
    mock_gmail_backend: MagicMock,
    tmp_path: Path,
) -> None:
    report = save_commission_pdf(
        gmail_read_backend=mock_gmail_backend,
        commission_query='from:jack.copeland@theglugglejugfactory.com commission',
        max_scan=10,
        commission_dir=tmp_path,
    )

    assert report.message_id == "msg1"
    assert report.commission_date == date(2026, 3, 1)
    assert report.amount_eur == Decimal("1234.56")
    assert report.renamed_filename == "2026-03 Commission March €1,234.56.pdf"
    assert "March" in report.renamed_filename
    assert "Commission" in report.renamed_filename
    assert report.renamed_filename.startswith("2026-03")
    assert "€1,234.56" in report.renamed_filename
    assert report.renamed_filename.endswith(".pdf")
    assert report.pdf_path.is_file()
    assert report.pdf_path.parent == tmp_path
    assert report.pdf_path.name == report.renamed_filename
```

### 4c. Error-path tests

#### No emails found

```python
def test_save_commission_pdf_no_emails(tmp_path: Path) -> None:
    bk = MagicMock()
    bk.list_messages.return_value = []
    with pytest.raises(SaveCommissionPdfError, match="No commission emails"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
        )
```

#### No PDF attachment

```python
def test_save_commission_pdf_no_attachment(tmp_path: Path) -> None:
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="commission"),
        GmailMessageSummary(id="m2", thread_id="t2", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.return_value = None  # no attachment for any
    with pytest.raises(SaveCommissionPdfError, match="No PDF attachment"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
        )
```

#### First email has no attachment, second does

```python
def test_save_commission_pdf_skips_non_attachment_emails(
    tmp_path: Path,
) -> None:
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    )
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t1", snippet="commission"),
        GmailMessageSummary(id="m2", thread_id="t2", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.side_effect = [
        None,
        (fixture_pdf.read_bytes(), "Invoice April Commission (EUR)", 1743465600000),
    ]
    report = save_commission_pdf(
        gmail_read_backend=bk,
        commission_query="from:jack commission",
        commission_dir=tmp_path,
    )
    assert report.message_id == "m2"
```

#### Unparseable PDF

```python
def test_save_commission_pdf_unparseable_pdf(tmp_path: Path) -> None:
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.return_value = (
        b"not a pdf at all",
        "Invoice March Commission (EUR)",
        1740787200000,
    )
    with pytest.raises(SaveCommissionPdfError, match="Failed to parse"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
        )
```

#### No month in subject

```python
def test_save_commission_pdf_no_month_in_subject(tmp_path: Path) -> None:
    fixture_pdf = (
        Path(__file__).resolve().parent
        / "fixtures" / "pdf" / "invoice_eur_dot_decimal.pdf"
    )
    bk = MagicMock()
    bk.list_messages.return_value = [
        GmailMessageSummary(id="m1", thread_id="t", snippet="commission"),
    ]
    bk.get_message_pdf_with_metadata.return_value = (
        fixture_pdf.read_bytes(),
        "Commission invoice attached",  # no month name
        1740787200000,
    )
    with pytest.raises(SaveCommissionPdfError, match="Could not find month"):
        save_commission_pdf(
            gmail_read_backend=bk,
            commission_query="from:jack commission",
            commission_dir=tmp_path,
        )
```

### 4d. CLI tests (subcommand)

Follow `TestCliRunMonth` pattern from `tests/test_run_month.py:283-406`, but adapted:
- **No env var guard** — the guard is an interactive `input()` prompt instead.
- Use `@patch("builtins.input")` to simulate user confirmation (or abort).

Tests:

```python
class TestCliSaveCommissionPdf:
    def test_test_run_skips_confirmation(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--test-run goes straight through, no interactive prompt."""
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        with (
            patch("googleads_invoice.cli.GmailApiReadBackend.from_env"),
            patch("googleads_invoice.cli.save_commission_pdf") as mock_save,
        ):
            mock_save.return_value = SaveCommissionReport(
                message_id="m1",
                pdf_path=Path("2026-03 Commission March €1,234.56.pdf"),
                commission_date=date(2026, 3, 1),
                amount_eur=Decimal("1234.56"),
                renamed_filename="2026-03 Commission March €1,234.56.pdf",
            )
            code = main(["save-commission-pdf", "--test-run"])
            assert code == 0
            assert mock_save.call_args.kwargs["test_run"] is True

    @patch("builtins.input", return_value="y")
    def test_confirms_then_saves(
        self,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without --test-run, prompts for confirmation, then saves."""
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        with (
            patch("googleads_invoice.cli.GmailApiReadBackend.from_env"),
            patch("googleads_invoice.cli.save_commission_pdf") as mock_save,
        ):
            mock_save.return_value = SaveCommissionReport(
                message_id="m1",
                pdf_path=Path("2026-04 Commission April €1,234.56.pdf"),
                commission_date=date(2026, 4, 1),
                amount_eur=Decimal("1234.56"),
                renamed_filename="2026-04 Commission April €1,234.56.pdf",
            )
            code = main(["save-commission-pdf"])
            assert code == 0
            assert mock_save.call_args.kwargs["test_run"] is False

    @patch("builtins.input", return_value="n")
    def test_abort_on_no(
        self,
        mock_input: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """User says 'n' → aborts with code 2."""
        from googleads_invoice.cli import main

        monkeypatch.setenv("GOOGLE_OAUTH_TOKEN", "/tmp/dummy.json")
        with patch("googleads_invoice.cli.GmailApiReadBackend.from_env"):
            code = main(["save-commission-pdf"])
            assert code == 2

    def test_errors_when_oauth_missing(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing OAuth token → code 2."""
        from googleads_invoice.cli import main

        monkeypatch.delenv("GOOGLE_OAUTH_TOKEN", raising=False)
        code = main(["save-commission-pdf", "--test-run"])
        assert code == 2
```

### 4e. Integration test marker

No new pytest marker needed. These tests don't need real Gmail — they pass mocked bytes. So they run in CI by default.

---

## 5. Import summary (what goes in each new/modified file)

### `src/googleads_invoice/save_commission_pdf.py` imports:

```python
from __future__ import annotations
import calendar
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from googleads_invoice.addresses import DROPBOX_INVOICE_DIR
from googleads_invoice.commission_pdf import CommissionPdfError, parse_commission_pdf_amount
from googleads_invoice.gmail_api_backend import GmailApiReadBackend
from googleads_invoice.invoice_artifacts import _eur_commission_filename_amount
```

### `src/googleads_invoice/invoice_artifacts.py`

Add public-for-package helper `_eur_commission_filename_amount(amount: Decimal) -> str` (see Step 4 — comma grouping, strip redundant ``.00``, no ``€`` prefix).

### `src/googleads_invoice/gmail_api_backend.py` new imports:

None needed — `base64` and `HttpError` are already imported. New function reuses existing `_urlsafe_b64decode`.

### `src/googleads_invoice/cli.py` new imports:

```python
from googleads_invoice.gmail_api_backend import commission_mail_query_from_env
from googleads_invoice.save_commission_pdf import SaveCommissionPdfError, save_commission_pdf
```

No new `_ENV_*` constants needed — the guard is interactive `input()` confirmation, not an env var.

---

## 6. New file: `src/googleads_invoice/commission_pdf.py`

This module parses Jack's commission PDF for the **EUR total only** (last row of the table, labeled "Total invoice value" or similar). Date is NOT extracted from the PDF — it comes from the email subject + sent date (see Step 3).

### `parse_commission_pdf_amount(source: str | Path | bytes) -> Decimal`

Signature:

```python
def parse_commission_pdf_amount(source: str | Path | bytes) -> Decimal:
```

Implementation:

1. If `source` is a `str` or `Path`, read the file bytes. Otherwise, use the bytes directly.
2. Open with `pypdf.PdfReader(BytesIO(data), strict=False)`.
3. Extract all text from all pages into one string.
4. Find the **last** `€` amount in the text. This is the total. Use the same `_parse_money_token()` from `invoice_pdf.py:116-131` — import and reuse it, don't copy.
   - Search for the last `€` followed by a number: `re.findall(r'€\s*([\d.,]+)', text)` and take `[-1]`.
5. Raise `CommissionPdfError(ValueError)` if no `€` amount is found.

```python
class CommissionPdfError(ValueError):
    """Raised when the commission PDF cannot be parsed for EUR amount."""
```

This is the sole source of EUR parsing for commissions. Do NOT try `parse_invoice_pdf` as a fallback — that function extracts an invoice date which is incorrect for commission PDFs.

---

## 7. What NOT to do

- Do NOT send any email (no SMTP).
- Do NOT modify the source email (don't mark read, don't delete, don't archive).
- Do NOT save the raw attachment directly to the final destination — write to a temp file first for parsing, then move to the target directory (commissions dir or `~/Downloads`).
- Do NOT create a new directory or change `addresses.py:29-31`. Use the existing path as-is.
- Do NOT change the existing `GmailBackend` Protocol in `gmail_facade.py`. The new `get_message_pdf_with_metadata` method goes only on `GmailApiReadBackend`, not on the Protocol.
- Do NOT expose the commissions path as a CLI flag. Production always uses `addresses.py`; the `commission_dir` function parameter exists only for tests.
- Clean up the temp parse file on failure (or any early exit before move) with `unlink(missing_ok=True)`. On success, `shutil.move` in Step 5 removes the source — no separate unlink needed.

---

## 8. Verification after implementation

Run these commands:

```bash
# Type-check (if mypy or similar is configured)
# (no typechecker configured in this project — skip)

# Run all tests
python -m pytest tests/test_save_commission_pdf.py -v

# Run full suite to check no regressions
python -m pytest tests/ -v

# Check the commission PDF parser with the fixture
python -c "
from googleads_invoice.commission_pdf import parse_commission_pdf_amount
from pathlib import Path
a = parse_commission_pdf_amount(Path('tests/fixtures/pdf/invoice_eur_dot_decimal.pdf'))
print(a)
assert str(a) == '1234.56', f'Expected 1234.56, got {a}'
print('OK')
"
```
