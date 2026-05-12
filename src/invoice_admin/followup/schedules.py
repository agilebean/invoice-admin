"""Cron schedule definitions for followup checks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FollowupRule:
    """A rule that triggers when a row has been in a status for too long."""

    status: str
    max_age_hours: int
    new_status: str | None  # Transition target, or None to only notify
    notification_priority: str  # 'default', 'high', 'urgent'
    message_template: str


FOLLOWUP_RULES: list[FollowupRule] = [
    FollowupRule(
        status="awaiting_tan",
        max_age_hours=4,
        new_status=None,
        notification_priority="high",
        message_template="⏰ Reminder: Approve €{amount} to {vendor} in SecureGo+ (waiting {hours}h)",
    ),
    FollowupRule(
        status="awaiting_tan",
        max_age_hours=24,
        new_status="needs_review",
        notification_priority="urgent",
        message_template=(
            "⚠️ Overdue TAN: €{amount} to {vendor} has been waiting 24h. Transferred to needs_review."
        ),
    ),
    FollowupRule(
        status="needs_review",
        max_age_hours=72,
        new_status=None,
        notification_priority="high",
        message_template="📋 Still needs review: {vendor} invoice for €{amount} (row {id})",
    ),
    FollowupRule(
        status="submitting",
        max_age_hours=2,
        new_status="failed",
        notification_priority="urgent",
        message_template="❌ Foyer submission stuck: {vendor} for €{amount} (row {id})",
    ),
]
