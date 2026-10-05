"""GitHub source: issues, PRs, commits, Actions runs, releases, discussions.

Everything is normalized into plain JSON-friendly dicts so a snapshot can be
archived and re-analyzed later without the network.
"""

import os
import subprocess

import requests

API = "https://api.github.com"
OWNER, REPO = "PHAREHUB", "PHARE"
SLUG = f"{OWNER}/{REPO}"

ISSUE_FIELDS = """
  number title url createdAt closedAt updatedAt state stateReason
  author { login }
  labels(first: 20) { nodes { name } }
  comments(last: 100) { totalCount nodes { author { login } createdAt bodyText } }
  closedByPullRequestsReferences(first: 5, includeClosedPrs: true) { nodes { number merged } }
  timelineItems(itemTypes: CLOSED_EVENT, last: 1) {
    nodes { ... on ClosedEvent {
      createdAt actor { login }
      closer { __typename ... on PullRequest { number } ... on Commit { oid messageHeadline } }
    } }
  }
"""

PR_FIELDS = """
  number title url createdAt closedAt updatedAt mergedAt state isDraft merged
  author { login }
  mergedBy { login }
  baseRefName additions deletions changedFiles
  labels(first: 20) { nodes { name } }
  files(first: 100) { nodes { path additions deletions } }
  comments(last: 100) { totalCount nodes { author { login } createdAt } }
  reviews(last: 100) { nodes { author { login } submittedAt state comments { totalCount } } }
"""

SEARCH_QUERY = f"""
query($q: String!, $after: String) {{
  search(query: $q, type: ISSUE, first: 25, after: $after) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{
      __typename
      ... on Issue {{ {ISSUE_FIELDS} }}
      ... on PullRequest {{ {PR_FIELDS} }}
    }}
  }}
}}
"""


def token():
    if t := os.environ.get("GITHUB_TOKEN"):
        return t
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


class GitHub:
    def __init__(self, tok=None):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {tok or token()}",
                               "Accept": "application/vnd.github+json"})

    def graphql(self, query, **variables):
        r = self.s.post(f"{API}/graphql", json={"query": query, "variables": variables}, timeout=60)
        r.raise_for_status()
        body = r.json()
        if "errors" in body:
            raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body["data"]

    def rest_pages(self, path, key=None, **params):
        url, params = f"{API}/{path}", {"per_page": 100, **params}
        while url:
            r = self.s.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            yield from (data[key] if key else data)
            url, params = r.links.get("next", {}).get("url"), None

    def search(self, q):
        after = None
        while True:
            res = self.graphql(SEARCH_QUERY, q=q, after=after)["search"]
            yield from res["nodes"]
            if not res["pageInfo"]["hasNextPage"]:
                return
            after = res["pageInfo"]["endCursor"]

    def count(self, q):
        query = "query($q: String!) { search(query: $q, type: ISSUE, first: 0) { issueCount } }"
        return self.graphql(query, q=q)["search"]["issueCount"]


def _login(actor):
    return (actor or {}).get("login") or "ghost"


def _names(conn):
    return [n["name"] for n in conn["nodes"]]


def normalize_issue(n):
    closed = (n["timelineItems"]["nodes"] or [None])[-1]
    closer = (closed or {}).get("closer") or {}
    return {
        "number": n["number"], "title": n["title"], "url": n["url"],
        "author": _login(n["author"]), "labels": _names(n["labels"]),
        "created_at": n["createdAt"], "closed_at": n["closedAt"], "updated_at": n["updatedAt"],
        "state": n["state"], "state_reason": n["stateReason"],
        "closed_by": _login(closed["actor"]) if closed else None,
        "closer": {"type": closer["__typename"],
                   "ref": closer.get("number") or closer.get("oid"),
                   "headline": closer.get("messageHeadline")} if closer else None,
        "linked_prs": [p["number"] for p in n["closedByPullRequestsReferences"]["nodes"]],
        "comments": [{"author": _login(c["author"]), "created_at": c["createdAt"],
                      "body": c["bodyText"][:300]} for c in n["comments"]["nodes"]],
        "comment_count": n["comments"]["totalCount"],
    }


def normalize_pr(n):
    return {
        "number": n["number"], "title": n["title"], "url": n["url"],
        "author": _login(n["author"]), "labels": _names(n["labels"]),
        "created_at": n["createdAt"], "closed_at": n["closedAt"], "updated_at": n["updatedAt"],
        "merged_at": n["mergedAt"], "merged_by": _login(n["mergedBy"]) if n["mergedBy"] else None,
        "state": n["state"], "draft": n["isDraft"], "base": n["baseRefName"],
        "additions": n["additions"], "deletions": n["deletions"], "changed_files": n["changedFiles"],
        "files": [{"path": f["path"], "additions": f["additions"], "deletions": f["deletions"]}
                  for f in (n["files"] or {"nodes": []})["nodes"]],
        "comments": [{"author": _login(c["author"]), "created_at": c["createdAt"]}
                     for c in n["comments"]["nodes"]],
        "reviews": [{"author": _login(r["author"]), "submitted_at": r["submittedAt"],
                     "state": r["state"], "comments": r["comments"]["totalCount"]}
                    for r in n["reviews"]["nodes"] if r["submittedAt"]],
    }


