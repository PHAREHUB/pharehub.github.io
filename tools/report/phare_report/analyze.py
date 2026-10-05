"""Turn a raw snapshot into the numbers and lists a report shows. Pure: no network."""

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from .period import Period, parse_ts

BOTS = {"coderabbitai", "copilot-pull-request-reviewer", "github-advanced-security", "copilot",
        "github-actions", "dependabot", "ghost"}

# first matching prefix wins; seven areas + "other" so each gets one fixed categorical color
AREAS = [
    ("src/core/", "core"), ("src/amr/", "amr"), ("src/", "simulator/io"),
    ("pyphare/", "python"), ("tests/", "tests"),
    (".github/", "build/ci"), ("res/", "build/ci"), ("tools/", "build/ci"), ("doc/", "doc"),
]
AREA_ORDER = ["core", "amr", "python", "tests", "simulator/io", "build/ci", "doc", "other"]

TC_MASTER_BRANCHES = {"refs/heads/master", "master", "<default>"}
STALE_DAYS = 30
CLOSING_COMMENT_WINDOW = timedelta(minutes=10)


def is_bot(login):
    return login.lower() in BOTS or login.endswith("[bot]")


def area_of(path):
    if "/" not in path and path.startswith("CMakeLists"):
        return "build/ci"
    return next((a for prefix, a in AREAS if path.startswith(prefix)), "other")


def areas_of(files):
    return sorted({area_of(f["path"]) for f in files}, key=AREA_ORDER.index)


def lines_by_area(files):
    out = Counter()
    for f in files:
        out[area_of(f["path"])] += f["additions"] + f["deletions"]
    return {a: out[a] for a in AREA_ORDER if out[a]}


def period_of(snap):
    p = snap["period"]
    return Period(p["name"], p["kind"], parse_ts(p["start"]), parse_ts(p["end"]))


def _hours(a, b):
    return (b - a).total_seconds() / 3600


# --- issues -----------------------------------------------------------------

def closing_comment(issue):
    """The closer's own comment posted just before closing, if any: often says why."""
    closed_at = parse_ts(issue["closed_at"])
    for c in reversed(issue["comments"]):
        t = parse_ts(c["created_at"])
        if c["author"] == issue["closed_by"] and timedelta(0) <= closed_at - t <= CLOSING_COMMENT_WINDOW:
            return c["body"]
    return None


def issue_outcome(issue):
    if issue["state"] == "OPEN":
        return "reopened since"
    return {"COMPLETED": "completed", "NOT_PLANNED": "not planned",
            "DUPLICATE": "duplicate"}.get(issue["state_reason"], (issue["state_reason"] or "closed").lower())


def issue_how(issue):
    closer = issue["closer"]
    if closer and closer["type"] == "PullRequest":
        return {"kind": "pr", "ref": closer["ref"]}
    if closer and closer["type"] == "Commit":
        return {"kind": "commit", "ref": closer["ref"][:9], "headline": closer["headline"]}
    if issue["linked_prs"]:
        return {"kind": "pr", "ref": issue["linked_prs"][0]}
    return {"kind": "manual", "by": issue["closed_by"], "comment": closing_comment(issue)}


def issue_row(issue):
    return {**{k: issue[k] for k in ("number", "title", "url", "author", "labels")},
            "created_at": parse_ts(issue["created_at"]), "closed_at": parse_ts(issue["closed_at"])}


# --- pull requests ----------------------------------------------------------

def human_reviews(pr):
    return [r for r in pr["reviews"] if r["author"] != pr["author"] and not is_bot(r["author"])]


def first_review_hours(pr):
    times = [parse_ts(r["submitted_at"]) for r in human_reviews(pr)]
    return _hours(parse_ts(pr["created_at"]), min(times)) if times else None


def pr_state(pr):
    if pr["merged_at"]:
        return "merged"
    if pr["closed_at"]:
        return "closed"
    return "draft" if pr["draft"] else "open"


