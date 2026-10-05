"""Load the hand-edited content/ files (TOML, stdlib only) and the generated data/ files."""

import json
import sys
import tomllib
from pathlib import Path

CONTENT_FILES = ["site", "team", "publications", "news", "capabilities", "roadmap", "gallery"]


def load(root):
    root = Path(root)
    c = {name: tomllib.loads((root / "content" / f"{name}.toml").read_text()) for name in CONTENT_FILES}
    c["model_body"] = (root / "content" / "model_body.html").read_text()
    gfi = root / "data" / "site" / "good_first_issues.json"
    c["good_first_issues"] = json.loads(gfi.read_text()) if gfi.exists() else None
    c["latest_week"] = latest_week(root)
    return c


def latest_week(root):
    """Headline numbers of the newest archived weekly report, via the report package."""
    snaps = sorted((Path(root) / "data" / "weekly").glob("*.json"))
    if not snaps:
        return None
    sys.path.insert(0, str(Path(root) / "tools" / "report"))
    from phare_report.analyze import analyze  # noqa: E402  (sibling package, not installed)
    v = analyze(json.loads(snaps[-1].read_text()))
    return {"name": v["period"]["name"], "start": v["period"]["start"], "last_day": v["period"]["last_day"],
            **v["headline"]}


def validate_markers(c):
    """Count content still flagged for team validation."""
    n = 0
    n += bool(c["site"].get("validate_tagline"))
    n += sum(1 for r in c["capabilities"]["rows"] if r.get("validate"))
    n += bool(c["roadmap"].get("validate"))
    n += c["model_body"].count('class="validate"')
    return n
