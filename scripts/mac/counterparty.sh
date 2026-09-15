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
# Everything goes to the log, because launchd has nowhere else to put it. A run started by hand
# printed nothing at all, though, which is indistinguishable from a hung one - so when a terminal
# is attached the log is mirrored to it as well.
if [ -t 1 ]; then exec > >(tee -a "$LOG") 2>&1; else exec >>"$LOG" 2>&1; fi
# One run at a time. Two sessions working the review queue at once answer the same items
# twice and can write over each other's answers, so take a lock for the whole run and release
# it however the run ends. mkdir is the atomic primitive here; macOS has no flock(1).
# Before working the queue by hand, check whether a scheduled run holds it:
#   ls -d ~/Counterparty/data/cache/run.lock 2>/dev/null && echo "a scheduled run is working the queue"
LOCK="$REPO/data/cache/run.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "==== $(date -u +%FT%TZ) skipped: another run holds $LOCK (delete it if no run is live)"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT INT TERM
echo "==== $(date -u +%FT%TZ) start"
# Generated artefacts: the runner's copy wins. history.parquet belongs here too - the build
# appends to it, it was left dirty on 9 September, and every run from the 10th died on the pull.
git checkout -- data/json data/history.parquet 2>/dev/null || true
# A dirty tree used to end the run right here, under set -e, taking the review queue and the
# headline judging with it - silently, for five days. A refused fast-forward now parks whatever is
# local and retries once, and says so in the log.
if ! git pull --ff-only; then
  echo "!! fast-forward refused; stashing local changes and retrying"
  git stash push --include-untracked -m "local-run $(date -u +%FT%TZ)" || true
  git pull --ff-only
fi
source .venv/bin/activate
# 1. collect from bank sites and the FCA NSM from this network (residential IP), extract, queue
echo "-- collecting Pillar 3 from bank sites and the FCA NSM"
python -m bankcredit.cli run pillar3 || true
# 1b. the sites that block scripts: browser headers first, then headless Chromium (playwright) if installed
echo "-- retrying the sites that block scripts"
python -m bankcredit.cli browser || true
# 2. work the review queue with Claude Code (subscription login, no API key)
if command -v claude >/dev/null 2>&1; then
  echo "-- working the review queue (this is the slow one)"
  claude -p "/counterparty-review" --allowedTools "Bash,Read,Write,Edit,Glob,Grep" --max-turns 80 || echo "claude review step failed"
fi
# 2b. judge the fortnight's headlines (subscription login, no API key); verdicts are applied by every pipeline run
if command -v claude >/dev/null 2>&1; then
  echo "-- judging the headlines"
  claude -p "/counterparty-news" --allowedTools "Bash,Read,Write,Edit,Glob,Grep" --max-turns 40 || echo "claude news step failed"
fi
# 2c. the written summary on each profile: only the names whose inputs have moved since it was
# written, or whose summary is over ninety days old, so most nights this is nothing at all
if command -v claude >/dev/null 2>&1; then
  if python -m bankcredit.cli summaries due | head -1 | grep -qv "^0 of"; then
    echo "-- writing the summaries that are owed"
    claude -p "/counterparty-summary" --allowedTools "Bash,Read,Write,Edit,Glob,Grep" --max-turns 60 || echo "claude summary step failed"
    python -m bankcredit.cli summaries check || echo "!! a summary failed its check; see above"
  fi
fi
# 3. load any answers and push the data; the GitHub pipeline rebuilds the site on push
python -m bankcredit.cli review ingest || true
python -m bankcredit.cli learn > /dev/null 2>&1 || true
# which sources have stopped working, and which never did; the report is committed and shown on Status
python -m bankcredit.cli health || true
# One push path for every runner: the same script the cloud routines call, which commits the
# answers and nothing else. data/review includes browser-links.json and news_verdicts.json.
echo "-- pushing the answers"
bash tools/push-data.sh "Local run $(date -u +%F): Pillar 3 collection and review" || true
# Then ask for the day's collection, if it is still owed. The marker used to go in the message
# above unconditionally, which now means collecting twice on any day the 05:10 kick already ran;
# kick.sh reads the stamps on origin/main and decides, so this is a no-op when there is nothing owed.
bash tools/kick.sh || true
echo "==== $(date -u +%FT%TZ) done"
