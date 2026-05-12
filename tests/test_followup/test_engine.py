"""Tests for FollowupEngine."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from invoice_admin.core.notify import Notification
from invoice_admin.followup.engine import FollowupEngine
from invoice_admin.followup.schedules import FOLLOWUP_RULES
from invoice_admin.core.tracker import Tracker


class _CaptureNotifier:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return True


def test_followup_engine_tan_escalation(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    with Tracker(db) as t:
        rid = t.insert("file", "tan-1", status="awaiting_tan", vendor="VR", amount=42.0)

    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE invoices SET status_updated_at = ? WHERE id = ?", (old, rid))
    conn.commit()
    conn.close()

    cap = _CaptureNotifier()
    with Tracker(db) as t:
        eng = FollowupEngine(t, cap, None)
        actions = eng.run_once()

    assert any("transition" in a and "needs_review" in a for a in actions)
    with Tracker(db) as t:
        row = t.get(rid)
    assert row is not None
    assert row.status == "needs_review"
    assert len(cap.sent) >= 2


def test_followup_rules_cover_distinct_statuses() -> None:
    statuses = {r.status for r in FOLLOWUP_RULES}
    assert "awaiting_tan" in statuses
    assert "needs_review" in statuses
    assert "submitting" in statuses
