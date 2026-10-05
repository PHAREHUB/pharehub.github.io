"""Report periods: half-open UTC intervals [start, end) with a stable name.

Names: "2026-W40" (ISO week), "2026-09" (month), "2026-Q3" (quarter), "2026" (year).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True)
class Period:
    name: str
    kind: str  # "weekly" | "monthly" | "quarterly" | "yearly"
    start: datetime
    end: datetime

    def days(self):
        d = self.start.date()
        while d < self.end.date():
            yield d
            d += timedelta(days=1)

    def contains(self, ts):
        return ts is not None and self.start <= ts < self.end


def _utc(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def parse(name):
    if m := re.fullmatch(r"(\d{4})-W(\d{2})", name):
        start = date.fromisocalendar(int(m[1]), int(m[2]), 1)
        return Period(name, "weekly", _utc(start), _utc(start + timedelta(days=7)))
    if m := re.fullmatch(r"(\d{4})-(\d{2})", name):
        y, mo = int(m[1]), int(m[2])
        nxt = date(y + mo // 12, mo % 12 + 1, 1)
        return Period(name, "monthly", _utc(date(y, mo, 1)), _utc(nxt))
    if m := re.fullmatch(r"(\d{4})-Q([1-4])", name):
        y, q = int(m[1]), int(m[2])
        start = date(y, 3 * q - 2, 1)
        nxt = date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
        return Period(name, "quarterly", _utc(start), _utc(nxt))
    if m := re.fullmatch(r"(\d{4})", name):
        y = int(m[1])
        return Period(name, "yearly", _utc(date(y, 1, 1)), _utc(date(y + 1, 1, 1)))
    raise ValueError(f"unknown period name: {name!r}")


def last_complete_week(now):
    """The ISO week that ended most recently before `now`."""
    y, w, _ = (now.date() - timedelta(days=7)).isocalendar()
    return parse(f"{y}-W{w:02d}")


def parse_ts(s):
    """Parse GitHub ISO-8601 ("2026-10-05T09:03:46Z") or TeamCity ("20261005T092407+0000")."""
    if s is None:
        return None
    if re.fullmatch(r"\d{8}T\d{6}[+-]\d{4}", s):
        return datetime.strptime(s, "%Y%m%dT%H%M%S%z").astimezone(timezone.utc)
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
