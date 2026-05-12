"""Tests for invoice_admin.core.tracker."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_admin.core.errors import IdempotencyViolation, TrackerError
from invoice_admin.core.tracker import Tracker


def test_tracker_insert_get_update(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        rid = t.insert("file", "hash-1", invoice_type="sepa_transfer", status="received")
        row = t.get(rid)
        assert row is not None
        assert row.source_ref == "hash-1"
        assert row.invoice_type == "sepa_transfer"
        assert row.status_updated_at is not None
        first_ts = row.status_updated_at
        t.update_status(rid, "prepared", pdf_path="/tmp/x.pdf")
        row2 = t.get(rid)
        assert row2 is not None
        assert row2.status == "prepared"
        assert row2.pdf_path == "/tmp/x.pdf"
        assert row2.status_updated_at is not None
        assert row2.status_updated_at != first_ts


def test_tracker_list_filtered(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        t.insert("file", "a", invoice_type="foyer_claim", status="received")
        t.insert("file", "b", invoice_type="sepa_transfer", status="received")
        t.insert("file", "c", invoice_type="foyer_claim", status="failed")
        rows = t.list_rows(invoice_type="foyer_claim", status=None)
        assert {r.source_ref for r in rows} == {"a", "c"}
        rows2 = t.list_rows(invoice_type=None, status="received")
        assert {r.source_ref for r in rows2} == {"a", "b"}
        rows3 = t.list_rows(invoice_type="foyer_claim", status="failed")
        assert [r.source_ref for r in rows3] == ["c"]


def test_tracker_idempotency_violation(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        t.insert("email", "<id@host>")
        with pytest.raises(IdempotencyViolation):
            t.insert("email", "<id@host>")


def test_tracker_exists(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        assert t.exists("nope") is False
        t.insert("file", "abc")
        assert t.exists("abc") is True


def test_tracker_list_by_status_and_type(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        a = t.insert("file", "a1", invoice_type="sepa_transfer", status="received")
        b = t.insert("file", "b1", invoice_type="sepa_transfer", status="failed")
        rows = t.list_by_status("received")
        assert [r.id for r in rows] == [a]
        rows2 = t.list_by_type("sepa_transfer", status="failed")
        assert [r.id for r in rows2] == [b]


def test_tracker_list_overdue(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        t.insert("file", "r1", due_date="2000-01-01", status="received")
        t.insert("file", "r2", due_date="2000-01-01", status="paid")
        overdue = t.list_overdue()
        assert len(overdue) == 1
        assert overdue[0].source_ref == "r1"


def test_tracker_update_unknown_column(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        rid = t.insert("file", "x")
        with pytest.raises(TrackerError):
            t.update_status(rid, "received", not_a_column=1)


def test_tracker_error_blob_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    blob = json.dumps({"type": "ExtractionError", "message": "bad", "traceback": "tb"})
    with Tracker(db) as t:
        rid = t.insert("file", "e1")
        t.update_status(rid, "failed", error=blob)
        row = t.get(rid)
        assert row is not None
        assert json.loads(row.error or "{}")["type"] == "ExtractionError"
