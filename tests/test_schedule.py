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
PUSH = Path(__file__).resolve().parent.parent / "tools" / "push-data.sh"


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
    kick pushes work the guard then declines to do, or the other way about. They no longer share a
    line of shell, because the kick also runs on a Mac and BSD date has no -d."""
    for path in (SCRIPT, KICK):
        text = path.read_text()
        assert "05:00" in text, f"{path.name} does not name the hour the day starts"
        for wrong in ("04:00", "06:00", "00:00"):
            assert f"'today {wrong}'" not in text and f"T{wrong}:00Z" not in text, \
                f"{path.name} uses {wrong}, not 05:00"


def test_the_kick_reads_a_timestamp_on_a_mac_as_well_as_a_runner():
    """date -u -d is a GNU extension. On the Mac it printed "date: illegal option -- d" and, under
    set -e, ended there, so the kick has never once gone out from a Mac."""
    text = KICK.read_text()
    assert "date -u -j -f" in text, "no BSD fallback for reading a timestamp"
    assert "epoch()" in text, "the two forms are behind one helper"
    bare = [ln for ln in text.splitlines()
            if "date -u -d" in ln and "epoch()" not in ln and not ln.strip().startswith("#")]
    assert len(bare) == 1, f"GNU-only date calls outside the helper: {bare}"


def test_the_push_script_shows_what_it_staged_with_a_command_that_exists(tmp_path):
    """`git status --cached` is not a thing. It printed a usage message, and under pipefail that
    ended push-data.sh before the commit and the push: every run said done and pushed nothing.

    Run for real against a throwaway repository, because the point is that the command works, not
    that it is spelled some particular way."""
    import subprocess
    text = PUSH.read_text()
    assert "set -euo pipefail" in text, "which is why an invalid command there is fatal"
    shows = [ln.strip() for ln in text.splitlines()
             if ln.strip().startswith("git ") and "sed 's/^/  /'" in ln]
    assert len(shows) == 1, f"expected one line that lists what was staged, got {shows}"
    repo = tmp_path / "r"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(repo)], check=True)
    (repo / "a.txt").write_text("one\n")
    subprocess.run(git + ["add", "a.txt"], check=True)
    done = subprocess.run(["bash", "-c", f"cd {repo} && set -euo pipefail && {shows[0]}"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "a.txt" in done.stdout, done.stdout


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


# ---- whether the day's collection arrived, said on the page ------------------------------------
def punct(started, generated, finished=None, source="esma"):
    """Render the Status page's punctuality line from a run log, the way the page does.

    Not from data/state/last-collect: the workflow writes that after the site is built, so reading
    it reported the previous run and contradicted the table underneath."""
    from bankcredit.site import build
    runs = [] if started is None else [
        {"source": source, "status": "ok", "rows": 1,
         "started": started, "finished": finished or started, "message": ""}]
    return build.punctuality({"runs": runs}, generated)


def test_a_collection_on_time_reads_as_a_quiet_line():
    out = punct("2026-09-14T05:20:00", "2026-09-14T06:00:00", finished="2026-09-14T05:34:00")
    assert "punct good" in out and "started 05:20" in out and "finished 05:34" in out
    assert "20 minutes" in out


def test_a_collection_hours_late_says_so_and_says_why():
    """Eight mornings running, the kick did not fire and the day waited for GitHub. Nobody saw it,
    because the only place it was said was a routine's chat reply."""
    out = punct("2026-09-14T10:39:00", "2026-09-14T11:30:00", finished="2026-09-14T10:50:00")
    assert "punct warn" in out
    assert "5h 39m" in out, out
    assert "morning kick" in out


def test_a_day_with_no_collection_is_not_a_quiet_line():
    out = punct("2026-09-12T09:34:00", "2026-09-14T11:30:00")
    assert "punct bad" in out and "No collection today" in out and "2 days ago" in out


def test_no_collection_in_the_log_says_nothing_can_be_assumed_current():
    out = punct(None, "2026-09-14T11:30:00")
    assert "punct bad" in out and "No collection recorded" in out


def test_the_line_describes_the_run_that_built_the_page(tmp_path):
    """The bug this replaced: the page was built at 11:59 by a collection that began at 11:46, and
    the line reported 10:50, because the stamp it read is written after the build."""
    from bankcredit.site import build
    runs = [{"source": "esma", "status": "ok", "rows": 1, "message": "",
             "started": "2026-09-14T10:37:40", "finished": "2026-09-14T10:39:36"},
            {"source": "esma", "status": "ok", "rows": 1, "message": "",
             "started": "2026-09-14T11:46:33", "finished": "2026-09-14T11:48:30"}]
    out = build.punctuality({"runs": runs}, "2026-09-14T11:59:00Z")
    assert "started 11:46" in out and "finished 11:48" in out, out
    assert "10:37" not in out and "10:39" not in out


