#!/usr/bin/env python3
"""Merge two versions of a data file the way the store would, not the way a text editor would.

Every table here is a set of records with a natural key, written whole on each save. Git sees a
rewritten binary blob and a JSON file with a hundred moved lines, so two runs that touched the same
table conflict even when they wrote about entirely different banks. That is not a theoretical cost:

  - The Mac run of 14 September collected Pillar 3 figures for six banks. The cloud pipeline ran a
    full collection an hour later. Both wrote data/facts.parquet, and git could only offer to throw
    one of them away.
  - The pipeline's own push does `git pull --rebase -X theirs`, which answers that question by
    discarding whatever a local run had pushed in the meantime, quietly.

There is a right answer and the store already knows it: union the records, keyed. This is that
answer wired in as a git merge driver, so it happens during the pull with nobody watching.

Where both sides changed the same record, the side that changed it wins; where both changed it,
ours wins and the file is named on stderr, because a run's own answers are the ones worth keeping
and a person can look afterwards. A record deleted on either side stays deleted.

Install into a clone (idempotent; .gitattributes says which paths it covers):

    python3 tools/merge-data.py --install

Git calls it as:  merge-data.py %O %A %B %P   - ancestor, ours, theirs, path. Ours is the result.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def install() -> int:
    """Teach this clone the driver. The name matches .gitattributes; the config is per-clone, so
    every runner has to do this once - the Mac job and the workflow both call it before they pull."""
    subprocess.run(["git", "config", "merge.counterparty.name",
                    "union data records on their natural key"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "merge.counterparty.driver",
                    f"python3 {ROOT / 'tools' / 'merge-data.py'} %O %A %B %P"], cwd=ROOT, check=True)
    return 0


def norm(v):
    """One value, comparable. NaN is not equal to itself and numpy scalars are not equal to ints."""
    try:
        import pandas as pd
        if v is None or (not isinstance(v, (list, dict, tuple)) and pd.isna(v)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, AttributeError):
            pass
    return v


def three_way(base: dict, ours: dict, theirs: dict) -> tuple[dict, list]:
    """Union three keyed collections. Returns the merged records, in order, and the keys both
    sides changed - incoming order first, so a file stays stable across runs."""
    gone = (set(base) - set(ours)) | (set(base) - set(theirs))
    order = [k for k in theirs if k not in gone] + [k for k in ours if k not in theirs and k not in gone]
    out, fought = {}, []
    for k in order:
        o, t = ours.get(k), theirs.get(k)
        if o is None or t is None:
            out[k] = o if t is None else t
        elif o == t or base.get(k) == t:
            out[k] = o
        elif base.get(k) == o:
            out[k] = t
        else:
            out[k] = o
            fought.append(k)
    return out, fought


def frame(path: Path):
    import pandas as pd
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_parquet(path)


def keyed(df, key: list[str]) -> dict:
    if df.empty:
        return {}
    rows = {}
    for rec in df.to_dict("records"):
        rec = {c: norm(v) for c, v in rec.items()}
        rows[tuple(str(rec.get(c)) for c in key)] = rec
    return rows


def merge_parquet(o: Path, a: Path, b: Path, table: str) -> int:
    import pandas as pd
    from bankcredit.store import KEYS
    key = KEYS[table]
    base, ours, theirs = (keyed(frame(p), key) for p in (o, a, b))
    merged, fought = three_way(base, ours, theirs)
    rows = list(merged.values())
    cols = list(dict.fromkeys([c for side in (theirs, ours) for rec in side.values() for c in rec]))
    pd.DataFrame(rows, columns=cols or None).to_parquet(a, index=False)
    say(table, len(base), len(ours), len(theirs), len(rows), fought)
    return 0


def load_json(path: Path):
    if not path.exists() or path.stat().st_size == 0:
        return None
    return json.loads(path.read_text() or "null")


def as_keyed(doc):
    """The shapes the review files take, or None when the file is a report, not a collection.

    A report says when it was generated - health.py writes that key and nothing keyed by an id
    has one - and its parts only make sense together, so there is no union to take."""
    if isinstance(doc, dict) and "generated" in doc:
        return None
    if isinstance(doc, dict):
        return dict(doc)
    if isinstance(doc, list) and all(isinstance(r, dict) and "id" in r for r in doc):
        return {str(r["id"]): r for r in doc}
    return None


def merge_json(o: Path, a: Path, b: Path, name: str) -> int:
    ours_doc, theirs_doc = load_json(a), load_json(b)
    ours, theirs = as_keyed(ours_doc), as_keyed(theirs_doc)
    if ours is None or theirs is None:
        # A generated report - locator-health.json and its like. There is nothing to union: the
        # newer run looked at more, so it wins outright.
        when = lambda d: str((d or {}).get("generated") or "") if isinstance(d, dict) else ""
        if when(theirs_doc) > when(ours_doc):
            a.write_text(b.read_text())
            print(f"merge-data: {name}: kept the newer report", file=sys.stderr)
        else:
            print(f"merge-data: {name}: kept this run's report", file=sys.stderr)
        return 0
    base = as_keyed(load_json(o)) or {}
    merged, fought = three_way(base, ours, theirs)
    rows = list(merged.values())
    doc = rows if isinstance(ours_doc, list) else merged
    text = json.dumps(doc, indent=1, ensure_ascii=False, default=str)
    a.write_text(text + "\n" if a.read_text().endswith("\n") else text)
    say(name, len(base), len(ours), len(theirs), len(rows), fought)
    return 0


def say(name, base, ours, theirs, out, fought) -> None:
    note = f", {len(fought)} record(s) written by both runs kept from this one" if fought else ""
    print(f"merge-data: {name}: {ours} here + {theirs} incoming (from {base}) -> {out}{note}",
          file=sys.stderr)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--install"]:
        return install()
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    o, a, b, path = Path(argv[0]), Path(argv[1]), Path(argv[2]), Path(argv[3])
    try:
        if path.suffix == ".parquet":
            return merge_parquet(o, a, b, path.stem)
        if path.suffix == ".json":
            return merge_json(o, a, b, path.name)
    except Exception as exc:                                    # noqa: BLE001
        # Never lose a merge to a bug in the merge: hand it back to git as an ordinary conflict,
        # which leaves both sides on disk and stops the pull.
        print(f"merge-data: {path}: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"merge-data: {path}: not a file this driver knows", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
