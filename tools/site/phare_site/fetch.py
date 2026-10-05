"""Fetch the open "good first issue" list into data/site/good_first_issues.json (network step).

    python -m phare_site.fetch --root ../..

The build reads the saved file, so building the site never needs the network.
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

QUERY = 'repo:PHAREHUB/PHARE is:issue is:open label:"good first issue"'


def token():
    if t := os.environ.get("GITHUB_TOKEN"):
        return t
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def fetch(tok=None):
    r = requests.get("https://api.github.com/search/issues", params={"q": QUERY, "per_page": 50, "sort": "created"},
                     headers={"Authorization": f"Bearer {tok or token()}", "Accept": "application/vnd.github+json"},
                     timeout=60)
    r.raise_for_status()
    return [{"number": i["number"], "title": i["title"], "url": i["html_url"],
             "labels": sorted(l["name"] for l in i["labels"] if l["name"] != "good first issue"),
             "created_at": i["created_at"]} for i in r.json()["items"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True, help="site repository root")
    args = ap.parse_args()
    out = args.root / "data" / "site" / "good_first_issues.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        issues = fetch()
    except requests.RequestException as e:
        print(f"good first issues not refreshed ({e}); keeping {out}")
        return
    out.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "issues": issues}, indent=1) + "\n")
    print(f"{len(issues)} good first issues -> {out}")


if __name__ == "__main__":
    main()
