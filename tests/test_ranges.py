from datetime import UTC, date, datetime

import pytest

from costpulse.ranges import USAGE, UsageError, parse_range

NOW = datetime(2026, 10, 18, 15, 30, tzinfo=UTC)


def test_no_argument_resolves_to_month():
    assert parse_range("", NOW) == parse_range("month", NOW)


def test_today_is_today_to_tomorrow_exclusive():
    r = parse_range("today", NOW)
    assert (r.start, r.end) == (date(2026, 10, 18), date(2026, 10, 19))
    assert r.label == "today (Oct 18)"


def test_week_covers_last_7_days_including_today():
    r = parse_range("week", NOW)
    assert (r.start, r.end) == (date(2026, 10, 12), date(2026, 10, 19))
    assert (r.end - r.start).days == 7
    assert r.label == "last 7 days (Oct 12–18)"


def test_week_across_month_boundary_labels_both_months():
    r = parse_range("week", datetime(2026, 10, 3, tzinfo=UTC))
    assert r.start == date(2026, 9, 27)
    assert r.label == "last 7 days (Sep 27–Oct 3)"


def test_month_starts_on_first_of_current_month():
    r = parse_range("month", NOW)
    assert (r.start, r.end) == (date(2026, 10, 1), date(2026, 10, 19))
    assert r.label == "month to date (Oct 1–18)"


def test_month_on_the_first_resolves_to_full_previous_month():
    r = parse_range("month", datetime(2026, 10, 1, 9, 0, tzinfo=UTC))
    assert (r.start, r.end) == (date(2026, 9, 1), date(2026, 10, 1))
    assert r.label == "last month (Sep 1–30)"


def test_month_on_january_first_rolls_back_a_year():
    r = parse_range("month", datetime(2027, 1, 1, tzinfo=UTC))
    assert (r.start, r.end) == (date(2026, 12, 1), date(2027, 1, 1))
    assert r.label == "last month (Dec 1–31)"


@pytest.mark.parametrize("text", ["  TODAY ", "Today", "\tweek\n", "MONTH"])
def test_arguments_are_trimmed_and_case_insensitive(text):
    parse_range(text, NOW)


@pytest.mark.parametrize("text", ["banana", "yesterday", "month please", "7d"])
def test_unknown_argument_raises_usage_error(text):
    with pytest.raises(UsageError, match=r"\[today\|week\|month\]"):
        parse_range(text, NOW)
    assert USAGE == "Usage: /cost [today|week|month]"
