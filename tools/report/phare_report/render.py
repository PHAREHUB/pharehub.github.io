"""Render every archived snapshot to HTML, plus the dashboard.

    python -m phare_report.render --data ../../data --out ../../reports

Pages are always regenerated from data/, so a template change reaches every report.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from . import svg, visual
from .analyze import analyze, period_of


def _num(v):
    return "–" if v is None else f"{v:,}"


def _duration_h(h):
    if h is None:
        return "–"
    if h < 48:
        return f"{h:.0f} h"
    return f"{h / 24:.1f} d"


def _days(d):
    return "–" if d is None else (f"{d * 24:.0f} h" if d < 2 else f"{d:.1f} d")


def environment():
    env = Environment(loader=PackageLoader("phare_report", "templates"),
                      autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.filters.update(num=_num, hours=_duration_h, days=_days)
    env.globals.update(svg=svg, max=max, sum=sum)
    return env


def render_weekly(env, view, period, history, prev_name, next_name, standalone=True):
    """history: headline dicts of the archived weeks up to and including this one."""
    b, h = view["backlog"], view["headline"]
    return env.get_template("weekly.html").render(
        v=view, kpis=visual.kpis(history), timeline=visual.timeline(view, period),
        issue_wf=visual.waterfall(b["issue"]["start"], [("opened", h["issues_opened"], "c2"),
                                                       ("closed", -h["issues_closed"], "c6")], b["issue"]["end"]),
        pr_wf=visual.waterfall(b["pr"]["start"], [("opened", h["prs_opened"], "c3"),
                                                 ("merged", -h["prs_merged"], "c7"),
                                                 ("closed", -h["prs_closed"], "c-other")], b["pr"]["end"]),
        issue_labels=visual.label_bars(view["issues_opened"]), outcomes=visual.outcome_split(view["issues_closed"]),
        prs=visual.pr_chart(view), people=visual.heat_table(view["authors"]),
        matrix=visual.review_matrix(view["review_events"]), ci=visual.ci_strips(view["ci_events"], period),
        churn=visual.churn_bars(view["churn"]),
        prev_name=prev_name, next_name=next_name, standalone=standalone, root="../",
        generated_at_text=f"{view['generated_at']:%-d %b %Y, %H:%M} UTC")


TREND_METRICS = [("commits", "Commits on master"), ("prs_merged", "PRs merged"),
                 ("issues_opened", "Issues opened"), ("issues_closed", "Issues closed"),
                 ("reviews", "Reviews"), ("ci_builds", "CI builds")]


def trend_charts(rows):
    """One small column chart per metric, one column per week (last 26 weeks)."""
    chrono = list(reversed(rows))[-26:]
    labels = [r["name"][-3:] for r in chrono]
    charts = []
    for key, title in TREND_METRICS:
        values = [r[key] for r in chrono]
        tips = [f"{r['name']}: {v:,} {title.lower()}" for r, v in zip(chrono, values)]
        charts.append({"title": title, "last": values[-1], "svg": svg.columns(values, labels, tips)})
    return charts


def render_dashboard(env, rows, standalone=True):
    return env.get_template("dashboard.html").render(
        rows=rows, trend=trend_charts(rows) if rows else [], standalone=standalone, root="",
        generated_at_text=f"{datetime.now(timezone.utc):%-d %b %Y, %H:%M} UTC")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fragment", type=Path, help="also write the latest weekly page without <html> wrapper here")
    args = ap.parse_args()

    env = environment()
    raw = [json.loads(p.read_text()) for p in sorted((args.data / "weekly").glob("*.json"))]
    views = [analyze(r) for r in raw]
    periods = [period_of(r) for r in raw]
    names = [v["period"]["name"] for v in views]
    (args.out / "weekly").mkdir(parents=True, exist_ok=True)
    for i, v in enumerate(views):
        args_i = (env, v, periods[i], [w["headline"] for w in views[:i + 1]],
                  names[i - 1] if i > 0 else None, names[i + 1] if i + 1 < len(names) else None)
        (args.out / "weekly" / f"{names[i]}.html").write_text(render_weekly(*args_i))
        if args.fragment and i == len(views) - 1:
            args.fragment.write_text(render_weekly(*args_i, standalone=False))
    rows = [{"name": v["period"]["name"], "start": v["period"]["start"], "last_day": v["period"]["last_day"],
             **v["headline"]} for v in reversed(views)]
    (args.out / "index.html").write_text(render_dashboard(env, rows))
    print(f"rendered {len(views)} weekly reports + dashboard -> {args.out}")


if __name__ == "__main__":
    main()
