"""Entity master access."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import Entity

PATH = Path(__file__).resolve().parent.parent / "data" / "entities.csv"


def load() -> list[Entity]:
    with PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        r = {k: (v or "") for k, v in r.items()}
        r["active"] = r.get("active", "true").lower() != "false"
        out.append(Entity(**{k: r[k] for k in Entity.__dataclass_fields__ if k in r}))
    return out


def by_id() -> dict[str, Entity]:
    return {e.id: e for e in load()}
