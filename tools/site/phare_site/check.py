"""Check the built site: links resolve, no dead placeholders, scripts only from allowed CDNs.

    python -m phare_site.check --root ../..

Exit code 1 if anything is wrong. External links are listed, not fetched.
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urlparse

ALLOWED_SCRIPT_HOSTS = {"cdnjs.cloudflare.com"}
SKIP_DIRS = {"tools", ".git", ".venv", "data", "content"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.scripts, self.ids = [], [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and "href" in a:
            self.links.append(a["href"])
        if tag in ("img", "video", "source") and "src" in a:
            self.links.append(a["src"])
        if tag == "link" and a.get("rel") in ("icon", "stylesheet") and "href" in a:
            self.links.append(a["href"])
        if tag == "script" and "src" in a:
            self.scripts.append(a["src"])


def pages(root):
    for p in sorted(root.rglob("*.html")):
        if not SKIP_DIRS & set(p.relative_to(root).parts):
            yield p


def check(root):
    root = Path(root).resolve()
    parsed = {}
    for p in pages(root):
        pg = Page()
        pg.feed(p.read_text())
        parsed[p] = pg
    errors, external = [], set()
    for p, pg in parsed.items():
        rel = p.relative_to(root)
        for href in pg.links:
            if href.strip() in ("", "#"):
                errors.append(f"{rel}: empty link href={href!r}")
                continue
            u = urlparse(href)
            if u.scheme in ("http", "https"):
                external.add(href)
                continue
            if u.scheme in ("mailto",):
                continue
            path, frag = urldefrag(href)
            target = (p.parent / path).resolve() if path else p
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                errors.append(f"{rel}: broken link {href}")
            elif frag and target.suffix == ".html":
                tp = parsed.get(target)
                if tp is not None and frag not in tp.ids:
                    errors.append(f"{rel}: missing anchor {href}")
        for src in pg.scripts:
            host = urlparse(src).netloc
            if host and host not in ALLOWED_SCRIPT_HOSTS:
                errors.append(f"{rel}: script from {host} (allowed: {', '.join(sorted(ALLOWED_SCRIPT_HOSTS))})")
        if re.search(r"polyfill\.io", p.read_text()):
            errors.append(f"{rel}: references polyfill.io")
    return errors, sorted(external), len(parsed)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    errors, external, n = check(args.root)
    for e in errors:
        print("ERROR", e)
    print(f"{n} pages checked, {len(errors)} errors, {len(external)} distinct external links (not fetched)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
