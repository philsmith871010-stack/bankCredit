"""What each rating was on any past day, rebuilt from the register's own action log.

The `ratings` table is the state today. The European Rating Platform also publishes, under every
live rating record, the actions that produced it - back to 1 July 2015, the day the agencies loaded
their books into the platform. `rating_actions` holds those; this module reads them back as state.

The rules are the ones the adapter already applies to today's ratings, moved along the time axis:
one record per agency, rating type and horizon, foreign currency ahead of local, a headline rating
name ahead of a debt-class variant, and a withdrawn record is not a rating. A reconstruction on
different rules would produce a history that does not join up with the present.

Everything here is read off one sweep of the action log, done once per entity: the state is
recomputed only on the days it actually changed, and any question about a particular day is a
lookup into that. Rabobank alone carries 3,600 actions across 267 rating records, so re-walking
the log per question would not have been quick enough to run over the whole universe.

Two limits are the register's, not ours: nothing before July 2015 is here, and a rating record an
agency has removed from the platform takes its actions with it.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date

import pandas as pd

from .adapters.esma import NAME_RANK

# Actions that set a rating, actions that end one. Everything else - outlook and watch moves - is
# a change of tone on a rating that stays where it was.
SETS = {"AF", "UP", "DG", "NW", "OR"}
ENDS = {"WD"}
# Preference between rating types when an agency publishes several, as on the profile today.
TYPE_PREF = {"idr": 0, "issuer": 1, "deposit": 2, "counterparty": 3, "resolution_counterparty": 4}
AGENCY_ORDER = ["fitch", "sp", "moodys", "dbrs", "kbra", "scope", "jcr"]
START = "2015-07-01"       # the platform's first day; every agency's book arrives on it


def _rank(currency: str, rating_name: str) -> tuple[int, int]:
    ccy = (currency or "").lower()
    ccy_rank = 0 if ccy.startswith("foreign") else (1 if ccy.startswith("local") else 2)
    return ccy_rank, NAME_RANK.get((rating_name or "").lower().strip(), 1)


class Book:
    """One entity's rating records and the state they were in on each day that state changed."""

    def __init__(self, actions: pd.DataFrame | None = None):
        self.records: list[dict] = []
        self.dates: list[str] = []
        self.states: list[dict] = []           # agency -> {value, type, date}
        self.composites: list[float | None] = []
        if actions is not None and not actions.empty:
            self._build(actions)

    # ---- building ----
    def _build(self, actions: pd.DataFrame) -> None:
        from .export import rating_grade
        recs: dict[str, dict] = {}
        changes: dict[str, list[tuple[str, str]]] = {}     # date -> [(record id, new value)]
        for r in actions.sort_values(["date", "event_id"]).itertuples():
            if (r.horizon or "") != "long" or not r.agency:
                continue
            code, d = (r.action_code or ""), str(r.date)[:10]
            if code not in SETS and code not in ENDS:
                continue                                   # an outlook move leaves the rating where it is
            rec = recs.get(r.parent_id)
            if rec is None:
                rank = _rank(getattr(r, "currency", ""), getattr(r, "rating_name", ""))
                rec = recs[r.parent_id] = {"agency": r.agency, "type": r.rating_type,
                                           "pref": TYPE_PREF.get(r.rating_type, 9), "rank": rank}
            value = "" if code in ENDS else (r.value or "")
            if code in SETS and not value:
                continue
            changes.setdefault(d, []).append((r.parent_id, value))
        self.records = list(recs.values())
        live: dict[str, tuple[str, str]] = {}              # record id -> (value, date set)
        for d in sorted(changes):
            for rid, value in changes[d]:
                if value:
                    live[rid] = (value, d)
                else:
                    live.pop(rid, None)
            state = {}
            for rid, (value, seen) in live.items():
                rec = recs[rid]
                key = (rec["pref"], rec["rank"][0], rec["rank"][1], _desc(seen))
                cur = state.get(rec["agency"])
                if cur is None or key < cur[0]:
                    state[rec["agency"]] = (key, {"agency": rec["agency"], "value": value,
                                                  "type": rec["type"], "date": seen})
            state = {a: state[a][1] for a in AGENCY_ORDER if a in state}
            grades = [g for g in (rating_grade(s["value"]) for s in state.values()) if g is not None]
            comp = round(float(pd.Series(grades).median()), 1) if grades else None
            if self.states and self.states[-1] == state:
                continue                                   # an affirmation is not a change
            self.dates.append(d)
            self.states.append(state)
            self.composites.append(comp)

    # ---- reading ----
    def __bool__(self) -> bool:
        return bool(self.dates)

    def _i(self, when: str | date) -> int:
        when = when.isoformat() if isinstance(when, date) else str(when)[:10]
        return bisect_right(self.dates, when) - 1

    def state_at(self, when: str | date) -> list[dict]:
        """One headline long-term rating per agency on that day, in the order the site shows them."""
        i = self._i(when)
        return list(self.states[i].values()) if i >= 0 else []

    def composite_at(self, when: str | date) -> float | None:
        """The median of the agencies' grades on that day: the number the profile shows today,
        computed on the ratings that stood then."""
        i = self._i(when)
        return self.composites[i] if i >= 0 else None

    def agency_steps(self) -> list[dict]:
        """Per agency, the days its headline rating changed and what it changed to. A step, not a
        reading: the line between two changes is flat because the rating was flat."""
        from .export import rating_grade
        out: dict[str, list] = {}
        last: dict[str, str] = {}
        for d, state in zip(self.dates, self.states):
            for ag in list(last):
                if ag not in state:                        # every agency rating withdrawn
                    last.pop(ag)
                    out.setdefault(ag, []).append([d, "", None])
            for ag, s in state.items():
                if last.get(ag) == s["value"]:
                    continue
                last[ag] = s["value"]
                out.setdefault(ag, []).append([d, s["value"], rating_grade(s["value"])])
        return [{"agency": a, "steps": out[a]} for a in AGENCY_ORDER if out.get(a)]

    def composite_steps(self) -> list[list]:
        """The days the composite grade moved, and where to."""
        out, last = [], object()
        for d, c in zip(self.dates, self.composites):
            if c is None or c == last:
                continue
            last = c
            out.append([d, c])
        return out

    def moves(self) -> list[dict]:
        """Every change in an agency's headline rating after the platform's first day, newest first.

        The first entry in each agency's series is the book it loaded on day one, not an action it
        took, so it is not a move.
        """
        from .export import rating_grade
        out = []
        for row in self.agency_steps():
            steps = row["steps"]
            for i in range(1, len(steps)):
                d, value, grade = steps[i]
                prev = steps[i - 1][1]
                if not value:
                    out.append({"date": d, "agency": row["agency"], "action": "withdrawal",
                                "from": prev, "value": "", "notches": None})
                    continue
                if not prev:
                    # the agency had withdrawn and has rated the bank again: a new rating, and
                    # calling it a downgrade from nothing would be worse than saying nothing
                    out.append({"date": d, "agency": row["agency"], "action": "new",
                                "from": "", "value": value, "notches": None})
                    continue
                pg = rating_grade(prev)
                notches = (pg - grade) if (pg is not None and grade is not None) else None
                out.append({"date": d, "agency": row["agency"],
                            "action": "upgrade" if (notches or 0) > 0 else "downgrade",
                            "from": prev, "value": value, "notches": abs(notches) if notches else None})
        return sorted(out, key=lambda x: x["date"], reverse=True)


def _desc(d: str) -> str:
    """Sort a date descending inside an ascending tuple."""
    return "".join(chr(ord("9") - (ord(c) - ord("0"))) if c.isdigit() else c for c in d)


def by_entity(actions: pd.DataFrame | None) -> dict[str, Book]:
    """One Book per entity, built in a single pass over the table."""
    if actions is None or actions.empty:
        return {}
    return {eid: Book(g) for eid, g in actions.groupby("entity_id")}
