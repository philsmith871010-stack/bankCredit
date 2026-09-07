# Running Counterparty on your Mac (no API key)

Two things run without any Anthropic API key:

1. **The pipeline on GitHub Actions** collects Pillar 3 PDFs (bank sites plus the
   FCA National Storage Mechanism), reads the KM1 key-metrics template with fixed
   rules (`bankcredit/extract/km1.py`), validates every figure against the
   template's own arithmetic, and publishes the site. Figures that pass with
   warnings are shown as *unverified*; failures go to `data/review/queue.json`.
2. **A local run on your Mac** resolves the queue and reaches the sites that block
   scripts. The reading is done by Claude Code under your subscription login
   (`claude login`), driven by the repository skill
   `.claude/skills/counterparty-review/SKILL.md`. No key is stored anywhere.

## Setup (once)

```bash
git clone https://github.com/philsmith871010-stack/bankCredit ~/Counterparty
cd ~/Counterparty
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm install -g @anthropic-ai/claude-code && claude login      # subscription login, no key
.venv/bin/pip install playwright && .venv/bin/playwright install chromium   # headless browser for bot-blocked sites
brew install tesseract                                          # OCR for the few image-only PDFs
cp scripts/mac/com.pwlbtoday.counterparty.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pwlbtoday.counterparty.plist
```

The job runs weekdays at 07:30 local time (edit the plist to change it). Run it
by hand any time with `scripts/mac/counterparty.sh`; the log is
`data/cache/local-run.log`.

## What a run does

| Step | Command | Notes |
|---|---|---|
| Collect | `python -m bankcredit.cli run pillar3` | Same collector the pipeline runs, from your home connection |
| Browser sites | `python -m bankcredit.cli browser` | Bot-blocked sites: browser headers, then headless Chromium; reports what is still blocked |
| Review | `claude -p "/counterparty-review"` | Opens each queued PDF page, writes `data/review/resolved/<id>.json` |
| Load | `python -m bankcredit.cli review ingest` | Answers become facts with method `pdf_manual` |
| Publish | `git push` | The pipeline rebuilds and deploys the site |

## Doing it interactively instead

Open Claude Code in the repository and type `/counterparty-review`. The skill
walks the queue with you and stops when it is empty. For a single PDF you
downloaded yourself:

```bash
python -m bankcredit.cli pdf lloyds-banking-group ~/Downloads/lbg-pillar-3-h1-2026.pdf https://www.lloydsbankinggroup.com/...
```

## Firms that need the browser

`kind="browser"` in `bankcredit/adapters/pillar3_locators.py`: Lloyds Banking
Group, Lloyds Bank, Bank of Scotland, Investec, Handelsbanken plc, the small
societies, the Gulf and Singapore banks and the US majors. The `browser` command
clears most of them from a home connection; the ones it reports as blocked are
behind Cloudflare or Akamai challenges and need the Claude-in-Chrome extension,
which the review skill drives. Everything else is collected by script; Paragon
and Close Brothers come from the FCA NSM.
