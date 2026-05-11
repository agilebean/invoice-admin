"""Gmail → commission PDF (visible under Downloads) → parse amount → derive month from email → move."""

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
from googleads_invoice.gmail_facade import GmailTransportError
from googleads_invoice.invoice_artifacts import _eur_commission_filename_amount


class SaveCommissionPdfError(RuntimeError):
    """A step in save-commission-pdf failed."""

_MONTH_MAP: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_SUBJECT_MONTH_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
    re.IGNORECASE,
)


def _downloads_dir_default() -> Path:
    return Path.home() / "Downloads"


def _month_number_from_subject(subject: str) -> int:
    m = _SUBJECT_MONTH_RE.search(subject)
    if not m:
        raise SaveCommissionPdfError(
            f"Could not find month in email subject: {subject!r}"
        )
    key = m.group(1).lower()
    mo = _MONTH_MAP.get(key)
    if mo is None:
        raise SaveCommissionPdfError(
            f"Could not find month in email subject: {subject!r}"
        )
    return mo


def _year_from_internal_date_ms(internal_date_ms: int) -> int:
    if internal_date_ms and internal_date_ms > 0:
        return datetime.fromtimestamp(
            internal_date_ms / 1000.0, tz=timezone.utc
        ).year
    return date.today().year


def _commission_date_from_email(subject: str, internal_date_ms: int) -> date:
    month = _month_number_from_subject(subject)
    year = _year_from_internal_date_ms(internal_date_ms)
    return date(year, month, 1)


@dataclass(frozen=True)
class SaveCommissionReport:
    """Result of :func:`save_commission_pdf`."""

    message_id: str
    pdf_path: Path
    commission_date: date
    amount_eur: Decimal
    renamed_filename: str
    steps: list[str] = field(default_factory=list)


def save_commission_pdf(
    *,
    gmail_read_backend: GmailApiReadBackend,
    commission_query: str,
    max_scan: int = 10,
    commission_dir: Path | None = None,
    test_run: bool = False,
    downloads_dir: Path | None = None,
) -> SaveCommissionReport:
    """Search Gmail for commission mail, stage PDF under Downloads (visible), parse, save renamed file."""
    _t0 = time.monotonic()
    _last_t = [_t0]
    _STEP = 6

    def _step(n: int, msg: str) -> None:
        now = time.monotonic()
        step_dur = now - _last_t[0]
        total = now - _t0
        _last_t[0] = now
        print(f"  [{n}/{_STEP}] +{step_dur:.1f}s/{total:.1f}s {msg}", flush=True)

    steps: list[str] = []
    staging_root = (
        downloads_dir if downloads_dir is not None else _downloads_dir_default()
    )

    _step(1, "Searching Gmail for commission mail...")
    try:
        rows = gmail_read_backend.list_messages(
            commission_query, max_results=max_scan
        )
    except GmailTransportError as e:
        raise SaveCommissionPdfError(f"Gmail search failed: {e}") from e

    if not rows:
        raise SaveCommissionPdfError(
            f"No commission emails found for query {commission_query!r}"
        )
    steps.append(f"Found {len(rows)} matching message(s)")
    print(f"  Found {len(rows)} match(es) for query.", flush=True)

    _step(2, "Downloading PDF attachment from Gmail...")
    message_id: str | None = None
    pdf_bytes: bytes | None = None
    subject_s: str = ""
    internal_date_ms: int = 0

    for r in rows:
        try:
            got = gmail_read_backend.get_message_pdf_with_metadata(r.id)
        except GmailTransportError as e:
            raise SaveCommissionPdfError(
                f"Failed to download PDF from message {r.id!r}: {e}"
            ) from e
        if got is None:
            continue
        b, subj, idms = got
        message_id = r.id
        pdf_bytes = b
        subject_s = subj
        internal_date_ms = idms
        steps.append(f"Downloaded PDF from message {r.id}")
        break

    if pdf_bytes is None or message_id is None:
        raise SaveCommissionPdfError(
            f"No PDF attachment found in any of the {len(rows)} matching commission emails"
        )

    _step(3, f"Saving attachment to Downloads (visible): {staging_root}...")
    staging_root.mkdir(parents=True, exist_ok=True)
    staging_path = staging_root / f"Commission download {message_id}.pdf"
    staging_path.write_bytes(pdf_bytes)
    steps.append(f"Staged in Downloads folder: {staging_path}")
    print(f"  Download visible at: {staging_path}", flush=True)

    moved = False
    try:
        _step(4, "Parsing EUR amount from PDF...")
        try:
            amount_eur = parse_commission_pdf_amount(staging_path)
        except CommissionPdfError as e:
            raise SaveCommissionPdfError(f"Failed to parse commission PDF: {e}") from e
        steps.append(f"Amount: EUR {amount_eur}")

        _step(5, "Deriving commission month from email subject + sent date...")
        commission_date = _commission_date_from_email(subject_s, internal_date_ms)
        steps.append(
            f"Commission period: {commission_date.isoformat()} (from mail subject + year)"
        )

        _step(6, "Moving renamed file to destination...")
        month_display = calendar.month_name[commission_date.month]
        amount_str = _eur_commission_filename_amount(amount_eur)
        base_name = (
            f"{commission_date.year}-{commission_date.month:02d} "
            f"Commission {month_display} €{amount_str}.pdf"
        )
        steps.append(f"Filename: {base_name}")

        if test_run:
            dest_dir = staging_root
        else:
            dest_dir = commission_dir or Path(DROPBOX_INVOICE_DIR).expanduser()

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / base_name
        if dest.is_file():
            stem = dest.stem
            ext = dest.suffix
            for i in range(1, 100):
                alt = dest_dir / f"{stem} ({i}){ext}"
                if not alt.is_file():
                    dest = alt
                    break

        renamed_filename = dest.name

        shutil.move(str(staging_path), str(dest))
        moved = True
        if not dest.is_file():
            raise SaveCommissionPdfError(
                f"File move failed: {staging_path} -> {dest}"
            )
        steps.append(f"Saved: {dest}")

    finally:
        if not moved and staging_path.is_file():
            staging_path.unlink(missing_ok=True)

    _tot = time.monotonic() - _t0
    print(f"  Done ({_tot:.1f}s total)", flush=True)

    return SaveCommissionReport(
        message_id=message_id,
        pdf_path=dest,
        commission_date=commission_date,
        amount_eur=amount_eur,
        renamed_filename=renamed_filename,
        steps=steps,
    )