def test_a_news_only_run_is_not_mistaken_for_the_day_s_collection():
    """Only the full collection runs esma. A headline refresh at 14:00 must not read as a
    collection that was nine hours late."""
    out = punct("2026-09-14T14:00:00", "2026-09-14T14:10:00", source="events")
    assert "No collection recorded" in out


# ---- the Mac job survives a dirty working tree --------------------------------------------------
MAC = Path(__file__).resolve().parent.parent / "scripts" / "mac" / "counterparty.sh"


def test_a_generated_file_left_dirty_cannot_end_the_local_run():
    """What actually happened: the build appends to data/history.parquet, it was left modified on
    9 September, and from the 10th every run died on `git pull --ff-only` under set -e - taking the
    review queue and the headline judging with it, silently, for five days."""
    text = MAC.read_text()
    assert "set -euo pipefail" in text, "the script does stop on error, which is why this matters"
    assert "data/history.parquet" in text, "the generated table is discarded before the pull"
    pull = [ln for ln in text.splitlines() if "git pull --ff-only" in ln]
    assert pull, "the script still pulls"
    assert any("if ! git pull --ff-only" in ln for ln in pull), \
        "a refused fast-forward must be caught, not left to end the run"
    assert "git stash push" in text, "and whatever is local is parked rather than discarded"


def test_the_local_run_never_discards_work_to_get_its_pull():
    """Stash, never reset or clean: a run that eats the maintainer's uncommitted work to unblock
    itself is worse than one that stops."""
    text = MAC.read_text()
    for forbidden in ("git reset --hard", "git clean", "git checkout -- .", "git checkout ."):
        assert forbidden not in text, f"the local run uses {forbidden!r}"


def test_a_run_started_by_hand_is_not_silent():
    """It sent everything to the log, so a manual run printed nothing at all and could not be told
    from a hung one. launchd still has nowhere but the log; a terminal gets both."""
    text = MAC.read_text()
    assert "[ -t 1 ]" in text, "the script does not notice whether a terminal is attached"
    assert 'tee -a "$LOG"' in text, "a terminal should see the log as it is written"
    assert 'exec >>"$LOG" 2>&1' in text, "and launchd should still get the plain redirect"
    steps = [ln for ln in text.splitlines() if ln.strip().startswith('echo "-- ')]
    assert len(steps) >= 4, f"the slow steps should say what they are, found {len(steps)}"


def _push_repo(tmp_path):
    """A bare origin, a clone of it wired to push, and a second clone to play the other runner.

    push-data.sh works on the repository it lives in, so the pieces it needs are copied into the
    clone: the point is to watch the real script make real commits against a real remote.
    """
    import pandas as pd
    origin, clone, other = tmp_path / "origin.git", tmp_path / "clone", tmp_path / "other"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(origin)], check=True)
    cfg = ["-c", "user.name=t", "-c", "user.email=t@t"]
    root = Path(__file__).resolve().parent.parent

    def git(where, *args, **kw):
        return subprocess.run(["git", "-C", str(where), *cfg, *args],
                              capture_output=True, text=True, **kw)

    subprocess.run(["git", "clone", "--quiet", str(origin), str(clone)], check=True)
    (clone / "data" / "review").mkdir(parents=True)
    # Every path the script stages has to exist: one `git add` with a missing pathspec adds nothing.
    for name in ("facts", "documents", "runs", "events"):
        rows(f"{name}-base").to_parquet(clone / "data" / f"{name}.parquet", index=False)
    (clone / "data" / "review" / "queue.json").write_text("[]\n")
    (clone / "tools").mkdir()
    (clone / "tools" / "push-data.sh").write_text(PUSH.read_text())
    (clone / "tools" / "merge-data.py").write_text((root / "tools" / "merge-data.py").read_text())
    (clone / ".gitattributes").write_text((root / ".gitattributes").read_text())
    (clone / "bankcredit").mkdir()
    (clone / "bankcredit" / "__init__.py").write_text("")
    (clone / "bankcredit" / "store.py").write_text((root / "bankcredit" / "store.py").read_text())
    for where in (clone,):
        git(where, "config", "user.name", "t", check=True)
        git(where, "config", "user.email", "t@t", check=True)
    git(clone, "add", "-A", check=True)
    git(clone, "commit", "--quiet", "-m", "base", check=True)
    git(clone, "push", "--quiet", "-u", "origin", "main", check=True)
    subprocess.run(["git", "clone", "--quiet", str(origin), str(other)], check=True)
    git(other, "config", "user.name", "t", check=True)
    git(other, "config", "user.email", "t@t", check=True)
    return clone, other, git


