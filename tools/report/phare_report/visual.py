"""Chart data for the report pages: positions in percent, classes, tooltips. Pure.

Templates draw these as HTML/CSS (text stays readable at any width); only
sparklines are SVG.
"""

import math
from collections import Counter

from . import svg
from .analyze import AREA_ORDER

AREA_CLASS = {a: f"c{i + 1}" for i, a in enumerate(AREA_ORDER[:-1])} | {"other": "c-other"}

KPI_METRICS = [("commits", "Commits on master"), ("prs_merged", "PRs merged"),
               ("issues_opened", "Issues opened"), ("issues_closed", "Issues closed"),
               ("reviews", "Reviews"), ("ci_builds", "CI builds")]

AGE_MAX_H = 24 * 1000          # 1000 days
AGE_TICKS = [(1, "1 h"), (24, "1 d"), (24 * 7, "1 wk"), (24 * 30, "1 mo"), (24 * 365, "1 yr")]
SIZE_MAX = 100_000
SIZE_TICKS = [(10, "10"), (100, "100"), (1000, "1k"), (10_000, "10k")]


def _pct(t, p):
    span = (p["end"] - p["start"]).total_seconds()
    return round(100 * (t - p["start"]).total_seconds() / span, 2)


def _log_pct(v, vmax, vmin=1):
    if v is None or v <= vmin:
        return 0.0
    return round(100 * min(1.0, math.log10(v / vmin) / math.log10(vmax / vmin)), 2)


# --- headline ---------------------------------------------------------------

def kpis(history):
    """history: headline dicts, oldest first, the current week last."""
    cur, prev = history[-1], (history[-2] if len(history) > 1 else None)
    out = []
    for key, title in KPI_METRICS:
        values = [h[key] for h in history[-13:]]
        delta = None if prev is None else cur[key] - prev[key]
        out.append({"key": key, "title": title, "value": cur[key], "delta": delta,
                    "spark": svg.sparkline(values) if len(values) > 1 else ""})
    return out


# --- week at a glance -------------------------------------------------------

def timeline(view, period):
    p = {"start": period.start, "end": period.end}
    gh = "https://github.com/PHAREHUB/PHARE"

    def lane(name, cls, events):
        return {"name": name, "cls": cls, "count": len(events),
                "events": sorted(events, key=lambda e: e["left"])}

    commits = [{"left": _pct(c["t"], p), "r": 4 + min(4, math.log10(c["additions"] + c["deletions"] + 1)),
                "href": f"{gh}/commit/{c['sha']}",
                "tip": f"{c['sha'][:7]} {c['headline']} — @{c['author']} (+{c['additions']} −{c['deletions']})"}
               for c in view["commits"]]
    merged = [{"left": _pct(x["merged_at"], p), "r": 5, "href": x["url"],
               "tip": f"#{x['number']} merged: {x['title']} — @{x['author']}"} for x in view["prs_merged"]]
    opened = [{"left": _pct(x["created_at"], p), "r": 5, "href": x["url"],
               "tip": f"#{x['number']} opened: {x['title']} — @{x['author']}"} for x in view["prs_opened"]]
    iopened = [{"left": _pct(i["created_at"], p), "r": 5, "href": i["url"],
                "tip": f"#{i['number']} {i['title']} — @{i['author']}"} for i in view["issues_opened"]]
    iclosed = [{"left": _pct(i["closed_at"], p), "r": 5, "href": i["url"],
                "tip": f"#{i['number']} closed ({i['outcome']}): {i['title']}"} for i in view["issues_closed"]]
    reviews = [{"left": _pct(e["t"], p), "r": 4, "href": f"{gh}/pull/{e['number']}",
                "tip": f"@{e['reviewer']} reviewed #{e['number']} by @{e['author']} ({e['state'].lower()})"}
               for e in view["review_events"]]
    failures = [{"left": _pct(e["t"], p), "r": 4, "href": None,
                 "tip": f"{e['source']} · {e['lane']} failed on {e['branch'] or 'unknown branch'}"}
                for e in view["ci_events"] if e["status"] == "bad"]

    days = list(period.days())
    return {
        "days": [{"label": d.strftime("%a %-d"), "short": d.strftime("%a")[0], "left": round(100 * (i + .5) / len(days), 2),
                  "grid": round(100 * i / len(days), 2)} for i, d in enumerate(days)],
        "lanes": [lane("Commits on master", "c1", commits), lane("PRs merged", "c7", merged),
                  lane("PRs opened", "c3", opened), lane("Issues opened", "c2", iopened),
                  lane("Issues closed", "c6", iclosed), lane("Reviews", "c5", reviews),
                  lane("CI failures", "bad", failures)],
    }