def pr_row(pr, now):
    end = parse_ts(pr["merged_at"] or pr["closed_at"]) or now
    return {
        "number": pr["number"], "title": pr["title"], "url": pr["url"], "author": pr["author"],
        "draft": pr["draft"], "labels": pr["labels"], "state": pr_state(pr),
        "created_at": parse_ts(pr["created_at"]), "merged_at": parse_ts(pr["merged_at"]),
        "closed_at": parse_ts(pr["closed_at"]),
        "lines_by_area": lines_by_area(pr["files"]),
        "additions": pr["additions"], "deletions": pr["deletions"], "changed_files": pr["changed_files"],
        "areas": areas_of(pr["files"]),
        "open_days": round(_hours(parse_ts(pr["created_at"]), end) / 24, 1),
        "reviewers": sorted({r["author"] for r in human_reviews(pr)}),
        "bot_reviewers": sorted({r["author"] for r in pr["reviews"] if is_bot(r["author"])}),
        "merged_by": pr.get("merged_by"),
        "first_review_h": first_review_hours(pr),
    }


# --- CI ---------------------------------------------------------------------

def tc_group(config):
    if "_Users_" in config["id"]:
        return "personal"
    if "Next CI" in config["project"]:
        return "shadow (next CI)"
    return "main"


def tc_lane_name(cid, configs):
    """Config name; personal configs ("Phare_Phare_Users_Phil_Build") are prefixed with their owner."""
    name = configs.get(cid, {}).get("name", cid)
    if "_Users_" in cid:
        return f"{cid.split('_Users_')[1].split('_')[0]} · {name}"
    return name


def teamcity_summary(tc):
    if not tc or "error" in tc:
        return {"error": (tc or {}).get("error", "no data")}
    configs = {c["id"]: c for c in tc["configs"]}
    per = defaultdict(lambda: Counter())
    tests = defaultdict(lambda: {"runs": 0, "passed": 0, "failed": 0, "ignored": 0, "max_count": 0})
    by_rev = defaultdict(list)
    failing = Counter()
    for b in tc["builds"]:
        status = {"UNKNOWN": "canceled"}.get(b["status"], b["status"].lower())
        per[b["config"]][status] += 1
        if b["branch"] in TC_MASTER_BRANCHES:
            per[b["config"]][f"master_{status}"] += 1
        if t := b["tests"]:
            s = tests[b["config"]]
            s["runs"] += t.get("count", 0)
            s["passed"] += t.get("passed", 0)
            s["failed"] += t.get("failed", 0)
            s["ignored"] += t.get("ignored", 0)
            s["max_count"] = max(s["max_count"], t.get("count", 0))
        if b["revision"] and status in ("success", "failure"):
            by_rev[(b["config"], b["revision"])].append(b)
        failing.update(b["failed_tests"])

    rows = []
    for cid, counts in per.items():
        c = configs.get(cid, {"id": cid, "name": cid, "project": "?"})
        rows.append({"id": cid, "name": c["name"], "group": tc_group(c),
                     "success": counts["success"], "failure": counts["failure"], "canceled": counts["canceled"],
                     "master_failure": counts["master_failure"],
                     "master_builds": sum(v for k, v in counts.items() if k.startswith("master_")),
                     "tests": tests.get(cid)})
    rows.sort(key=lambda r: (r["group"] != "main", -(r["success"] + r["failure"] + r["canceled"])))

    # same config + same commit, both red and green: a test that failed then passed is a flaky
    # candidate; a red build without failed tests is a build/infra failure fixed by a rerun
    flaky, green_reruns = [], 0
    for (cid, rev), builds in by_rev.items():
        if {b["status"] for b in builds} == {"SUCCESS", "FAILURE"}:
            failed = sorted({t for b in builds for t in b["failed_tests"]})
            if failed:
                flaky.append({"config": configs.get(cid, {}).get("name", cid), "revision": rev[:9],
                              "builds": len(builds), "failed_tests": failed})
            else:
                green_reruns += 1

    total = {k: sum((s[k] for s in tests.values()), 0) for k in ("runs", "passed", "failed", "ignored")}
    return {"configs": rows, "tests": total, "flaky": flaky, "green_reruns": green_reruns,
            "failing_tests": failing.most_common(10), "builds": len(tc["builds"])}


def actions_summary(runs):
    per = defaultdict(Counter)
    for r in runs:
        per[r["workflow"]][r["conclusion"] or r["status"]] += 1
        if r["branch"] == "master" and r["event"] == "push":
            per[r["workflow"]]["master_" + (r["conclusion"] or r["status"])] += 1
    return sorted(({"workflow": w, "success": c["success"], "failure": c["failure"],
                    "cancelled": c["cancelled"], "master_failure": c["master_failure"],
                    "total": sum(v for k, v in c.items() if not k.startswith("master_"))}
                   for w, c in per.items()), key=lambda r: -r["total"])


