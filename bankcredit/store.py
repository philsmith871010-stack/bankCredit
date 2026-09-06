"""Parquet-backed long tables plus JSON exports for the static site.

Tables live under data/: facts.parquet, ratings.parquet, prices.parquet, runs.parquet.
Appends are idempotent on a natural key so adapters can be re-run safely.
"""
from __future__ import annotations

import json
import os
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
    "runs": ["run_id"],
}


def path(table: str) -> Path:
    return DATA / f"{table}.parquet"


def read(table: str) -> pd.DataFrame:
    p = path(table)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def upsert(table: str, rows: list | pd.DataFrame) -> int:
    """Append rows, replacing any existing row with the same natural key. Returns rows written."""
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
        merged = pd.concat([old, new], ignore_index=True)
        merged = merged.drop_duplicates(subset=key, keep="last")
    else:
        merged = new
    DATA.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path(table), index=False)
    return len(new)


def drop(table: str, **eq) -> int:
    """Delete rows whose columns equal the given values. Returns rows removed."""
    df = read(table)
    if df.empty:
        return 0
    mask = pd.Series(True, index=df.index)
    for col, val in eq.items():
        mask &= df[col] == val
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
