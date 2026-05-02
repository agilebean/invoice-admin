from datetime import date

from googleads_invoice.billing_period import (
    billing_month_label_for_previous_calendar_month,
)


def test_previous_month_mid_year() -> None:
    assert (
        billing_month_label_for_previous_calendar_month(ref=date(2026, 5, 2))
        == "April 2026"
    )


def test_previous_month_january_rolls_year() -> None:
    assert (
        billing_month_label_for_previous_calendar_month(ref=date(2026, 1, 15))
        == "December 2025"
    )


def test_previous_month_first_day_of_month() -> None:
    assert (
        billing_month_label_for_previous_calendar_month(ref=date(2026, 3, 1))
        == "February 2026"
    )
