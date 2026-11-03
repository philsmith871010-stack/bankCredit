# Counterparty

Bank credit for UK local-authority treasury desks: who they can place money with, and for how long,
from regulatory filings, rating registers and market prices. A static site built by Python
from the data a daily GitHub Actions pipeline collects, published on GitHub Pages at
https://philsmith871010-stack.github.io/bankCredit/. The product is to be renamed PWLBinvest.

## Running it

- `bash tools/dev.sh`: build, serve http://localhost:8000/bankCredit/, rebuild on every save and
  reload the browser. `.claude/launch.json` starts the same server for the desktop app's preview.
  Details in docs/local-dev.md.
- Tests: `python -m pytest -q --ignore=tests/test_site_browser.py` for the unit tests;
  `python tools/dev.py --once` and then `python -m pytest -q tests/test_site_browser.py` for the
  browser tests, which need a build in site/.

## Where things are

- `bankcredit/site/build.py`, `components.py` and `assets/`: the site, with its pages, shell, CSS and JS.
- `bankcredit/export.py`: the data the pages read (data/json), the scores and the score history.
- `bankcredit/adapters/`: the collectors. `bankcredit/adapters/pillar3_locators.py` says where each bank publishes.
- `.github/workflows/pipeline.yml`: the daily pipeline. Every push to main rebuilds and deploys the site.
- `docs/`: decisions and method, including docs/pathways.md for the site's shape and docs/local-run.md for the Mac's weekly job.

## Rules

- Never commit `data/json`, `data/history.parquet` or `site/` from a local build: the pipeline owns them.
  The dev server builds from a copy under `.dev/`, so it never touches them.
- Public pages never name a rating agency against a rating. The agencies' own ratings appear only
  through `members/ratings.json`, which the build writes when `COUNTERPARTY_ATTRIBUTED` is set.
  See docs/attributed-ratings.md.
- Links and fetches stay relative to the page, resolved through `data-root`, because the site
  lives under /bankCredit/. The dev server serves it there too, so a link that escapes 404s locally.
- Data answers, such as review-queue resolutions, are pushed with
  `tools/push-data.sh`, never with a broad `git add`.
- Every push to main deploys, so run the tests first.
