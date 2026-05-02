"""Calendar month helpers for which period Google is billing (typically prior month)."""

from __future__ import annotations

from calendar import month_name
from datetime import date, timedelta


def billing_month_label_for_previous_calendar_month(*, ref: date | None = None) -> str:
    """Human label for the billing month: the full calendar month *before* ``ref``.

    Example: if ``ref`` is 2 May 2026, returns ``\"April 2026\"`` (the invoice email month
    Jack cares about when you run the job in early May).
    """
    ref = date.today() if ref is None else ref
    first_this = ref.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return f"{month_name[last_prev.month]} {last_prev.year}"
