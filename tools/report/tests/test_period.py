from datetime import date, datetime, timezone

import pytest

from phare_report.period import last_complete_week, parse, parse_ts


def test_iso_week():
    p = parse("2026-W40")
    assert (p.kind, p.start.date(), p.end.date()) == ("weekly", date(2026, 9, 28), date(2026, 10, 5))
    assert len(list(p.days())) == 7


def test_iso_week_crossing_year():
    p = parse("2026-W01")
    assert p.start.date() == date(2025, 12, 29)


@pytest.mark.parametrize("name,start,end", [
    ("2026-09", date(2026, 9, 1), date(2026, 10, 1)),
    ("2026-12", date(2026, 12, 1), date(2027, 1, 1)),
    ("2026-Q3", date(2026, 7, 1), date(2026, 10, 1)),
    ("2026-Q4", date(2026, 10, 1), date(2027, 1, 1)),
    ("2026", date(2026, 1, 1), date(2027, 1, 1)),
])
def test_coarse_periods(name, start, end):
    p = parse(name)
    assert (p.start.date(), p.end.date()) == (start, end)


def test_bad_name():
    with pytest.raises(ValueError):
        parse("2026-W4")


def test_half_open():
    p = parse("2026-W40")
    assert p.contains(p.start) and not p.contains(p.end) and not p.contains(None)


def test_last_complete_week():
    monday_morning = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)
    assert last_complete_week(monday_morning).name == "2026-W40"
    sunday = datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc)
    assert last_complete_week(sunday).name == "2026-W40"


def test_parse_ts_both_formats():
    assert parse_ts("2026-10-05T09:03:46Z") == datetime(2026, 10, 5, 9, 3, 46, tzinfo=timezone.utc)
    assert parse_ts("20261005T112407+0200") == datetime(2026, 10, 5, 9, 24, 7, tzinfo=timezone.utc)
