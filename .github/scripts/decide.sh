#!/usr/bin/env bash
# What this run should do, decided from the clock and from what the previous run left behind.
#
# GitHub does not deliver this repository's scheduled events on time, and drops most of them. Over
# two days, four of the eight expected pipeline events arrived, each between three and five hours
# after its slot; of fourteen expected headline events, four arrived. Push events, by contrast,
# start within seconds, every time. Nothing written in a workflow file can make that scheduler
# punctual, so the schedule is no longer treated as a clock. It is a supply of chances - one an
# hour through the working day - and this script decides, at the start of each of them, whether
# anything is still owed:
#
#   full   the day's collection has not happened yet, so run every adapter and publish
#   news   the collection is done, but the headlines are over an hour and a half old
#   build  a code push: rebuild and republish the site from the data already committed
#   skip   nothing owed; leave in a few seconds without touching the data or the site
#
# The consequence is that a slot arriving four hours late still does the day's work, a slot
# arriving after the work is done costs twenty seconds, and a slot that never arrives at all costs
# nothing, because the next one covers for it. Punctuality itself comes from outside: a kick that
# pushes at the appointed time (tools/kick.sh), which these slots exist to catch up behind.
set -euo pipefail

now=$(date -u +%s)
owed_from=$(date -u -d 'today 05:00' +%s)   # the day's collection is owed from 05:00 UTC
dow=$(date -u +%u)                          # 1-7, Monday first
hour=$((10#$(date -u +%H)))

# A stamp the last run committed, as a unix time; nothing yet, or anything unreadable, is 0.
stamp() { [ -f "data/state/$1" ] && date -u -d "$(cat "data/state/$1")" +%s 2>/dev/null || echo 0; }
collected=$(stamp last-collect)
headlined=$(stamp last-headlines)

mode=auto
case "${EVENT:-}" in
  push)
    # A code push republishes the site from committed data - unless the day's collection has not
    # happened yet, in which case it does that too. A push is the only event GitHub delivers
    # reliably: 151 of this pipeline's first 158 runs came from one, within seconds, against 7 of
    # the 45 scheduled events expected over the same three weekdays. So every push is a chance to
    # catch up, and the day's first push after 05:00 UTC collects. [collect] asks regardless, and
    # is what the kick pushes.
    #
    # This cannot loop: the workflow commits its data with GITHUB_TOKEN, and GitHub does not raise
    # workflow events for a push made with it.
    case "${MESSAGE:-}" in
      *"[collect]"*) mode=full ;;
      *) if [ "$now" -ge "$owed_from" ] && [ "$collected" -lt "$owed_from" ]; then mode=full; else mode=build; fi ;;
    esac ;;
  workflow_dispatch)
    mode="${WANTED:-auto}" ;;
esac

if [ "$mode" = auto ]; then
  if [ "$now" -ge "$owed_from" ] && [ "$collected" -lt "$owed_from" ]; then
    mode=full
  elif [ "$dow" -le 5 ] && [ "$hour" -ge 6 ] && [ "$hour" -le 19 ] \
       && [ $((now - headlined)) -ge 5400 ]; then
    mode=news
  else
    mode=skip
  fi
fi

ago() { [ "$1" -eq 0 ] && echo never || echo "$(( (now - $1) / 3600 ))h ago"; }
echo "mode=$mode" >> "${GITHUB_OUTPUT:-/dev/stdout}"
{ echo "### $mode"
  echo ""
  echo "| | |"
  echo "|---|---|"
  echo "| event | ${EVENT:-none} |"
  echo "| now | $(date -u +%FT%TZ) |"
  echo "| last collection | $(ago "$collected") |"
  echo "| last headlines | $(ago "$headlined") |"
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
