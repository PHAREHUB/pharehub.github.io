"""Build the site pages at the repository root from templates + content/ + data/.

    python -m phare_site.build --root ../..            # publishable pages
    python -m phare_site.build --root ../.. --drafts   # also show "to validate" badges

Offline and deterministic: the same inputs give the same pages.
"""

import argparse
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader, select_autoescape

from . import content

PAGES = [  # (file, nav label, template)
    ("index.html", "Home", "index.html"),
    ("get-started.html", "Get started", "get-started.html"),
    ("science.html", "Science", "science.html"),
    ("model.html", "Model", "model.html"),
    ("contribute.html", "Contribute", "contribute.html"),
    ("about.html", "About & cite", "about.html"),
]

# old URLs kept alive
REDIRECTS = {
    "amrhybrid.html": "model.html",
    "firstrun2grids.html": "model.html#first-run",
}


def environment(root):
    common = Path(root) / "tools" / "common"
    env = Environment(loader=ChoiceLoader([PackageLoader("phare_site", "templates"), FileSystemLoader(common)]),
                      autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True)
    env.filters["num"] = lambda v: "–" if v is None else f"{v:,}"
    return env


def build(root, drafts=False):
    root = Path(root)
    c = content.load(root)
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
