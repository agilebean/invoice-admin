"""Followup engine — monitors tracker state and sends notifications."""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from invoice_admin.core.notify import Notification
from invoice_admin.core.tracker import InvoiceRow, Tracker
from invoice_admin.followup.schedules import FOLLOWUP_RULES, FollowupRule

logger = logging.getLogger(__name__)


def _parse_ts(raw: str) -> datetime:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hours_in_status(row: InvoiceRow) -> float:
    anchor = row.status_updated_at or row.ingested_at
    start = _parse_ts(anchor)
    return (datetime.now(timezone.utc) - start).total_seconds() / 3600.0


def _rule_message(rule: FollowupRule, row: InvoiceRow) -> str:
    hours = int(_hours_in_status(row))
    amount = row.amount if row.amount is not None else 0.0
    vendor = row.vendor or "unknown"
    return rule.message_template.format(
        id=row.id,
        amount=amount,
        vendor=vendor,
        hours=hours,
    )


class FollowupEngine:
    """Checks tracker for overdue items and sends notifications."""

    def __init__(self, tracker: Tracker, notifier: Any, config: Any) -> None:
        self._tracker = tracker
        self._notifier = notifier
        self._config = config
        self._last_digest_day: date | None = None

    def run_once(self) -> list[str]:
        """One pass of followup checks. Returns list of actions taken."""
        actions: list[str] = []
        for rule in FOLLOWUP_RULES:
            for row in self._tracker.list_by_status(rule.status):
                if _hours_in_status(row) <= float(rule.max_age_hours):
                    continue
                if rule.new_status is not None:
                    self._tracker.update_status(row.id, rule.new_status)
                    actions.append(f"transition row={row.id} -> {rule.new_status}")
                body = _rule_message(rule, row)
                title = f"Followup ({rule.status})"
                self._notifier.send(
                    Notification(
                        title=title,
                        body=body,
                        priority=rule.notification_priority,
                        click_url=None,
                    )
                )
                actions.append(f"notify row={row.id} rule={rule.status}>{rule.max_age_hours}h")

        now_local = datetime.now().astimezone()
        today = now_local.date()
        if now_local.hour == 9 and self._last_digest_day != today:
            overdue = self._tracker.list_overdue()
            if overdue:
                lines = [f"{r.id} {r.vendor or '?'} €{r.amount or 0} due={r.due_date} [{r.status}]" for r in overdue]
                digest = "Daily overdue digest:\n" + "\n".join(lines)
                self._notifier.send(
                    Notification(
                        title="Invoice overdue digest",
                        body=digest,
                        priority="default",
                        click_url=None,
                    )
                )
                actions.append(f"digest overdue_count={len(overdue)}")
            self._last_digest_day = today

        return actions

    def run_forever(self, interval_minutes: int = 30) -> None:
        """Loop: run_once() every interval_minutes. Handle KeyboardInterrupt gracefully."""
        try:
            while True:
                self.run_once()
                time.sleep(max(1, interval_minutes) * 60)
        except KeyboardInterrupt:
            logger.info("followup loop stopped (KeyboardInterrupt)")
