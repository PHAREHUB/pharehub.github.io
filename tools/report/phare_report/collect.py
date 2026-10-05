"""Fetch everything about one period and archive it as a raw snapshot JSON.

    python -m phare_report.collect 2026-W40 --data ../../data    # writes data/weekly/2026-W40.json
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import period as periods
from .sources import github, teamcity

SNAPSHOT_VERSION = 1


def _active(p, item, *keys):
    """True if any timestamp of the item, or of its comments/reviews, falls inside the period."""
    times = [item.get(k) for k in keys]
    times += [c["created_at"] for c in item.get("comments", [])]
    times += [r["submitted_at"] for r in item.get("reviews", [])]
    return any(p.contains(periods.parse_ts(t)) for t in times if t)


def trim(snap):
    """Drop items with no activity inside the period (the search returns everything touched since its start)."""
    p = periods.parse(snap["period"]["name"])
    snap["issues"] = [i for i in snap["issues"] if _active(p, i, "created_at", "closed_at")]
    snap["prs"] = [x for x in snap["prs"] if _active(p, x, "created_at", "closed_at", "merged_at")]
    snap["discussions"] = [d for d in snap["discussions"] if _active(p, d, "created_at")]
    snap["releases"] = [r for r in snap["releases"] if _active(p, r, "created_at")]
    return snap


def collect(p, gh=None):
    gh = gh or github.GitHub()
    start_day, end_day = p.start.date(), p.end.date()
    last_day = end_day - timedelta(days=1)

    issues, prs = github.fetch_items(gh, start_day.isoformat())
    authors = {pr["author"] for pr in prs if p.contains(periods.parse_ts(pr["created_at"]))}
    releases, discussions = github.fetch_releases_and_discussions(gh)

    return trim({
        "version": SNAPSHOT_VERSION,
        "repo": github.SLUG,
        "period": {"name": p.name, "kind": p.kind, "start": p.start.isoformat(), "end": p.end.isoformat()},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "issues": issues,
        "prs": prs,
        "open_prs": github.fetch_open_prs(gh),
        "commits": github.fetch_commits(gh, p.start.isoformat(), p.end.isoformat()),
        "actions_runs": github.fetch_actions_runs(gh, start_day.isoformat(), last_day.isoformat()),
        "releases": releases,
        "discussions": discussions,
        "backlog": github.fetch_backlog(gh, start_day.isoformat(), end_day.isoformat()),
        "prior_pr_counts": github.fetch_prior_pr_counts(gh, authors, start_day.isoformat()),
        "teamcity": teamcity.fetch(p.start, p.end),
    })


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("period", nargs="?", help="e.g. 2026-W40 (default: last complete ISO week)")
    ap.add_argument("--data", type=Path, help="data directory; the snapshot goes to <data>/weekly/<period>.json")
    ap.add_argument("-o", "--output", type=Path, help="explicit output file instead of --data")
    args = ap.parse_args()

    p = periods.parse(args.period) if args.period else periods.last_complete_week(datetime.now(timezone.utc))
    if not (args.output or args.data):
        ap.error("give --data or --output")
    args.output = args.output or args.data / p.kind / f"{p.name}.json"
    snap = collect(p)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
    print(f"{p.name}: {len(snap['issues'])} issues, {len(snap['prs'])} PRs, {len(snap['commits'])} commits, "
          f"{len(snap['actions_runs'])} Actions runs, "
          f"{len((snap['teamcity'] or {}).get('builds', []))} TeamCity builds -> {args.output}")


if __name__ == "__main__":
    main()
