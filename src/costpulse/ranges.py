"""Turn the /cost argument into a UTC Cost Explorer date range."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

USAGE = "Usage: /cost [today|week|month]"


class UsageError(ValueError):
    """The /cost argument is not one of today, week or month."""


@dataclass(frozen=True)
class DateRange:
    start: date
    # Exclusive, matching Cost Explorer's TimePeriod.End.
    end: date
    label: str


def parse_range(text: str, now: datetime) -> DateRange:
    """Resolve a /cost argument against `now`, which must be timezone-aware UTC."""
    arg = text.strip().lower() or "month"
    today = now.date()
    tomorrow = today + timedelta(days=1)

    if arg == "today":
        return DateRange(today, tomorrow, f"today ({_day(today)})")
    if arg == "week":
        start = today - timedelta(days=6)
        return DateRange(start, tomorrow, f"last 7 days ({_span(start, today)})")
    if arg == "month":
        if today.day == 1:
            # Month to date would be a few hours of partial data; show the full previous month.
            last_month_end = today - timedelta(days=1)
            start = last_month_end.replace(day=1)
            return DateRange(start, today, f"last month ({_span(start, last_month_end)})")
        start = today.replace(day=1)
        return DateRange(start, tomorrow, f"month to date ({_span(start, today)})")
    raise UsageError(USAGE)


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def _span(first: date, last: date) -> str:
    if first.month == last.month:
        return f"{_day(first)}–{last.day}"
    return f"{_day(first)}–{_day(last)}"
