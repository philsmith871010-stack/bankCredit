"""Is every source we rely on still working?

Tests catch a change we make. This catches a change the world makes: a bank redesigns its
investor pages, a locator's pattern stops matching, and nothing fails - the collector simply
returns no documents and the bank quietly drops out of the scored set. Nobody notices until
someone asks why a name has no figures.

So every run classifies each entity's Pillar 3 locator:

  ok        a document arrived within the window its reporting cadence implies
  overdue   the locator worked once but its newest document is older than that window
  never     a locator exists and has never yielded a document
  no source no locator at all, and no other adapter supplies a capital ratio
  by design capital is not published at this entity at all (data/reference/capital-not-published.json)

and each locator itself for a pattern that no longer compiles or names an entity that is not in
the register. The report is written to data/review/locator-health.json and committed, so a
regression shows up as a diff as well as on the Status page.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import store
from .entities import load as load_entities
from .adapters.pillar3_locators import LOCATORS
from .score import ALTERNATES, PILLARS

REPORT = store.DATA / "review" / "locator-health.json"
# a semi-annual filer plus a quarter's grace: past this, something has broken rather than slipped
OVERDUE_DAYS = 300
# the same metrics the score's capital pillar accepts, so this never reports a gap the score does
# not see: a US bank reporting Tier 1 leverage on average assets has capital, in the terms we use
CAPITAL = tuple(PILLARS["capital"][1]) + (ALTERNATES["leverage_ratio"][0],)


def _faults() -> list[dict]:
    """Locators that cannot work at all, whatever the site does."""
    known = {e.id for e in load_entities()}
    out, seen = [], set()
    for loc in LOCATORS:
        ent = loc["entity"]
        if ent not in known:
            out.append({"entity": ent, "fault": "not in the entity register"})
        for field in ("match", "exclude"):
            if loc.get(field):
                try:
                    re.compile(loc[field])
                except re.error as exc:
                    out.append({"entity": ent, "fault": f"{field} does not compile: {exc}"})
        # a page legitimately appears twice when one locator takes the capital report and
        # another the LCR disclosure, so the template and the pattern are part of the identity
        key = (ent, loc.get("page", ""), loc.get("match", ""), loc.get("template", "km1"),
               tuple(loc.get("urls", ())))
        if key in seen:
            out.append({"entity": ent, "fault": f"identical locator repeated for {loc.get('page') or loc.get('urls')}"})
        seen.add(key)
    return out


def report(today: date | None = None) -> dict:
    today = today or date.today()
    entities = [e for e in load_entities() if e.active]
    facts = store.read("facts")
    docs = store.read("documents")
    from .export import capital_not_published
    not_published = capital_not_published()
    by_entity: dict[str, list[dict]] = {}
    for loc in LOCATORS:
        by_entity.setdefault(loc["entity"], []).append(loc)

    rows = []
    for e in entities:
        locs = by_entity.get(e.id, [])
        cap = facts[(facts.entity_id == e.id) & (facts.metric.isin(CAPITAL))] if not facts.empty else facts
        newest = max((str(d)[:10] for d in cap.reference_date), default=None) if not cap.empty else None
        sources = sorted(set(cap.source)) if not cap.empty else []
        n_docs = int((docs.entity_id == e.id).sum()) if not docs.empty else 0
        age = (today - date.fromisoformat(newest)).days if newest else None

        if e.id in not_published:
            state = "by design"          # a stated reason, not a gap: never chase these
        elif newest and age is not None and age <= OVERDUE_DAYS:
            state = "ok"
        elif newest:
            state = "overdue"
        elif locs:
            state = "never"
        else:
            state = "no source"
        rows.append({"entity": e.id, "short": e.short_name, "region": e.region,
                     "locators": len(locs), "kinds": sorted({l.get("kind", "html") for l in locs}),
                     "documents": n_docs, "capital_as_of": newest, "age_days": age,
                     "capital_sources": sources, "state": state})

    counts = {s: sum(1 for r in rows if r["state"] == s)
              for s in ("ok", "overdue", "never", "no source", "by design")}
    return {"generated": today.isoformat(), "counts": counts, "faults": _faults(),
            "entities": sorted(rows, key=lambda r: (["never", "overdue", "no source", "by design", "ok"].index(r["state"]), r["entity"]))}


def write(rep: dict | None = None) -> dict:
    rep = rep or report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    import json
    REPORT.write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
    return rep


def load() -> dict:
    import json
    try:
        return json.loads(REPORT.read_text())
    except Exception:
        return {}
