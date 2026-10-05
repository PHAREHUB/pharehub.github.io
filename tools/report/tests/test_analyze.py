from phare_report.analyze import analyze, area_of, issue_how, issue_outcome, teamcity_summary

# a week: 2026-09-28 (Mon) .. 2026-10-05 (exclusive)
IN, IN2, BEFORE, AFTER = "2026-09-30T10:00:00Z", "2026-10-01T12:00:00Z", "2026-09-01T00:00:00Z", "2026-10-06T00:00:00Z"


def issue(**kw):
    base = {"number": 1, "title": "t", "url": "u", "author": "alice", "labels": [],
            "created_at": BEFORE, "closed_at": None, "updated_at": IN, "state": "OPEN", "state_reason": None,
            "closed_by": None, "closer": None, "linked_prs": [], "comments": [], "comment_count": 0}
    return {**base, **kw}


def pr(**kw):
    base = {"number": 10, "title": "p", "url": "u", "author": "alice", "labels": [],
            "created_at": BEFORE, "closed_at": None, "updated_at": IN, "merged_at": None, "merged_by": None,
            "state": "OPEN", "draft": False, "base": "master", "additions": 1, "deletions": 1,
            "changed_files": 1, "files": [], "comments": [], "reviews": []}
    return {**base, **kw}


def snapshot(**kw):
    base = {"period": {"name": "2026-W40", "kind": "weekly",
                       "start": "2026-09-28T00:00:00+00:00", "end": "2026-10-05T00:00:00+00:00"},
            "generated_at": "2026-10-05T06:00:00+00:00",
            "issues": [], "prs": [], "open_prs": [], "commits": [], "actions_runs": [],
            "releases": [], "discussions": [], "backlog": {}, "prior_pr_counts": {},
            "teamcity": {"configs": [], "builds": []}}
    return {**base, **kw}


def closed(**kw):
    return issue(state="CLOSED", state_reason="COMPLETED", closed_at=IN2, closed_by="bob", **kw)


# --- how an issue was closed ------------------------------------------------

def test_closed_by_pr():
    i = closed(closer={"type": "PullRequest", "ref": 42, "headline": None})
    assert issue_how(i) == {"kind": "pr", "ref": 42}


def test_closed_by_commit():
    i = closed(closer={"type": "Commit", "ref": "abcdef1234567", "headline": "fix it"})
    assert issue_how(i) == {"kind": "commit", "ref": "abcdef123", "headline": "fix it"}


def test_closed_manually_without_pr_uses_closers_last_comment():
    i = closed(comments=[{"author": "bob", "created_at": "2026-10-01T11:55:00Z", "body": "done in #7"}])
    assert issue_how(i) == {"kind": "manual", "by": "bob", "comment": "done in #7"}


def test_closing_comment_must_be_recent_and_by_closer():
    i = closed(comments=[{"author": "bob", "created_at": "2026-10-01T09:00:00Z", "body": "old"},
                         {"author": "carol", "created_at": "2026-10-01T11:59:00Z", "body": "not closer"}])
    assert issue_how(i)["comment"] is None


def test_outcomes():
    assert issue_outcome(closed()) == "completed"
    assert issue_outcome(issue(state="CLOSED", state_reason="NOT_PLANNED")) == "not planned"
    assert issue_outcome(issue(state="OPEN", closed_at=IN2)) == "reopened since"


# --- whole-report counts ----------------------------------------------------

def test_window_filtering_and_pr_buckets():
    v = analyze(snapshot(
        issues=[issue(number=1, created_at=IN), issue(number=2, created_at=BEFORE), issue(number=3, created_at=AFTER)],
        prs=[pr(number=10, created_at=IN), pr(number=11, merged_at=IN2, closed_at=IN2, state="MERGED"),
             pr(number=12, closed_at=IN2, state="CLOSED")]))
    assert [i["number"] for i in v["issues_opened"]] == [1]
    assert [x["number"] for x in v["prs_opened"]] == [10]
    assert [x["number"] for x in v["prs_merged"]] == [11]
    assert [x["number"] for x in v["prs_closed"]] == [12]


