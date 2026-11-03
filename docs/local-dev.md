# Developing the site locally

`bash tools/dev.sh` builds the site from the committed data, serves it at
<http://localhost:8000/bankCredit/>, rebuilds whenever you save a file and reloads the browser.

## Set up once, on the Mac

Use a clone of its own. `~/Counterparty` belongs to the weekly job, which pulls there and parks
anything uncommitted to make its pull, so work in progress does not belong in it.

```bash
git clone https://github.com/philsmith871010-stack/bankCredit ~/Code/bankCredit
cd ~/Code/bankCredit
bash tools/dev.sh --open
```

The first run creates `.venv` and installs the requirements, a minute or two. It then builds, about
forty seconds, and opens the site. After that, `bash tools/dev.sh` starts it in seconds, serving the
last build while it makes a fresh one.

## The loop

Save a file and the page reloads itself. What a save costs depends on what it touches:

| You edit | It rebuilds | About |
|---|---|---|
| `bankcredit/site/` (pages, shell, CSS, JS) | the pages | 5 seconds |
| any other `bankcredit/` module | the data export, then the pages | 40 seconds |
| `data/` (a `git pull` with the day's collection) | a fresh copy of the data, the export, the pages | 40 seconds |

Where the user-facing code lives:

- `bankcredit/site/build.py`: every page and panel, such as the landing page, the tool and its pathways, and the bank profiles.
- `bankcredit/site/components.py`: the shell (header, pathway sidebar) and shared pieces (rating chart, chips, tiles).
- `bankcredit/site/assets/`: `site.css` and `landing.css` for styles; `app.js`, `policy.js` and `compare.js` for behaviour.
- `bankcredit/export.py`: the data each page reads, written to `data/json` by the build.

A build that fails leaves the last good site up and puts the error in a red bar at the foot of
every page. The bar clears itself on the next good build. The terminal shows the same error.

Other options: `--port 8080` (or `PORT=8080`), `--open` to open the browser, and `--public` to build
the public view without the members file of agency ratings.

## With Claude Code

Open `~/Code/bankCredit` in the Claude Code desktop app. `.claude/launch.json` tells it how to start
the server, so asking to preview the site opens it in the app's browser pane, and Claude starts the
server itself after editing.

## The data

The server builds from its own copy of `data/` under `.dev/`, which git ignores. A build rewrites
`data/json` and appends to `data/history.parquet`, and both belong to the pipeline, so building
from a copy keeps them untouched: `git status` shows only your code. `git pull` brings the latest
collection, and the server notices and rebuilds.

Two things differ from the live site. Bond-yield moves are missing, because the quotes are fetched
afresh on every pipeline run and never committed; `.venv/bin/python -m bankcredit.cli run bonds`
fetches them, in about seven minutes. And if the repository's `COUNTERPARTY_OVERLAY` secret holds
private overlay weights, the live scores use them while yours use the published default; export
the same JSON in your shell to match.

## Tests

```bash
.venv/bin/pip install pytest playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest -q --ignore=tests/test_site_browser.py        # unit tests, about 30 seconds
.venv/bin/python tools/dev.py --once                                    # build into site/, about 40 seconds
.venv/bin/python -m pytest -q tests/test_site_browser.py                # browser tests, about 4 minutes
```

A few tests read live sources, such as the EBA data hub or the FDIC API, and can fail because of the
source rather than the code.

## Shipping a change

Every push to `main` rebuilds and deploys the live site, in about five minutes. Run the tests,
check that `git status` lists only the code you meant to change, then commit and push. For anything
you want to look at before it goes live, push a branch first and merge it into `main` when happy.