# --- whole report -----------------------------------------------------------

def analyze(snap):
    p = period_of(snap)
    now = parse_ts(snap["generated_at"])
    within = lambda s: p.contains(parse_ts(s))
    # "current state" lists (waiting for review, stale) only make sense right after the period ends
    current = now - p.end < timedelta(days=8)

    issues, prs = snap["issues"], snap["prs"]
    issues_opened = [i for i in issues if within(i["created_at"])]
    issues_closed = [i for i in issues if within(i["closed_at"])]
    prs_opened = [x for x in prs if within(x["created_at"])]
    prs_merged = [x for x in prs if within(x["merged_at"])]
    prs_closed = [x for x in prs if within(x["closed_at"]) and not x["merged_at"]]
    commits = [c for c in snap["commits"] if within(c["date"])]
    reviews = [(x, r) for x in prs for r in x["reviews"] if within(r["submitted_at"])]
    comments = ([(i, c) for i in issues for c in i["comments"] if within(c["created_at"])]
                + [(x, c) for x in prs for c in x["comments"] if within(c["created_at"])]
                + [(d, c) for d in snap["discussions"] for c in d["comments"] if within(c["created_at"])])
    tc = snap.get("teamcity") or {}
    tc_builds = [b for b in tc.get("builds", []) if within(b["finished_at"])]
    runs = [r for r in snap["actions_runs"] if within(r["created_at"])]

    # per day
    days = {d: Counter() for d in p.days()}
    def bump(ts, key):
        if (t := parse_ts(ts)) and t.date() in days:
            days[t.date()][key] += 1
    for c in commits: bump(c["date"], "commits")
    for i in issues_opened: bump(i["created_at"], "issues_opened")
    for i in issues_closed: bump(i["closed_at"], "issues_closed")
    for x in prs_opened: bump(x["created_at"], "prs_opened")
    for x in prs_merged: bump(x["merged_at"], "prs_merged")
    for x in prs_closed: bump(x["closed_at"], "prs_closed")
    for x, r in reviews:
        if not is_bot(r["author"]) and r["author"] != x["author"]: bump(r["submitted_at"], "reviews")
    for _, c in comments:
        if not is_bot(c["author"]): bump(c["created_at"], "comments")
    for b in tc_builds:
        bump(b["finished_at"], "ci_builds")
        if b["status"] == "FAILURE": bump(b["finished_at"], "ci_failed")
    for r in runs:
        bump(r["created_at"], "ci_builds")
        if r["conclusion"] == "failure": bump(r["created_at"], "ci_failed")

    # authors
    a = defaultdict(Counter)
    for c in commits:
        a[c["author"]]["commits"] += 1
        a[c["author"]]["lines_added"] += c["additions"]
        a[c["author"]]["lines_removed"] += c["deletions"]
    for i in issues_opened: a[i["author"]]["issues_opened"] += 1
    for i in issues_closed:
        if i["closed_by"]: a[i["closed_by"]]["issues_closed"] += 1
    for x in prs_opened: a[x["author"]]["prs_opened"] += 1
    for x in prs_merged: a[x["author"]]["prs_merged"] += 1
    for x, r in reviews:
        if r["author"] != x["author"]: a[r["author"]]["reviews"] += 1
    for _, c in comments: a[c["author"]]["comments"] += 1
    prior = snap.get("prior_pr_counts", {})
    authors = sorted(({"login": login, "bot": is_bot(login), "first_time": prior.get(login) == 0, **counts}
                      for login, counts in a.items()),
                     key=lambda r: (r["bot"], -sum(v for k, v in r.items() if k in
                                                   ("commits", "prs_opened", "prs_merged", "reviews",
                                                    "issues_opened", "issues_closed", "comments")), r["login"]))

    # reviews
    first_reviews = [h for x in prs_opened + prs_merged if (h := first_review_hours(x)) is not None]
    merge_days = [_hours(parse_ts(x["created_at"]), parse_ts(x["merged_at"])) / 24 for x in prs_merged]

    # churn on master
    churn = defaultdict(Counter)
    for c in commits:
        for f in c["files"]:
            ar = area_of(f["path"])
            churn[ar]["additions"] += f["additions"]
            churn[ar]["deletions"] += f["deletions"]
            churn[ar]["files"] += 1
    churn = sorted(({"area": k, **v} for k, v in churn.items()), key=lambda r: -(r["additions"] + r["deletions"]))

    open_prs = [x for x in snap.get("open_prs", []) if not x["draft"]]
    waiting = [pr_row(x, now) for x in open_prs if not human_reviews(x)] if current else None
    stale = ([pr_row(x, now) for x in open_prs if now - parse_ts(x["updated_at"]) > timedelta(days=STALE_DAYS)]
             if current else None)
    unanswered = [issue_row(i) for i in issues_opened if i["state"] == "OPEN"
                  and not any(c["author"] != i["author"] and not is_bot(c["author"]) for c in i["comments"])]

    review_events = sorted(({"t": parse_ts(r["submitted_at"]), "reviewer": r["author"], "author": x["author"],
                             "number": x["number"], "title": x["title"], "state": r["state"]}
                            for x, r in reviews if not is_bot(r["author"]) and r["author"] != x["author"]),
                           key=lambda e: e["t"])
    tc_names = {c["id"]: c for c in tc.get("configs", [])}
    ci_events = sorted(
        [{"t": parse_ts(b["finished_at"]), "source": "TeamCity",
          "lane": tc_lane_name(b["config"], tc_names),
          "group": tc_group(tc_names.get(b["config"], {"id": b["config"], "project": ""})),
          "status": {"SUCCESS": "ok", "FAILURE": "bad"}.get(b["status"], "skip"),
          "branch": b["branch"], "tests": b["tests"]} for b in tc_builds]
        + [{"t": parse_ts(r["created_at"]), "source": "GitHub Actions", "lane": r["workflow"], "group": "actions",
            "status": {"success": "ok", "failure": "bad"}.get(r["conclusion"], "skip"),
            "branch": r["branch"], "tests": None} for r in runs],
        key=lambda e: e["t"])

    tc_window = {**tc, "builds": tc_builds} if "builds" in tc else tc
    tcs = teamcity_summary(tc_window)

    return {
        "period": {"name": p.name, "kind": p.kind, "start": p.start.date(), "last_day": (p.end - timedelta(days=1)).date()},
        "generated_at": now,
        "current": current,
        "headline": {
            "commits": len(commits), "issues_opened": len(issues_opened), "issues_closed": len(issues_closed),
            "prs_opened": len(prs_opened), "prs_merged": len(prs_merged), "prs_closed": len(prs_closed),
            "reviews": sum(1 for x, r in reviews if not is_bot(r["author"]) and r["author"] != x["author"]),
            "comments": sum(1 for _, c in comments if not is_bot(c["author"])),
            "ci_builds": len(tc_builds) + len(runs),
            "tests_run": (tcs.get("tests") or {}).get("runs", 0),
        },
        "days": [{"date": d, **days[d]} for d in sorted(days)],
        "issues_opened": [issue_row(i) for i in issues_opened],
        "issues_closed": [{**issue_row(i), "outcome": issue_outcome(i), "how": issue_how(i)} for i in issues_closed],
        "prs_opened": [pr_row(x, now) for x in prs_opened],
        "prs_merged": [pr_row(x, now) for x in prs_merged],
        "prs_closed": [pr_row(x, now) for x in prs_closed],
        "authors": authors,
        "review_times": {"first_review_h_median": median(first_reviews) if first_reviews else None,
                         "first_review_n": len(first_reviews),
                         "merge_days_median": median(merge_days) if merge_days else None,
                         "merge_n": len(merge_days)},
        "waiting_for_review": waiting,
        "stale_prs": stale,
        "unanswered_issues": unanswered,
        "backlog": snap["backlog"],
        "review_events": review_events,
        "ci_events": ci_events,
        "teamcity_partial": tc.get("partial_configs", []),
        "churn": churn,
        "commits": [{**c, "t": parse_ts(c["date"])} for c in commits],
        "actions": actions_summary(runs),
        "teamcity": tcs,
        "releases": [r for r in snap["releases"] if within(r["created_at"])],
        "discussions": [d for d in snap["discussions"]
                        if within(d["created_at"]) or any(within(c["created_at"]) for c in d["comments"])],
    }
