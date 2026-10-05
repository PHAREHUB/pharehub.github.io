# pharehub.github.io

The PHARE website, served by GitHub Pages at https://pharehub.github.io/.

The HTML pages at the root and in `reports/` are generated: edit the sources, not the pages.

| Edit this | to change |
|---|---|
| `content/*.toml` | team, publications, news, capabilities, roadmap, gallery, site-wide facts |
| `content/model_body.html` | the physics text of `model.html` |
| `tools/site/phare_site/templates/` | page layouts of the site |
| `tools/report/phare_report/templates/` | page layouts of the activity reports |
| `tools/common/phare.css` | colours, fonts and components shared by the site and the reports |
| `static/` | images and video |

## Build locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r tools/report/requirements.txt
cd tools/site
../../.venv/bin/python -m phare_site.fetch --root ../..          # refresh good first issues (network)
../../.venv/bin/python -m phare_site.build --root ../.. --drafts # --drafts shows "to validate" badges
../../.venv/bin/python -m phare_site.check --root ../..          # links, anchors, allowed scripts
../../.venv/bin/python -m pytest -q tests
```

Activity reports: see `tools/report/` (`collect` fetches a week into `data/weekly/`, `render` writes `reports/`).

## Automation

`.github/workflows/activity-report.yml` runs every Monday 06:00 UTC: it collects last week's activity,
refreshes the good-first-issue list, rebuilds the reports and the site, and commits the result.
It also rebuilds the site when `content/`, `static/` or `tools/` change on `main`.