def rows(*ids):
    """A run log, the table both runners write to on any day they both run."""
    import pandas as pd
    return pd.DataFrame([{"run_id": i, "source": i, "status": "ok", "rows": 1, "message": "",
                          "started": "2026-09-14T00:00:00", "finished": "2026-09-14T00:01:00"}
                         for i in ids])


def run_push(clone, message):
    return subprocess.run(["bash", str(clone / "tools" / "push-data.sh"), message],
                          capture_output=True, text=True)


def test_the_push_script_keeps_what_both_runs_wrote(tmp_path):
    """The 14 September case, end to end: the pipeline rewrote the run log while a local run was
    collecting, and both had rows the other did not. It has to merge and go out unattended."""
    clone, other, git = _push_repo(tmp_path)
    rows("runs-base", "cloud").to_parquet(other / "data" / "runs.parquet", index=False)
    git(other, "commit", "--quiet", "-am", "Pipeline data", check=True)
    git(other, "push", "--quiet", check=True)

    rows("runs-base", "local").to_parquet(clone / "data" / "runs.parquet", index=False)
    done = run_push(clone, "Local run: answers")

    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    git(other, "pull", "--quiet", check=True)
    import pandas as pd
    got = set(pd.read_parquet(other / "data" / "runs.parquet")["run_id"])
    assert got == {"runs-base", "cloud", "local"}, got


def test_the_push_script_commits_before_it_pulls(tmp_path):
    """The Mac run of 14 September ended with six answer files staged and nothing said. The pull
    is what refuses, and a pull that refuses with the work merely staged loses the run. The merge
    driver settles the ordinary collision now, so this is the day it cannot: commit first and the
    work survives the refusal either way."""
    clone, other, git = _push_repo(tmp_path)
    (clone / "tools" / "merge-data.py").write_text(
        'import subprocess, sys\n'
        'if "--install" in sys.argv:\n'
        '    subprocess.run(["git", "config", "merge.counterparty.driver",\n'
        '                    "python3 " + __file__ + " %O %A %B %P"])\n'
        '    raise SystemExit(0)\n'
        'raise SystemExit(1)\n')
    git(clone, "commit", "--quiet", "-am", "a driver that cannot", check=True)
    git(clone, "push", "--quiet", check=True)
    git(other, "pull", "--quiet", check=True)
    rows("runs-base", "cloud").to_parquet(other / "data" / "runs.parquet", index=False)
    git(other, "commit", "--quiet", "-am", "Pipeline data", check=True)
    git(other, "push", "--quiet", check=True)

    (clone / "data" / "facts.parquet").write_bytes(b"answers\n")
    rows("runs-base", "local").to_parquet(clone / "data" / "runs.parquet", index=False)
    done = run_push(clone, "Local run: answers")

    assert done.returncode == 1, f"a conflicted merge should not look like a success\n{done.stdout}"
    assert "committed locally and safe" in done.stderr, done.stderr
    log = git(clone, "log", "--format=%s", "-n", "3").stdout
    assert "Local run: answers" in log, f"the run's work was never committed:\n{log}"
    staged = git(clone, "diff", "--cached", "--name-only").stdout.split()
    assert "data/facts.parquet" not in staged, f"answers left staged and unpushed: {staged}"


def test_the_push_script_pushes_when_the_merge_goes_through(tmp_path):
    """The ordinary day: nothing upstream touches the answers, so they merge and go out."""
    clone, other, git = _push_repo(tmp_path)

    (other / "data" / "elsewhere.txt").write_text("unrelated\n")
    git(other, "add", "-A", check=True)
    git(other, "commit", "--quiet", "-m", "Pipeline data", check=True)
    git(other, "push", "--quiet", check=True)

    (clone / "data" / "facts.parquet").write_bytes(b"answers\n")
    done = run_push(clone, "Local run: answers")

    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "pushed: Local run: answers" in done.stdout, done.stdout
    assert "data/facts.parquet" in done.stdout, "it should say what it sent"
    git(other, "pull", "--quiet", check=True)
    assert (other / "data" / "facts.parquet").read_bytes() == b"answers\n"


def test_the_push_script_says_so_and_stops_when_there_is_nothing_to_send(tmp_path):
    """A run that found no new answers must not commit an empty change or fail the caller."""
    clone, _, git = _push_repo(tmp_path)
    done = run_push(clone, "Local run: answers")
    assert done.returncode == 0, done.stderr
    assert "nothing to push" in done.stdout, done.stdout
    assert "Local run" not in git(clone, "log", "--format=%s", "-n", "3").stdout