# --- issues -----------------------------------------------------------------

def waterfall(start, steps, end):
    """Columns: start total, signed steps, end total. steps = [(label, signed value, css class), ...]."""
    level, bars = start, [{"label": "open at start", "value": start, "lo": 0, "hi": start, "cls": "total", "dir": "up"}]
    for label, v, cls in steps:
        lo, hi = sorted((level, level + v))
        bars.append({"label": label, "value": v, "lo": lo, "hi": hi, "cls": cls, "dir": "up" if v >= 0 else "down"})
        level += v
    if level != end:
        lo, hi = sorted((level, end))
        bars.append({"label": "reopened or other", "value": end - level, "lo": lo, "hi": hi, "cls": "c-other",
                     "dir": "up" if end >= level else "down"})
    bars.append({"label": "open at end", "value": end, "lo": 0, "hi": end, "cls": "total", "dir": "up"})
    top = max(b["hi"] for b in bars) or 1
    # zoom the axis so steps stay visible next to large totals; the template labels where it starts
    low = min([start, end] + [b["lo"] for b in bars[1:-1]])
    floor = int(max(0, low - 1.5 * max(top - low, 1)) // 10 * 10)
    for b in bars:
        b["bottom"] = round(100 * (max(b["lo"], floor) - floor) / (top - floor), 2)
        b["height"] = max(round(100 * (b["hi"] - max(b["lo"], floor)) / (top - floor), 2), .8)
    return {"bars": bars, "floor": floor, "top": top}


def label_bars(issues, top=8):
    counts = Counter(l for i in issues for l in i["labels"])
    unlabeled = sum(1 for i in issues if not i["labels"])
    rows = counts.most_common(top) + ([("no label", unlabeled)] if unlabeled else [])
    vmax = max((n for _, n in rows), default=1)
    return [{"label": l, "n": n, "pct": round(100 * n / vmax, 2)} for l, n in rows]


OUTCOMES = [("pr", "fixed by a PR", "c1"), ("commit", "fixed by a commit", "c3"),
            ("manual", "closed without a link", "c-other"), ("not_planned", "not planned or duplicate", "c4")]


def outcome_split(closed):
    def kind(i):
        if i["outcome"] in ("not planned", "duplicate"):
            return "not_planned"
        return i["how"]["kind"]
    counts = Counter(kind(i) for i in closed)
    total = sum(counts.values()) or 1
    return [{"key": k, "label": lab, "cls": cls, "n": counts[k], "pct": round(100 * counts[k] / total, 2)}
            for k, lab, cls in OUTCOMES if counts[k]]


# --- pull requests ----------------------------------------------------------

def pr_chart(view):
    seen, rows = set(), []
    for bucket in ("prs_merged", "prs_opened", "prs_closed"):
        for x in view[bucket]:
            if x["number"] in seen:
                continue
            seen.add(x["number"])
            total = sum(x["lines_by_area"].values()) or (x["additions"] + x["deletions"])
            width = _log_pct(total + 1, SIZE_MAX)
            segs = [{"area": a, "cls": AREA_CLASS[a], "lines": n, "pct": round(width * n / total, 2)}
                    for a, n in x["lines_by_area"].items()] if total else []
            rows.append({**x, "age_pct": _log_pct(x["open_days"] * 24, AGE_MAX_H),
                         "review_pct": _log_pct(x["first_review_h"], AGE_MAX_H) if x["first_review_h"] else None,
                         "size_pct": width, "segments": segs, "lines": total})
    return {"rows": rows,
            "age_ticks": [{"label": l, "left": _log_pct(h, AGE_MAX_H)} for h, l in AGE_TICKS],
            "size_ticks": [{"label": l, "left": _log_pct(n + 1, SIZE_MAX)} for n, l in SIZE_TICKS],
            "areas": [{"area": a, "cls": AREA_CLASS[a]} for a in AREA_ORDER
                      if any(a in r["lines_by_area"] for r in rows)]}


# --- people -----------------------------------------------------------------

PEOPLE_COLUMNS = [("commits", "Commits"), ("prs_opened", "PRs opened"), ("prs_merged", "PRs merged"),
                  ("reviews", "Reviews given"), ("issues_opened", "Issues opened"),
                  ("issues_closed", "Issues closed"), ("comments", "Comments")]


def heat_table(authors):
    humans = [a for a in authors if not a["bot"]]
    maxes = {k: max((a.get(k, 0) for a in humans), default=0) for k, _ in PEOPLE_COLUMNS}
    rows = [{"login": a["login"], "first_time": a["first_time"],
             "lines_added": a.get("lines_added", 0), "lines_removed": a.get("lines_removed", 0),
             "cells": [{"v": a.get(k, 0), "shade": round(70 * a.get(k, 0) / maxes[k]) if maxes[k] else 0}
                       for k, _ in PEOPLE_COLUMNS]} for a in humans]
    return {"columns": [t for _, t in PEOPLE_COLUMNS], "rows": rows,
            "bots": [a for a in authors if a["bot"]]}


def review_matrix(events):
    pairs = Counter((e["reviewer"], e["author"]) for e in events)
    # ties broken by name: set order is not stable across runs
    reviewers = sorted({r for r, _ in pairs}, key=lambda r: (-sum(n for (rr, _), n in pairs.items() if rr == r), r))
    authors = sorted({a for _, a in pairs}, key=lambda a: (-sum(n for (_, aa), n in pairs.items() if aa == a), a))
    vmax = max(pairs.values(), default=1)
    return {"authors": authors,
            "rows": [{"reviewer": r, "cells": [{"author": a, "v": pairs[(r, a)],
                                                "shade": round(75 * pairs[(r, a)] / vmax)} for a in authors]}
                     for r in reviewers]}


# --- CI ---------------------------------------------------------------------

CI_GROUPS = [("actions", "GitHub Actions"), ("main", "TeamCity"), ("shadow (next CI)", "TeamCity, next CI (shadow)"),
             ("personal", "TeamCity, personal builds")]


def ci_strips(events, period):
    p = {"start": period.start, "end": period.end}
    lanes = {}
    for e in events:
        ln = lanes.setdefault((e["group"], e["lane"]), {"name": e["lane"], "ticks": [], "ok": 0, "bad": 0, "skip": 0,
                                                       "tests": 0, "failed_tests": 0})
        ln[e["status"]] += 1
        if t := e["tests"]:
            ln["tests"] += t.get("count", 0)
            ln["failed_tests"] += t.get("failed", 0)
        word = {"ok": "passed", "bad": "failed", "skip": "canceled"}[e["status"]]
        ln["ticks"].append({"left": _pct(e["t"], p), "cls": e["status"],
                            "tip": f"{e['lane']} {word} · {e['branch'] or ''} · {e['t']:%a %H:%M} UTC"})
    groups = []
    for key, title in CI_GROUPS:
        ls = sorted((v for (g, _), v in lanes.items() if g == key), key=lambda v: -(v["ok"] + v["bad"] + v["skip"]))
        if ls:
            groups.append({"title": title, "lanes": ls})
    tmax = max((v["tests"] for v in lanes.values()), default=0)
    for v in lanes.values():
        v["tests_pct"] = round(100 * v["tests"] / tmax, 2) if tmax else 0
    return groups


# --- code -------------------------------------------------------------------

def churn_bars(churn):
    vmax = max([c["additions"] for c in churn] + [c["deletions"] for c in churn] + [1])
    return [{**c, "cls": AREA_CLASS[c["area"]], "add_pct": round(100 * c["additions"] / vmax, 2),
             "del_pct": round(100 * c["deletions"] / vmax, 2)} for c in churn]
