"""What a run decides to do when it starts.

The scheduler is the one part of the pipeline nobody here controls: GitHub delivered four of the
last eight scheduled events for this repository, three to five hours late apiece, and dropped the
rest. The workflow's answer is to stop trusting the clock it is given and ask, at the start of every
run, what is still owed - so a late slot does the day's work, an unnecessary one leaves in seconds,
and a dropped one costs nothing. That decision is the thing to test, because a mistake in it means
either no collection at all or the same collection running twice over the top of itself.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "decide.sh"
KICK = Path(__file__).resolve().parent.parent / "tools" / "kick.sh"


def decide(tmp_path, *, collect=None, headlines=None, when=None, **env) -> str:
    """Run the guard against a state directory built for the moment described."""
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    for name, at in (("last-collect", collect), ("last-headlines", headlines)):
        if at is not None:
            (state / name).write_text(at.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(at, datetime) else at)
    out = tmp_path / "out"
    run = subprocess.run(["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(out), **env})
    assert run.returncode == 0, run.stderr
    return out.read_text().strip().removeprefix("mode=")


def at(hour: int, *, days: int = 0) -> datetime:
    """A moment today (or `days` back) at a whole hour, UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days)


# ---- the day's collection --------------------------------------------------------------------
def test_a_slot_that_arrives_before_anything_has_run_today_collects(tmp_path):
    assert decide(tmp_path, collect=at(6, days=1), EVENT="schedule") == "full"


def test_a_slot_arriving_hours_late_still_collects(tmp_path):
    """The whole point: 05:17 delivered at 09:34 must do the work, not decide it has missed it."""
    assert decide(tmp_path, collect=at(5, days=2), EVENT="schedule") == "full"


def test_a_second_slot_the_same_day_does_not_collect_again(tmp_path):
    mode = decide(tmp_path, collect=datetime.now(timezone.utc), headlines=datetime.now(timezone.utc),
                  EVENT="schedule")
    assert mode == "skip"


def test_a_repository_with_no_state_at_all_collects(tmp_path):
    assert decide(tmp_path, EVENT="schedule") == "full"


def test_an_unreadable_stamp_is_treated_as_never(tmp_path):
    """A truncated or half-written stamp must fail towards collecting, never towards silence."""
    assert decide(tmp_path, collect="not a date", EVENT="schedule") == "full"


# ---- headlines -------------------------------------------------------------------------------
def test_headlines_refresh_once_the_collection_is_done_and_they_are_stale(tmp_path):
    now = datetime.now(timezone.utc)
    if not (1 <= now.isoweekday() <= 5 and 6 <= now.hour <= 19):
        pytest.skip("headline hours are weekdays 06:00-19:00 UTC")
    assert decide(tmp_path, collect=now, headlines=now - timedelta(hours=3), EVENT="schedule") == "news"


def test_fresh_headlines_are_left_alone(tmp_path):
    now = datetime.now(timezone.utc)
    assert decide(tmp_path, collect=now, headlines=now - timedelta(minutes=20), EVENT="schedule") == "skip"


# ---- pushes ----------------------------------------------------------------------------------
def test_a_code_push_rebuilds_the_site_once_the_day_is_collected(tmp_path):
    now = datetime.now(timezone.utc)
    assert decide(tmp_path, collect=now, headlines=now,
                  EVENT="push", MESSAGE="Tidy the glossary wording") == "build"


def test_a_code_push_collects_when_the_day_still_owes_one(tmp_path):
    """A push is the only event GitHub delivers reliably, so it is also the catch-up.

    On 10 September 2026 every other route failed at once: GitHub dropped all fifteen slots, the
    routine that exists to be punctual could not push, and the Mac was asleep. Twenty pushes went
    in that day and not one of them collected, because a push only rebuilt.
    """
    assert decide(tmp_path, collect=at(8, days=1), EVENT="push",
                  MESSAGE="Tidy the glossary wording") == "full"


