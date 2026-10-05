from pathlib import Path

import pytest

from phare_site import build, check, content

ROOT = Path(__file__).resolve().parents[3]


def page(tmp_path, name, body):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"<!doctype html><html><body>{body}</body></html>")
    return p


def errors(tmp_path):
    return check.check(tmp_path)[0]


def test_clean_site_passes(tmp_path):
    page(tmp_path, "index.html", '<a href="b.html#x">b</a><a href="https://example.org">ext</a><a href="mailto:a@b.c">m</a>')
    page(tmp_path, "b.html", '<h2 id="x">x</h2>')
    assert errors(tmp_path) == []


@pytest.mark.parametrize("body,expected", [
    ('<a href="">x</a>', "empty link"),
    ('<a href="#">x</a>', "empty link"),
    ('<a href="missing.html">x</a>', "broken link"),
    ('<a href="b.html#nope">x</a>', "missing anchor"),
    ('<img src="static/none.png">', "broken link"),
    ('<script src="https://polyfill.io/v3/polyfill.min.js"></script>', "script from polyfill.io"),
])
def test_faults_are_caught(tmp_path, body, expected):
    page(tmp_path, "index.html", body)
    page(tmp_path, "b.html", '<h2 id="x">x</h2>')
    errs = errors(tmp_path)
    assert any(expected in e for e in errs), errs


def test_directory_link_resolves_to_index(tmp_path):
    page(tmp_path, "index.html", '<a href="reports/">r</a>')
    page(tmp_path, "reports/index.html", "")
    assert errors(tmp_path) == []


def test_real_content_loads_and_counts_pending_validation():
    c = content.load(ROOT)
    assert c["team"]["core"] and c["publications"]["cite_bibtex"].startswith("@article")
    assert content.validate_markers(c) >= 1


def test_build_is_deterministic(tmp_path, monkeypatch):
    first, _ = build.build(ROOT)
    a = {f: (ROOT / f).read_text() for f in first}
    build.build(ROOT)
    assert all((ROOT / f).read_text() == a[f] for f in first)
