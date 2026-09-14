"""Two runs that collected different banks must not cost one of them.

Every table here is written whole on each save, so git sees a rewritten blob and offers only to
keep one side. On 14 September that offer was real: a Mac run had six banks' Pillar 3 figures in
data/facts.parquet and the cloud pipeline's full collection an hour later had everything else. The
pipeline's own push answers the same question with `-X theirs`, which is to say it throws away
whatever a local run pushed while it was collecting, and says nothing.

The store has always known the right answer - union on the natural key - and these tests drive it
through real `git merge` on real repositories, because a merge driver that is never actually
invoked by git is a file full of good intentions.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
DRIVER = ROOT / "tools" / "merge-data.py"


def git(where, *args, check=True):
    return subprocess.run(["git", "-C", str(where), "-c", "user.name=t", "-c", "user.email=t@t",
                           *args], capture_output=True, text=True, check=check)


@pytest.fixture
def repo(tmp_path):
    """A repository that knows the driver, with one commit to branch away from."""
    r = tmp_path / "r"
    (r / "data" / "review").mkdir(parents=True)
    (r / "tools").mkdir()
    (r / "tools" / "merge-data.py").write_text(DRIVER.read_text())
    # The driver takes the natural keys from the store, so the store is what the test gives it:
    # a key that moved in the real file and not here would be a test agreeing with itself.
    (r / "bankcredit").mkdir()
    (r / "bankcredit" / "__init__.py").write_text("")
    (r / "bankcredit" / "store.py").write_text((ROOT / "bankcredit" / "store.py").read_text())
    (r / ".gitattributes").write_text((ROOT / ".gitattributes").read_text())
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(r)], check=True)
    git(r, "add", "-A")
    git(r, "commit", "--quiet", "-m", "base")
    subprocess.run(["python3", str(r / "tools" / "merge-data.py"), "--install"], cwd=r, check=True)
    return r


def runs(*ids) -> pd.DataFrame:
    return pd.DataFrame([{"run_id": i, "source": i.split("-")[0], "status": "ok", "rows": 1,
                          "message": "", "started": "2026-09-14T00:00:00",
                          "finished": "2026-09-14T00:01:00"} for i in ids])


def two_ways(repo, write_base, write_ours, write_theirs):
    """Commit a common ancestor, then a change on each of two branches, then merge them."""
    write_base(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "ancestor")
    git(repo, "checkout", "--quiet", "-b", "incoming")
    write_theirs(repo)
    git(repo, "commit", "--quiet", "-am", "the other run")
    git(repo, "checkout", "--quiet", "main")
    write_ours(repo)
    git(repo, "commit", "--quiet", "-am", "this run")
    return git(repo, "merge", "--no-edit", "incoming", check=False)


def test_both_runs_rows_survive_a_merge(repo):
    """The 14 September case: a local run and the pipeline wrote different rows into one table."""
    p = repo / "data" / "runs.parquet"
    done = two_ways(repo,
                    lambda r: runs("esma-1").to_parquet(p, index=False),
                    lambda r: runs("esma-1", "pillar3-local").to_parquet(p, index=False),
                    lambda r: runs("esma-1", "prices-cloud").to_parquet(p, index=False))
    assert done.returncode == 0, f"the merge should not need a person\n{done.stdout}{done.stderr}"
    got = set(pd.read_parquet(p)["run_id"])
    assert got == {"esma-1", "pillar3-local", "prices-cloud"}, got


def test_a_record_only_one_side_changed_takes_that_sides_value(repo):
    """Untouched here, rewritten there: the rewrite is the news, and it is not a conflict."""
    p = repo / "data" / "runs.parquet"
    changed = runs("esma-1")
    changed.loc[0, "status"] = "failed"
    two_ways(repo,
             lambda r: runs("esma-1").to_parquet(p, index=False),
             lambda r: runs("esma-1", "pillar3-local").to_parquet(p, index=False),
             lambda r: changed.to_parquet(p, index=False))
    got = pd.read_parquet(p).set_index("run_id")["status"].to_dict()
    assert got["esma-1"] == "failed", got


def test_a_record_both_runs_rewrote_keeps_this_ones_and_says_so(repo):
    """Nothing can decide this one, so the run doing the merging keeps its own answer - and the
    merge says which record, so it can be looked at rather than discovered months later."""
    p = repo / "data" / "runs.parquet"
    ours, theirs = runs("esma-1"), runs("esma-1")
    ours.loc[0, "message"] = "mine"
    theirs.loc[0, "message"] = "theirs"
    done = two_ways(repo,
                    lambda r: runs("esma-1").to_parquet(p, index=False),
                    lambda r: ours.to_parquet(p, index=False),
                    lambda r: theirs.to_parquet(p, index=False))
    assert done.returncode == 0, done.stderr
    assert pd.read_parquet(p).loc[0, "message"] == "mine"
    assert "both runs" in done.stdout + done.stderr, done.stdout + done.stderr


def test_a_record_one_side_deleted_stays_deleted(repo):
    """`drop` exists to take bad rows out. A union that resurrects them is worse than a conflict."""
    p = repo / "data" / "runs.parquet"
    two_ways(repo,
             lambda r: runs("esma-1", "junk").to_parquet(p, index=False),
             lambda r: runs("esma-1", "junk", "pillar3-local").to_parquet(p, index=False),
             lambda r: runs("esma-1").to_parquet(p, index=False))
    assert set(pd.read_parquet(p)["run_id"]) == {"esma-1", "pillar3-local"}


def queue(*items) -> str:
    return json.dumps([{"id": i, "status": "open"} if isinstance(i, str) else i
                       for i in items], indent=1) + "\n"


def test_the_review_queue_keeps_both_runs_answers(repo):
    """queue.json is a list of items with an id, so it unions like a table. An item answered here
    and left open there is answered."""
    p = repo / "data" / "review" / "queue.json"
    two_ways(repo,
             lambda r: p.write_text(queue("a", "b")),
             lambda r: p.write_text(queue({"id": "a", "status": "done"}, "b")),
             lambda r: p.write_text(queue("a", "b", "c")))
    got = {i["id"]: i["status"] for i in json.loads(p.read_text())}
    assert got == {"a": "done", "b": "open", "c": "open"}, got


def test_a_file_keyed_by_name_unions_too(repo):
    """browser-links.json, hints.json and news_verdicts.json are objects keyed by id, not lists."""
    p = repo / "data" / "review" / "news_verdicts.json"
    two_ways(repo,
             lambda r: p.write_text(json.dumps({"news:1": "keep"}, indent=1)),
             lambda r: p.write_text(json.dumps({"news:1": "keep", "news:2": "drop"}, indent=1)),
             lambda r: p.write_text(json.dumps({"news:1": "keep", "news:3": "keep"}, indent=1)))
    assert json.loads(p.read_text()) == {"news:1": "keep", "news:3": "keep", "news:2": "drop"}


def test_a_generated_report_takes_the_newer_run(repo):
    """locator-health.json is not a collection of records; it is one run's view of everything.
    Half of one and half of the other would be a report of something that never happened."""
    p = repo / "data" / "review" / "locator-health.json"
    report = lambda when, n: json.dumps({"generated": when, "counts": {"faults": n}}, indent=1)
    two_ways(repo,
             lambda r: p.write_text(report("2026-09-13T00:00:00", 1)),
             lambda r: p.write_text(report("2026-09-14T09:00:00", 2)),
             lambda r: p.write_text(report("2026-09-14T13:47:00", 3)))
    assert json.loads(p.read_text())["counts"]["faults"] == 3


def test_a_bug_in_the_driver_becomes_an_ordinary_conflict(repo):
    """The one thing it must never do is lose a merge to its own mistake: anything unexpected
    hands the file back to git with both sides intact and the pull stopped."""
    p = repo / "data" / "runs.parquet"
    (repo / "tools" / "merge-data.py").write_text(
        "import sys\nraise SystemExit(1 if len(sys.argv) > 1 else 0)\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "a driver that cannot")
    done = two_ways(repo,
                    lambda r: runs("esma-1").to_parquet(p, index=False),
                    lambda r: runs("esma-1", "mine").to_parquet(p, index=False),
                    lambda r: runs("esma-1", "theirs").to_parquet(p, index=False))
    assert done.returncode != 0, "a driver that failed must not report a clean merge"
    assert set(pd.read_parquet(p)["run_id"]) == {"esma-1", "mine"}, "our side is still on disk"


def test_every_table_the_driver_covers_has_a_key(repo):
    """.gitattributes points at data/*.parquet; store.KEYS is where the key comes from. A table
    added to one and not the other fails at the worst moment, mid-pull, on a runner."""
    import sys
    sys.path.insert(0, str(ROOT))
    from bankcredit.store import KEYS
    for p in sorted((ROOT / "data").glob("*.parquet")):
        assert p.stem in KEYS, f"data/{p.name} would conflict with nothing to merge it on"


def test_a_copy_of_the_driver_outside_the_clone_still_finds_the_store(repo, tmp_path):
    """A clone too far behind to have the driver yet has to get one from somewhere, and the
    somewhere is a copy outside the work tree. Git runs a merge driver from the top of the clone,
    so that is where the keys come from - not from wherever the copy happens to sit."""
    outside = tmp_path / "elsewhere" / "merge-data.py"
    outside.parent.mkdir()
    outside.write_text(DRIVER.read_text())
    git(repo, "config", "merge.counterparty.driver", f"python3 {outside} %O %A %B %P")
    p = repo / "data" / "runs.parquet"
    done = two_ways(repo,
                    lambda r: runs("esma-1").to_parquet(p, index=False),
                    lambda r: runs("esma-1", "mine").to_parquet(p, index=False),
                    lambda r: runs("esma-1", "theirs").to_parquet(p, index=False))
    assert done.returncode == 0, done.stdout + done.stderr
    assert set(pd.read_parquet(p)["run_id"]) == {"esma-1", "mine", "theirs"}
