"""TeamCity source: PHARE builds and their test counts, via read-only guest access."""

import requests

from ..period import parse_ts

URL = "https://hephaistos.lpp.polytechnique.fr/teamcity/guestAuth/app/rest"
PROJECT = "Phare"
RETENTION_CAP = 195  # configs keep ~200 builds; at the cap, older builds have been deleted
BUILD_FIELDS = ("id,buildTypeId,number,status,state,branchName,startDate,finishDate,webUrl,"
                "revisions(revision(version)),testOccurrences(count,passed,failed,ignored,muted)")


def _get(path, **params):
    r = requests.get(f"{URL}/{path}", params=params, headers={"Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    return r.json()


def _tc_date(day):
    return day.strftime("%Y%m%dT000000+0000")


def fetch(start, end):
    """Build configs and finished builds with finishDate in [start, end) (UTC datetimes).

    Returns {"error": ...} if TeamCity is unreachable, so the report can say so and still publish.
    """
    try:
        configs = _get("buildTypes", locator=f"affectedProject:(id:{PROJECT})",
                       fields="buildType(id,name,projectName,paused)")["buildType"]
        builds = _get("builds", fields=f"count,build({BUILD_FIELDS})",
                      locator=f"affectedProject:(id:{PROJECT}),state:finished,defaultFilter:false,count:2000,"
                              f"finishDate:(date:{_tc_date(start)},condition:after)")["build"]
        builds = [b for b in builds if parse_ts(b["finishDate"]) < end]
        failed_tests = {}
        for b in builds:
            if (b.get("testOccurrences") or {}).get("failed"):
                occ = _get("testOccurrences", locator=f"build:(id:{b['id']}),status:FAILURE,count:50",
                           fields="testOccurrence(name)")
                failed_tests[b["id"]] = [t["name"] for t in occ.get("testOccurrence", [])]
        retained = _get("builds", fields="build(buildTypeId,finishDate)",
                        locator=f"affectedProject:(id:{PROJECT}),state:finished,defaultFilter:false,count:20000")["build"]
    except requests.RequestException as e:
        return {"error": str(e)}

    names = {c["id"]: c["name"] for c in configs}
    by_config = {}
    for b in retained:
        by_config.setdefault(b["buildTypeId"], []).append(parse_ts(b["finishDate"]))
    # history start = 11th-oldest retained build: a few pinned/stray old builds survive cleanup
    since = {cid: sorted(ts)[min(10, len(ts) - 1)] for cid, ts in by_config.items() if len(ts) >= RETENTION_CAP}
    partial = [{"config": names.get(cid, cid), "since": t.isoformat()}
               for cid, t in sorted(since.items()) if t > start]

    return {
        "partial_configs": partial,
        "configs": [{"id": c["id"], "name": c["name"], "project": c["projectName"], "paused": c["paused"]}
                    for c in configs],
        "builds": [{
            "id": b["id"], "config": b["buildTypeId"], "number": b.get("number"),
            "status": b["status"], "branch": b.get("branchName"),
            "started_at": b.get("startDate"), "finished_at": b["finishDate"], "url": b.get("webUrl"),
            "revision": next((r["version"] for r in b["revisions"].get("revision", [])), None),
            "tests": b.get("testOccurrences"),
            "failed_tests": failed_tests.get(b["id"], []),
        } for b in builds],
    }
