#!/usr/bin/env bash
# Start the day's collection at the time it is meant to start.
#
# GitHub's scheduler is the one part of this pipeline that cannot be relied on: it delivered four of
# the last eight scheduled events for this repository, each three to five hours after its slot. Push
# events, on the same repository in the same week, started within seconds every time - all one
# hundred and thirty-three of them. So punctuality is bought with a push, and the schedule is left to
# do what it is good for, which is catching up afterwards.
#
# This writes one small stamp file and pushes it with [collect] in the message, which the pipeline
# reads as "collect now". It does nothing if the day's collection has already happened, or if a kick
# earlier today is still working, so running it twice, or on top of the scheduler, is harmless.
#
#   bash tools/kick.sh              collect if the day's collection is owed
#   bash tools/kick.sh --force      collect regardless
#   bash tools/kick.sh --dry-run    say what it would do, push nothing
#
# Exit 0 means a kick went out, 3 means none was owed, 1 means one was owed and could not be sent.
# A caller that cannot tell those apart reports success for a morning on which nothing happened,
# which is how 11 September went: the routine succeeded, no kick was pushed, and the collection
# waited four and a half hours for GitHub's own scheduler to turn up.
#
# The commit is assembled in a temporary index and pushed straight at origin/main, so it neither
# reads nor disturbs the working tree: safe to run from a clone that is mid-edit, and safe to run
# from a clone that is behind.
set -euo pipefail
cd "$(dirname "$0")/.."

force=""; dry=""
for a in "$@"; do case "$a" in --force) force=1 ;; --dry-run) dry=1 ;;
  *) echo "unknown option: $a" >&2; exit 2 ;; esac; done

git fetch --quiet origin main
now=$(date -u +%s)
owed_from=$(date -u -d 'today 05:00' +%s)

# The stamps as origin/main holds them, not as this clone happens to have them.
at() {
  local t; t=$(git show "origin/main:data/state/$1" 2>/dev/null) || { echo 0; return; }
  date -u -d "$t" +%s 2>/dev/null || echo 0
}
collected=$(at last-collect)
requested=$(at requested)

if [ -z "$force" ]; then
  if [ "$now" -lt "$owed_from" ]; then
    echo "nothing owed: the day's collection is not due until 05:00 UTC"; exit 3
  fi
  if [ "$collected" -ge "$owed_from" ]; then
    echo "nothing owed: collected $(( (now - collected) / 60 )) minutes ago"; exit 3
  fi
  # A kick that has already gone out today is still working; two collections would fight over the
  # same commit. Ninety minutes is longer than a full run has ever taken.
  if [ "$requested" -ge "$owed_from" ] && [ $((now - requested)) -lt 5400 ]; then
    echo "already kicked $(( (now - requested) / 60 )) minutes ago and still running"; exit 3
  fi
fi

stamp=$(date -u +%FT%TZ)
message="Collect $(date -u +%F) [collect]"
if [ -n "$dry" ]; then echo "would push: $message"; exit 0; fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
printf '%s\n' "$stamp" > "$tmp/requested"
blob=$(git hash-object -w "$tmp/requested")
export GIT_INDEX_FILE="$tmp/index"
git read-tree origin/main
git update-index --add --cacheinfo "100644,$blob,data/state/requested"
tree=$(git write-tree)
commit=$(git -c user.name="counterparty-bot" -c user.email="philsmith871010@gmail.com" \
  commit-tree "$tree" -p "$(git rev-parse origin/main)" -m "$message")

for wait in 2 4 8 16 0; do
  if git push --quiet origin "$commit:refs/heads/main"; then
    echo "kicked: $message ($commit)"; exit 0
  fi
  [ "$wait" -eq 0 ] && break
  echo "push failed, retrying in ${wait}s" >&2; sleep "$wait"
  git fetch --quiet origin main   # someone else pushed; rebuild on what is there now
  git read-tree origin/main
  git update-index --add --cacheinfo "100644,$blob,data/state/requested"
  tree=$(git write-tree)
  commit=$(git -c user.name="counterparty-bot" -c user.email="philsmith871010@gmail.com" \
    commit-tree "$tree" -p "$(git rev-parse origin/main)" -m "$message")
done
echo "could not push the kick" >&2; exit 1
