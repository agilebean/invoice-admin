"""Tests for followup schedule rules."""
from __future__ import annotations

from invoice_admin.followup.schedules import FOLLOWUP_RULES, FollowupRule


def test_followup_rules_are_frozen_data() -> None:
    assert len(FOLLOWUP_RULES) == 4
    assert all(isinstance(r, FollowupRule) for r in FOLLOWUP_RULES)
    assert FOLLOWUP_RULES[0].status == "awaiting_tan"
    assert FOLLOWUP_RULES[0].new_status is None