def test_a_push_on_a_repository_that_has_never_collected_collects(tmp_path):
    assert decide(tmp_path, EVENT="push", MESSAGE="Tidy the glossary wording") == "full"


def test_a_push_carrying_the_marker_collects_whatever_the_clock_says(tmp_path):
    """How the on-time kick asks for the day's collection, and how a person asks by hand."""
    now = datetime.now(timezone.utc)
    assert decide(tmp_path, collect=now, headlines=now,
                  EVENT="push", MESSAGE="Collect 2026-09-09 [collect]") == "full"


def test_a_commit_message_cannot_reach_the_shell(tmp_path):
    nasty = 'fix; touch /tmp/pwned; echo "$(id)" `whoami` [collect]'
    assert decide(tmp_path, EVENT="push", MESSAGE=nasty) == "full"
    assert not Path("/tmp/pwned").exists()


# ---- asking by hand --------------------------------------------------------------------------
@pytest.mark.parametrize("wanted", ["full", "news", "build"])
def test_a_dispatch_can_force_a_mode(tmp_path, wanted):
    now = datetime.now(timezone.utc)
    assert decide(tmp_path, collect=now, headlines=now,
                  EVENT="workflow_dispatch", WANTED=wanted) == wanted


def test_a_dispatch_left_on_auto_decides_for_itself(tmp_path):
    assert decide(tmp_path, collect=at(6, days=1), EVENT="workflow_dispatch", WANTED="auto") == "full"


# ---- the kick ---------------------------------------------------------------------------------
def test_the_kick_and_the_guard_agree_on_when_the_day_starts():
    """Two scripts, one rule: the day's collection is owed from 05:00 UTC. If they drift apart the
    kick pushes work the guard then declines to do, or the other way about."""
    for path in (SCRIPT, KICK):
        assert "date -u -d 'today 05:00' +%s" in path.read_text()


def test_the_kick_never_touches_the_working_tree():
    """It runs on a clone that may be mid-edit, so the commit is built in a temporary index and
    pushed straight at origin/main. A stray `git add` or `git checkout` here would eat real work."""
    text = KICK.read_text()
    assert "GIT_INDEX_FILE" in text and "commit-tree" in text
    for forbidden in ("git add", "git checkout", "git commit -m", "git reset", "git stash"):
        assert forbidden not in text, f"kick.sh uses {forbidden!r}"


def test_a_kick_that_went_nowhere_does_not_look_like_one_that_went_out():
    """On 11 September the 05:10 routine reported success and no kick was pushed, so the day's
    collection waited four and a half hours for GitHub's own scheduler. A caller that reads only
    an exit code has to be able to tell a kick from a decline: 0 sent, 3 none owed, 1 could not."""
    text = KICK.read_text()
    assert "exit 3" in text, "a decline has its own code"
    declines = [ln for ln in text.splitlines() if "nothing owed" in ln or "already kicked" in ln]
    assert declines, "the decline paths are still there"
    for line in declines:
        assert "exit 3" in line, f"a decline still exits 0: {line.strip()}"
    assert 'echo "kicked:' in text and "exit 0" in text, "and a kick still exits 0"


def test_the_kick_declines_when_the_day_is_already_collected(tmp_path):
    """Run for real against a throwaway repository, so the decision is tested and not the text."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", origin], check=True)
    subprocess.run(["git", "clone", "--quiet", str(origin), str(clone)], check=True)
    state = clone / "data" / "state"
    state.mkdir(parents=True)
    (state / "last-collect").write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    tools = clone / "tools"
    tools.mkdir()
    (tools / "kick.sh").write_text(KICK.read_text())
    git = ["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "--quiet", "-m", "state"], check=True)
    subprocess.run(git + ["push", "--quiet", "origin", "main"], check=True)
    done = subprocess.run(["bash", str(tools / "kick.sh"), "--dry-run"],
                          capture_output=True, text=True)
    assert done.returncode == 3, done.stdout + done.stderr
    assert "nothing owed" in done.stdout
