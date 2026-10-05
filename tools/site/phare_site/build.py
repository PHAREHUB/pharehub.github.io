"""Build the site pages at the repository root from templates + content/ + data/.

    python -m phare_site.build --root ../..            # publishable pages
    python -m phare_site.build --root ../.. --drafts   # also show "to validate" badges

Offline and deterministic: the same inputs give the same pages.
"""

import argparse
import re
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader, select_autoescape

from . import content

PAGES = [  # (file, nav label, template)
    ("index.html", "Home", "index.html"),
    ("get-started.html", "Installation", "get-started.html"),
    ("science.html", "Test cases", "science.html"),
    ("model.html", "Model", "model.html"),
    ("contribute.html", "Contributing", "contribute.html"),
    ("about.html", "Team and citation", "about.html"),
]

# old URLs kept alive
REDIRECTS = {
    "amrhybrid.html": "model.html",
    "firstrun2grids.html": "model.html#first-run",
}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")


def prepare_document(body):
    """Give every h2/h3 an id, collect them into a table of contents, drop inline styles and empty paragraphs."""
    toc = []

    def heading(m):
        level, attrs, inner = m[1], m[2] or "", m[3]
        hid = (re.search(r'id="([^"]+)"', attrs) or [None, slug(inner)])[1]
        if level in "23":
            toc.append({"level": int(level), "id": hid, "title": re.sub(r"<[^>]+>", "", inner).strip()})
        return f'<h{level} id="{hid}">{inner}</h{level}>'

    body = re.sub(r"<h([234])(\s[^>]*)?>(.*?)</h\1>", heading, body, flags=re.S)
    body = re.sub(r'\s+style="[^"]*"', "", body)
    body = re.sub(r"<p>\s*</p>", "", body)
    return toc, body


def environment(root):
    common = Path(root) / "tools" / "common"
    env = Environment(loader=ChoiceLoader([PackageLoader("phare_site", "templates"), FileSystemLoader(common)]),
                      autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.filters["num"] = lambda v: "–" if v is None else f"{v:,}"
    return env


def build(root, drafts=False):
    root = Path(root)
    c = content.load(root)
    c["model_toc"], c["model_body"] = prepare_document(c["model_body"])
    env = environment(root)
    nav = [(f, label) for f, label, _ in PAGES]
    written = []
    for f, label, tpl in PAGES:
        html = env.get_template(tpl).render(c=c, nav=nav, current=f, drafts=drafts)
        (root / f).write_text(html)
        written.append(f)
    for old, new in REDIRECTS.items():
        (root / old).write_text(env.get_template("redirect.html").render(target=new))
        written.append(old)
    return written, content.validate_markers(c)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True, help="site repository root")
    ap.add_argument("--drafts", action="store_true", help="show 'to validate' badges on drafted content")
    args = ap.parse_args()
    written, pending = build(args.root, args.drafts)
    print(f"built {len(written)} pages; {pending} content blocks still marked 'to validate'")


if __name__ == "__main__":
    main()