def test_first_review_ignores_bots_and_self():
    reviews = [{"author": "coderabbitai", "submitted_at": "2026-09-30T10:30:00Z", "state": "COMMENTED", "comments": 0},
               {"author": "alice", "submitted_at": "2026-09-30T11:00:00Z", "state": "COMMENTED", "comments": 0},
               {"author": "bob", "submitted_at": "2026-09-30T14:00:00Z", "state": "APPROVED", "comments": 0}]
    v = analyze(snapshot(prs=[pr(created_at=IN, reviews=reviews)]))
    assert v["prs_opened"][0]["first_review_h"] == 4.0
    assert v["prs_opened"][0]["reviewers"] == ["bob"]
    assert v["headline"]["reviews"] == 1
    bot = next(a for a in v["authors"] if a["login"] == "coderabbitai")
    assert bot["bot"] and v["authors"][-1]["bot"]


def test_first_time_contributor():
    v = analyze(snapshot(prs=[pr(author="newbie", created_at=IN)], prior_pr_counts={"newbie": 0}))
    assert v["authors"][0] == {"login": "newbie", "bot": False, "first_time": True, "prs_opened": 1}


def test_current_state_lists_only_right_after_the_period():
    late = analyze(snapshot(generated_at="2026-11-20T00:00:00+00:00", open_prs=[pr()]))
    assert late["waiting_for_review"] is None and late["stale_prs"] is None
    fresh = analyze(snapshot(open_prs=[pr(), pr(number=11, draft=True)]))
    assert [x["number"] for x in fresh["waiting_for_review"]] == [10]


def test_per_day_counts():
    v = analyze(snapshot(issues=[issue(created_at=IN)], commits=[
        {"sha": "a", "headline": "h", "date": IN, "author": "bob", "additions": 3, "deletions": 1, "pr": None,
         "files": [{"path": "src/core/x.hpp", "additions": 3, "deletions": 1}]}]))
    wed = next(d for d in v["days"] if str(d["date"]) == "2026-09-30")
    assert wed["issues_opened"] == 1 and wed["commits"] == 1
    assert v["churn"] == [{"area": "core", "additions": 3, "deletions": 1, "files": 1}]


# --- CI ---------------------------------------------------------------------

def test_area_mapping():
    assert area_of("src/core/data/grid/gridlayout.hpp") == "core"
    assert area_of("src/hdf5/writer.hpp") == "simulator/io"
    assert area_of("src/simulator/simulator.hpp") == "simulator/io"
    assert area_of("pyphare/pyphare/pharein/__init__.py") == "python"
    assert area_of("CMakeLists.txt") == "build/ci"
    assert area_of("README.md") == "other"


def build(id, status, rev="r1", failed_tests=(), tests=None, branch="pull/1"):
    return {"id": id, "config": "c", "number": str(id), "status": status, "branch": branch,
            "started_at": None, "finished_at": "20261001T120000+0000", "url": None, "revision": rev,
            "tests": tests, "failed_tests": list(failed_tests)}


def test_flaky_vs_green_rerun():
    tc = {"configs": [{"id": "c", "name": "gh_pr_gcc", "project": "Phare / Phare", "paused": False}],
          "builds": [build(1, "FAILURE", "r1", ["A.test"]), build(2, "SUCCESS", "r1"),
                     build(3, "FAILURE", "r2"), build(4, "SUCCESS", "r2"),
                     build(5, "UNKNOWN", "r3")]}
    s = teamcity_summary(tc)
    assert s["flaky"] == [{"config": "gh_pr_gcc", "revision": "r1", "builds": 2, "failed_tests": ["A.test"]}]
    assert s["green_reruns"] == 1
    assert s["configs"][0]["canceled"] == 1


def test_teamcity_unavailable_still_reports():
    v = analyze(snapshot(teamcity={"error": "connection refused"}))
    assert v["teamcity"] == {"error": "connection refused"}
    assert v["headline"]["tests_run"] == 0
