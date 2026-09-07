#!/bin/zsh
# Local Counterparty run for the maintainer's Mac. No API key: extraction is rules-based,
# and the review step runs Claude Code under the subscription login.
#
# Install once:
#   git clone https://github.com/philsmith871010-stack/bankCredit ~/Counterparty
#   cd ~/Counterparty && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   npm install -g @anthropic-ai/claude-code && claude login
#   cp scripts/mac/com.pwlbtoday.counterparty.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.pwlbtoday.counterparty.plist
set -euo pipefail
REPO="${COUNTERPARTY_REPO:-$HOME/Counterparty}"
LOG="$REPO/data/cache/local-run.log"
cd "$REPO"
mkdir -p data/cache
exec >>"$LOG" 2>&1
echo "==== $(date -u +%FT%TZ) start"
git pull --ff-only
source .venv/bin/activate
# 1. collect from bank sites and the FCA NSM from this network (residential IP), extract, queue
python -m bankcredit.cli run pillar3 || true
# 1b. the sites that block scripts: browser headers first, then headless Chromium (playwright) if installed
python -m bankcredit.cli browser || true
# 2. work the review queue with Claude Code (subscription login, no API key)
if command -v claude >/dev/null 2>&1; then
  claude -p "/counterparty-review" --allowedTools "Bash,Read,Write,Edit,Glob,Grep" --max-turns 80 || echo "claude review step failed"
fi
# 3. load any answers and push the data; the GitHub pipeline rebuilds the site on push
python -m bankcredit.cli review ingest || true
python -m bankcredit.cli learn > /dev/null 2>&1 || true
git add data/facts.parquet data/documents.parquet data/runs.parquet data/review 2>/dev/null || true   # data/review includes browser-links.json
if ! git diff --cached --quiet; then
  # [collect] makes the push run the full daily collection too, a backstop for GitHub's schedule
  git commit -m "Local run $(date -u +%F): Pillar 3 collection and review [collect]"
  git push
fi
echo "==== $(date -u +%FT%TZ) done"
