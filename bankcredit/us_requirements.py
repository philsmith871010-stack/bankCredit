"""US capital requirements, from data/reference/us-capital-requirements.json.

No US filing states an overall capital requirement the way a UK or EU bank's KM1 does, so a US
bank never had a Headroom score and its tiles were set against the 4.5% / 8% minimums. The
reference file builds the requirement on the Standardized approach: for a holding company, the
minimum plus its stress capital buffer and GSIB surcharge from the Fed's published table; for an
insured bank subsidiary, the minimum plus the 2.5% capital conservation buffer. Each entity holds
a list of periods, each in force from its effective date until the next.

    from bankcredit import us_requirements
    us_requirements.series_for("citigroup", ["2026-03-31", "2026-06-30"])
        -> {"cet1_requirement": [{"d": "2026-03-31", "v": 11.6, ...}, ...],
            "overall_capital_requirement": [{"d": "2026-03-31", "v": 15.1, ...}, ...]}
"""
from __future__ import annotations

import json
from datetime import date

from . import store

METRICS = ("cet1_requirement", "overall_capital_requirement")


def load(path=None) -> dict:
    """{entity_id: [period, ...]} oldest first; {} when the file is missing or unreadable."""
    p = path or store.DATA / "reference" / "us-capital-requirements.json"
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        periods = v if isinstance(v, list) else [v]
        out[k] = sorted((x for x in periods if x.get("effective")), key=lambda x: x["effective"])
    return out


def requirement_on(entity_id: str, on, table: dict | None = None) -> dict | None:
    """The period in force on `on` (a date or ISO string): the latest one effective on or before it."""
    table = load() if table is None else table
    d = str(on)[:10]
    held = [x for x in table.get(entity_id, []) if x["effective"] <= d]
    return held[-1] if held else None


def series_for(entity_id: str, dates, table: dict | None = None) -> dict:
    """Series points for the requirement at each of `dates` (the bank's capital reference dates) on or
    after the first effective date, in the shape export._series gives. Dates before any requirement
    was in force get no point: a 2026 surcharge says nothing about 2024."""
    table = load() if table is None else table
    out: dict[str, list] = {}
    for d in sorted({str(x)[:10] for x in dates if x}):
        per = requirement_on(entity_id, d, table)
        if not per:
            continue
        for m in METRICS:
            if per.get(m) is not None:
                out.setdefault(m, []).append({"d": d, "v": float(per[m]), "src": "us_requirements", "basis": "consolidated",
                                              "doc": per.get("source", ""), "page": None, "method": "reference",
                                              "conf": 1.0})
    return out


def facts_for(entity_id: str, dates, table: dict | None = None) -> list:
    """The same requirement as Fact records, for a caller that merges facts rather than series."""
    from .models import Fact
    return [Fact(entity_id=entity_id, reference_date=date.fromisoformat(p["d"]), metric=m, value=p["v"], unit="pct",
                 source="us_requirements", document=p["doc"], method="reference", confidence=1.0)
            for m, pts in series_for(entity_id, dates, table).items() for p in pts]
