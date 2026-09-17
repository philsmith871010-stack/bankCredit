"""Parquet-backed long tables plus JSON exports for the static site.

Tables live under data/: facts.parquet, ratings.parquet, prices.parquet, runs.parquet.
Appends are idempotent on a natural key so adapters can be re-run safely.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA = Path(os.environ.get("BANKCREDIT_DATA", Path(__file__).resolve().parent.parent / "data"))
KEYS = {
    "facts": ["entity_id", "reference_date", "metric", "basis", "source"],
    "ratings": ["entity_id", "agency", "rating_type", "horizon", "action_date"],
    "prices": ["entity_id", "date", "symbol"],
    "cds": ["entity_id", "date", "tier", "source"],
    "events": ["entity_id", "event_id"],
    "documents": ["entity_id", "url"],
    "series": ["series_id", "date"],
    "bonds": ["isin"],
    "bond_quotes": ["isin", "date"],
    "runs": ["run_id"],
    "history": ["entity_id", "date", "kind"],          # score and composite grade: daily snapshots and a quarterly backcast
    # Every rating action the European Rating Platform holds, back to its first day in July 2015.
    # The "ratings" table is the state today; this is how each of those ratings got there.
    "rating_actions": ["entity_id", "event_id"],
    # Ratings an agency has withdrawn. Deliberately not in "ratings": a withdrawn rating must never
    # reach a score, and a separate table cannot leak into one by an oversight at a point of use.
    "withdrawn_ratings": ["entity_id", "agency", "rating_type", "horizon", "action_date"],
    # Sovereign ratings, keyed by country code rather than entity: context beside a bank, never a
    # counterparty and never an input to a score.
    "sovereign_ratings": ["entity_id", "agency", "rating_type", "horizon", "action_date"],
}


# Every write rewrites its whole table, so two at once would lose one of them. Adapters now fetch
# several items at a time, and a fetch is allowed to record what it found, so the writes are held
# to one at a time here rather than in each caller. Costs nothing when nothing else is running.
_WRITING = threading.RLock()


def path(table: str) -> Path:
    return DATA / f"{table}.parquet"


def read(table: str) -> pd.DataFrame:
    p = path(table)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def upsert(table: str, rows: list | pd.DataFrame) -> int:
    """Append rows, replacing any existing row with the same natural key. Returns rows written."""
    with _WRITING:
        return _upsert(table, rows)


def _upsert(table: str, rows: list | pd.DataFrame) -> int:
    if isinstance(rows, list):
        if not rows:
            return 0
        if hasattr(rows[0], "__dataclass_fields__"):
            rows = pd.DataFrame([{f.name: getattr(r, f.name) for f in fields(r)} for r in rows])
        else:
            rows = pd.DataFrame(rows)
    if rows.empty:
        return 0
    new = rows.copy()
    for c in new.columns:
        if new[c].dtype == object:
            new[c] = new[c].apply(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    key = KEYS[table]
    old = read(table)
    if not old.empty:
        # a timestamp column keeps the form the table already has: text stays text, datetime stays
        # datetime. Mixing the two made an object column pyarrow refuses to write, and the first
        # ingest after the merge driver had stamped facts.parquet as text stopped the pipeline
        for c in new.columns:
            if c not in old.columns:
                continue
            o_dt, n_dt = pd.api.types.is_datetime64_any_dtype(old[c]), pd.api.types.is_datetime64_any_dtype(new[c])
            if n_dt and not o_dt:
                new[c] = new[c].apply(lambda v: v.isoformat() if pd.notna(v) else None)
            elif o_dt and not n_dt:
                new[c] = pd.to_datetime(new[c], errors="coerce")
        merged = pd.concat([old, new], ignore_index=True)
        merged = merged.drop_duplicates(subset=key, keep="last")
    else:
        merged = new
    DATA.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path(table), index=False)
    return len(new)


def drop(table: str, ne: dict | None = None, **eq) -> int:
    """Delete rows whose columns equal the given values (and differ from any in ne). Returns rows removed."""
    with _WRITING:
        return _drop(table, ne, **eq)


def _drop(table: str, ne: dict | None = None, **eq) -> int:
    df = read(table)
    if df.empty:
        return 0
    mask = pd.Series(True, index=df.index)
    for col, val in eq.items():
        mask &= df[col] == val
    for col, val in (ne or {}).items():
        mask &= df[col] != val
    if not mask.any():
        return 0
    df[~mask].to_parquet(path(table), index=False)
    return int(mask.sum())


def log_run(source: str, status: str, rows: int, message: str = "", started: datetime | None = None) -> None:
    now = datetime.utcnow()
    upsert("runs", [{
        "run_id": f"{source}-{now:%Y%m%dT%H%M%S}",
        "source": source, "status": status, "rows": rows, "message": message[:500],
        "started": (started or now).isoformat(), "finished": now.isoformat(),
    }])


def write_json(name: str, payload) -> Path:
    out = DATA / "json" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str))
    return out
