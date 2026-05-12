"""SQLite invoice tracker."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from invoice_admin.core.errors import IdempotencyViolation, TrackerError

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingested_at     TEXT NOT NULL,
    status_updated_at TEXT NOT NULL,
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

_INSERTABLE = frozenset({
    "invoice_type",
    "classifier_conf",
    "vendor",
    "invoice_date",
    "due_date",
    "amount",
    "currency",
    "iban",
    "bic",
    "verwendungszweck",
    "pdf_path",
    "status",
    "submitted_at",
    "approved_at",
    "paid_at",
    "reimbursed_at",
    "error",
    "notes",
})

_TERMINAL_OVERDUE = frozenset({"paid", "reimbursed", "failed"})


@dataclass(frozen=True)
class InvoiceRow:
    """A row from the tracker. All fields optional except id and status."""

    id: int
    status: str
    ingested_at: str
    status_updated_at: str
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


def _row_from_sqlite(row: sqlite3.Row) -> InvoiceRow:
    keys = row.keys()
    status_updated = str(row["status_updated_at"]) if "status_updated_at" in keys else str(row["ingested_at"])
    return InvoiceRow(
        id=int(row["id"]),
        status=str(row["status"]),
        ingested_at=str(row["ingested_at"]),
        status_updated_at=status_updated,
        source_type=str(row["source_type"]),
        source_ref=str(row["source_ref"]),
        invoice_type=row["invoice_type"],
        classifier_conf=row["classifier_conf"],
        vendor=row["vendor"],
        invoice_date=row["invoice_date"],
        due_date=row["due_date"],
        amount=row["amount"],
        currency=row["currency"],
        iban=row["iban"],
        bic=row["bic"],
        verwendungszweck=row["verwendungszweck"],
        pdf_path=row["pdf_path"],
        submitted_at=row["submitted_at"],
        approved_at=row["approved_at"],
        paid_at=row["paid_at"],
        reimbursed_at=row["reimbursed_at"],
        error=row["error"],
        notes=row["notes"],
    )


class Tracker:
    """Thread-safe tracker. One instance per process. Context manager for connection lifecycle."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> Tracker:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._ensure_status_updated_at_column()
        self._conn.commit()
        return self

    def _ensure_status_updated_at_column(self) -> None:
        conn = self._require_conn()
        cur = conn.execute("PRAGMA table_info(invoices)")
        names = {str(r[1]) for r in cur.fetchall()}
        if "status_updated_at" not in names:
            conn.execute("ALTER TABLE invoices ADD COLUMN status_updated_at TEXT")
            conn.execute(
                "UPDATE invoices SET status_updated_at = ingested_at "
                "WHERE status_updated_at IS NULL"
            )

    def __exit__(self, *args: Any) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise TrackerError("Tracker is not active; use 'with Tracker(path):'")
        return self._conn

    def exists(self, source_ref: str) -> bool:
        """Check idempotency: has this source_ref been ingested?"""
        cur = self._require_conn().execute(
            "SELECT 1 FROM invoices WHERE source_ref = ? LIMIT 1",
            (source_ref,),
        )
        return cur.fetchone() is not None

    def insert(self, source_type: str, source_ref: str, **kwargs: Any) -> int:
        """Insert a new row. Raises IdempotencyViolation if source_ref exists. Returns row id."""
        now = datetime.now(timezone.utc).isoformat()
        bad = set(kwargs) - _INSERTABLE
        if bad:
            raise TrackerError(f"Unknown columns for insert: {sorted(bad)}")
        cols = ["ingested_at", "status_updated_at", "source_type", "source_ref", *kwargs]
        vals: list[Any] = [now, now, source_type, source_ref]
        for k in kwargs:
            vals.append(kwargs[k])
        placeholders = ", ".join("?" * len(cols))
        sql = f"INSERT INTO invoices ({', '.join(cols)}) VALUES ({placeholders})"
        try:
            cur = self._require_conn().execute(sql, vals)
            self._require_conn().commit()
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e) and "source_ref" in str(e):
                raise IdempotencyViolation(source_ref) from e
            raise TrackerError(str(e)) from e
        return int(cur.lastrowid)

    def get(self, row_id: int) -> InvoiceRow | None:
        """Fetch one row by id."""
        cur = self._require_conn().execute("SELECT * FROM invoices WHERE id = ?", (row_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return _row_from_sqlite(row)

    def update_status(self, row_id: int, status: str, **extra: Any) -> None:
        """Atomically update status and optional extra fields."""
        bad = set(extra) - _INSERTABLE
        if bad:
            raise TrackerError(f"Unknown columns for update_status: {sorted(bad)}")
        now = datetime.now(timezone.utc).isoformat()
        sets = ["status = ?", "status_updated_at = ?"] + [f"{k} = ?" for k in extra]
        vals: list[Any] = [status, now, *extra.values(), row_id]
        sql = f"UPDATE invoices SET {', '.join(sets)} WHERE id = ?"
        cur = self._require_conn().execute(sql, vals)
        if cur.rowcount != 1:
            raise TrackerError(f"No row updated for id={row_id}")
        self._require_conn().commit()

    def list_by_status(self, status: str) -> list[InvoiceRow]:
        """List all rows with given status."""
        cur = self._require_conn().execute(
            "SELECT * FROM invoices WHERE status = ? ORDER BY id",
            (status,),
        )
        return [_row_from_sqlite(r) for r in cur.fetchall()]

    def list_overdue(self) -> list[InvoiceRow]:
        """Rows where due_date < today AND status NOT IN terminal states."""
        placeholders = ", ".join("?" * len(_TERMINAL_OVERDUE))
        today = datetime.now(timezone.utc).date().isoformat()
        sql = f"""
            SELECT * FROM invoices
            WHERE due_date IS NOT NULL
              AND date(due_date) < date(?)
              AND status NOT IN ({placeholders})
            ORDER BY due_date, id
        """
        cur = self._require_conn().execute(sql, (today, *_TERMINAL_OVERDUE))
        return [_row_from_sqlite(r) for r in cur.fetchall()]

    def list_by_type(self, invoice_type: str, status: str | None = None) -> list[InvoiceRow]:
        """List rows by type, optionally filtered by status."""
        if status is None:
            cur = self._require_conn().execute(
                "SELECT * FROM invoices WHERE invoice_type = ? ORDER BY id",
                (invoice_type,),
            )
        else:
            cur = self._require_conn().execute(
                "SELECT * FROM invoices WHERE invoice_type = ? AND status = ? ORDER BY id",
                (invoice_type, status),
            )
        return [_row_from_sqlite(r) for r in cur.fetchall()]

    def list_rows(
        self,
        *,
        invoice_type: str | None = None,
        status: str | None = None,
    ) -> list[InvoiceRow]:
        """List rows with optional filters (AND)."""
        clauses: list[str] = []
        params: list[Any] = []
        if invoice_type is not None:
            clauses.append("invoice_type = ?")
            params.append(invoice_type)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM invoices {where} ORDER BY id"
        cur = self._require_conn().execute(sql, params)
        return [_row_from_sqlite(r) for r in cur.fetchall()]
