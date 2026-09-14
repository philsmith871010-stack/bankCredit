#!/usr/bin/env bash
# Is the Mac job doing its job? Thirty seconds, once a week.
#
#   bash ~/Counterparty/scripts/mac/check.sh
#
# The job runs itself, weekdays at 07:30, and says nothing when it works. That is the right
# behaviour and it is also how one dirty file stopped it for five days without anyone noticing.
# This answers the four questions worth asking, and says plainly what to do about each.
#
# No `set -e`: every check should report, not stop the report at the first bad one.
set -uo pipefail
REPO="${COUNTERPARTY_REPO:-$HOME/Counterparty}"
cd "$REPO" 2>/dev/null || { echo "no clone at $REPO"; exit 1; }
LOG="data/cache/local-run.log"
ok=0

say() { printf '%-22s %s\n' "$1" "$2"; }
bad() { printf '%-22s !! %s\n' "$1" "$2"; ok=1; }

# 1. Is it scheduled at all? An unloaded job is silent in exactly the same way as a working one.
if ! command -v launchctl >/dev/null 2>&1; then
  say "scheduled" "not a Mac; skipping"
elif launchctl list 2>/dev/null | grep -q com.pwlbtoday.counterparty; then
  say "scheduled" "loaded, weekdays 07:30 local"
else
  bad "scheduled" "NOT loaded. Fix: launchctl load ~/Library/LaunchAgents/com.pwlbtoday.counterparty.plist"
fi

# 2. Did it finish? A run that started and never finished is the interesting case.
if [ -f "$LOG" ]; then
  last=$(grep '^==== ' "$LOG" | tail -1)
  case "$last" in
    *done) say "last run" "${last#==== }" ;;
    "")    bad "last run" "nothing in the log yet" ;;
    *)     bad "last run" "${last#==== } - started and did not finish" ;;
  esac
  # Anything the run itself flagged. The script prints these with a !! prefix.
  flags=$(grep -c '^!!' "$LOG" 2>/dev/null || echo 0)
  [ "$flags" -gt 0 ] && bad "warnings in log" "$flags - see: grep '^!!' $LOG | tail"
else
  bad "last run" "no log at $LOG"
fi

# 3. Is a run stuck? The lock is taken for the whole run and released however it ends.
if [ -d data/cache/run.lock ] && ! pgrep -f counterparty.sh >/dev/null 2>&1; then
  bad "lock" "held with no run alive. Fix: rmdir data/cache/run.lock"
fi

# 4. Did the work reach GitHub, and is the published data current? This is the one that matters:
#    a run that collects and cannot push has achieved nothing.
git fetch --quiet origin main 2>/dev/null
pushed=$(git log -1 --format='%cd  %s' --date=short origin/main --grep='^Local run' 2>/dev/null)
[ -n "$pushed" ] && say "last push from here" "$pushed" || bad "last push from here" "none found on origin/main"
collected=$(git show origin/main:data/state/last-collect 2>/dev/null | tr -d '\n')
[ -n "$collected" ] && say "site data collected" "$collected" || bad "site data collected" "no stamp on origin/main"
ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
[ "${ahead:-0}" -gt 0 ] && bad "unpushed commits" "$ahead here that origin does not have. Fix: git push"

[ "$ok" -eq 0 ] && echo && echo "All well." || { echo; echo "Something above needs a look."; }
exit "$ok"