def fetch_items(gh, since):
    """All issues and PRs updated since `since` (date string), split by type."""
    issues, prs = [], []
    for n in gh.search(f"repo:{SLUG} updated:>={since}"):
        if n["__typename"] == "Issue":
            issues.append(normalize_issue(n))
        elif n["__typename"] == "PullRequest":
            prs.append(normalize_pr(n))
    return issues, prs


def fetch_open_prs(gh):
    return [normalize_pr(n) for n in gh.search(f"repo:{SLUG} is:pr is:open")]


COMMITS_QUERY = """
query($since: GitTimestamp!, $until: GitTimestamp!, $after: String) {
  repository(owner: "PHAREHUB", name: "PHARE") {
    defaultBranchRef { name target { ... on Commit {
      history(since: $since, until: $until, first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { oid messageHeadline committedDate additions deletions
                author { name user { login } }
                associatedPullRequests(first: 1) { nodes { number } } }
      }
    } } }
  }
}
"""


def fetch_commits(gh, since, until):
    """Commits on the default branch (master) in [since, until), with per-file stats."""
    out, after = [], None
    while True:
        ref = gh.graphql(COMMITS_QUERY, since=since, until=until, after=after)["repository"]["defaultBranchRef"]
        hist = ref["target"]["history"]
        for c in hist["nodes"]:
            detail = gh.s.get(f"{API}/repos/{SLUG}/commits/{c['oid']}", timeout=60).json()
            prs = c["associatedPullRequests"]["nodes"]
            out.append({
                "sha": c["oid"], "headline": c["messageHeadline"], "date": c["committedDate"],
                "author": (c["author"]["user"] or {}).get("login") or c["author"]["name"],
                "additions": c["additions"], "deletions": c["deletions"],
                "pr": prs[0]["number"] if prs else None,
                "files": [{"path": f["filename"], "additions": f["additions"], "deletions": f["deletions"]}
                          for f in detail.get("files", [])],
            })
        if not hist["pageInfo"]["hasNextPage"]:
            return out
        after = hist["pageInfo"]["endCursor"]


def fetch_actions_runs(gh, since_day, last_day):
    return [{
        "id": r["id"], "workflow": r["name"], "event": r["event"], "branch": r["head_branch"],
        "sha": r["head_sha"], "status": r["status"], "conclusion": r["conclusion"],
        "created_at": r["created_at"], "attempt": r["run_attempt"], "actor": _login(r["actor"]),
    } for r in gh.rest_pages(f"repos/{SLUG}/actions/runs", key="workflow_runs",
                             created=f"{since_day}..{last_day}")]


REPO_EXTRAS_QUERY = """
{
  repository(owner: "PHAREHUB", name: "PHARE") {
    releases(first: 20, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { name tagName url createdAt publishedAt author { login } }
    }
    discussions(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { number title url createdAt updatedAt author { login } category { name }
              comments(last: 50) { nodes { author { login } createdAt } } }
    }
  }
}
"""


def fetch_releases_and_discussions(gh):
    repo = gh.graphql(REPO_EXTRAS_QUERY)["repository"]
    releases = [{"name": r["name"], "tag": r["tagName"], "url": r["url"], "created_at": r["createdAt"],
                 "published_at": r["publishedAt"], "author": _login(r["author"])}
                for r in repo["releases"]["nodes"]]
    discussions = [{"number": d["number"], "title": d["title"], "url": d["url"],
                    "created_at": d["createdAt"], "updated_at": d["updatedAt"],
                    "author": _login(d["author"]), "category": d["category"]["name"],
                    "comments": [{"author": _login(c["author"]), "created_at": c["createdAt"]}
                                 for c in d["comments"]["nodes"]]}
                   for d in repo["discussions"]["nodes"]]
    return releases, discussions


def fetch_backlog(gh, start_day, end_day):
    """Open issue/PR counts at the start and end of the window: created before t minus closed before t.

    Approximate if items were reopened; good enough for a trend.
    """
    def open_at(kind, day):
        return gh.count(f"repo:{SLUG} is:{kind} created:<{day}") - gh.count(f"repo:{SLUG} is:{kind} closed:<{day}")
    return {kind: {"start": open_at(kind, start_day), "end": open_at(kind, end_day)} for kind in ("issue", "pr")}


def fetch_prior_pr_counts(gh, authors, before_day):
    """Number of PRs each author opened before the window (0 = first-time contributor)."""
    return {a: gh.count(f"repo:{SLUG} is:pr author:{a} created:<{before_day}") for a in sorted(authors)}
