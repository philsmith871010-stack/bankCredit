#!/bin/zsh
# The weekly Counterparty run for the maintainer's Mac, built to survive the laptop being off.
#
# launchd calls this every hour the Mac is awake, and once at login. It does nothing unless the
# last completed run is more than six days old, so the work happens about once a week, on whatever
# hour the laptop happens to be on: a laptop that was closed on the appointed morning gets its run
# the next time it is open, rather than waiting for next week. A failed run is retried after six
# hours, not every hour, and a lock left behind by a run the laptop was shut on is cleared.
#
# The run itself is scripts/mac/counterparty.sh: Pillar 3 from the bank sites that refuse a
# data-centre address, on this home connection; the browser-only sites; the review queue and the
# headlines under Claude Code; the summaries that are owed; then the push. The daily collection of
# ratings, prices, CDS and headlines does not depend on this job at all. It runs in the cloud.
#
# Install once:
#   cp ~/Counterparty/scripts/mac/com.pwlbtoday.counterparty-weekly.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.pwlbtoday.counterparty-weekly.plist
# Run it now, whatever the stamp says:
#   zsh ~/Counterparty/scripts/mac/weekly.sh --now
set -uo pipefail
REPO="${COUNTERPARTY_REPO:-$HOME/Counterparty}"
CACHE="$REPO/data/cache"
LOG="$CACHE/local-run.log"
STAMP="$CACHE/last-weekly"             # when the last run finished, epoch seconds
ATTEMPT="$CACHE/last-weekly-attempt"   # when the last run started
PERIOD=$((6 * 24 * 3600))              # six days, so the same weekday a week on is never "an hour too early"
RETRY=$((6 * 3600))                    # after a failure, wait this long before trying again
STALE_LOCK=$((6 * 3600))               # a lock older than this was left by a run the laptop was shut on
mkdir -p "$CACHE"
now=$(date +%s)
force=""
[ "${1:-}" = "--now" ] && force=1

if [ -z "$force" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  [ $((now - last)) -lt "$PERIOD" ] && exit 0
  tried=$(cat "$ATTEMPT" 2>/dev/null || echo 0)
  [ $((now - tried)) -lt "$RETRY" ] && exit 0
  # No network (the lid just opened, a train): not a failure, just not now. Next hour.
  curl -sS --max-time 10 -o /dev/null https://api.github.com/ 2>/dev/null || exit 0
fi

# A lock with no run alive and older than six hours: the laptop was closed on a run. Clear it,
# or every run from now on exits in a second saying another run holds it, which is how the
# daily job can stop for good without a word.
LOCK="$CACHE/run.lock"
if [ -d "$LOCK" ] && ! pgrep -f counterparty.sh >/dev/null 2>&1; then
  if [ $((now - $(stat -f %m "$LOCK"))) -gt "$STALE_LOCK" ]; then
    rmdir "$LOCK" && echo "==== $(date -u +%FT%TZ) weekly: cleared a lock left by a run that never finished" >> "$LOG"
  fi
fi

echo "$now" > "$ATTEMPT"
# caffeinate keeps the Mac from idling to sleep for the hour or so the run takes.
if caffeinate -i /bin/zsh "$REPO/scripts/mac/counterparty.sh"; then
  date +%s > "$STAMP"
else
  echo "==== $(date -u +%FT%TZ) weekly: the run failed; next try in six hours (see above)" >> "$LOG"
  exit 1
fi
