"""The sovereign rating of each country the universe places money in.

A bank is rated in the context of the state that stands behind its banking system, and a treasurer
comparing a Qatari bank with a Finnish one is comparing two sovereigns as much as two balance
sheets. The ratings are in the same public register the bank ratings come from - agencies file
sovereign ratings to the ESMA European Rating Platform like any other - so this costs no new
source, no key and no licence.

Kept apart from the banks on purpose: a country is not a counterparty, it has no place in the
universe table or the score, and its rating is shown beside a bank as context rather than folded
into it. One row per country per agency, in its own table.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date

from .. import store
from ..models import Rating
from . import register
from .esma import (SOLR, PARENT_FQ, FIELDS, ROWS, SLEEP, WITHDRAWN, agency_code,
                   horizon, outlook, parse_date, _quote)
from .esma import ESMARatingsAdapter

log = logging.getLogger("bankcredit")

REFERENCE = "sovereigns.json"

# Only the credit rating agencies the site already shows for banks. The register also carries the
# Economist Intelligence Unit, whose country-risk scale reads like a rating and is not one - it
# has France at BBB where S&P and Fitch have AA-, and averaging the two would say something false.
AGENCY_ALLOW = {"fitch", "sp", "moodys", "dbrs", "kbra", "scope", "jcr", "capital", "creditreform"}


def _names(meta: dict) -> list[str]:
    """Every spelling for one country: the issuer, plus any alternates the reference file lists."""
    return [meta["issuer"], *(meta.get("also") or [])]


def sovereigns() -> dict[str, dict]:
    """country code -> {issuer, short}. Data, not code: a name the register spells differently is
    corrected in the reference file without touching this module."""
    p = store.DATA / "reference" / REFERENCE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@register
class SovereignRatingsAdapter(ESMARatingsAdapter):
    name = "sovereign"
    cadence = "weekly"          # a sovereign rating moves a few times a year at most

    def discover(self):
        """Only the countries the universe actually holds a bank in."""
        held = {e.country for e in self.entities if e.country}
        return [(cc, meta) for cc, meta in sorted(sovereigns().items()) if cc in held]

    def fetch(self, item):
        """One country, every name the register files it under: France is "French Republic" to
        Scope and "Republic of France" to S&P, and each spelling carries different agencies."""
        cc, meta = item
        want = {n.strip().lower() for n in _names(meta)}
        params = {"q": "issuerName:(" + " OR ".join(_quote(n) for n in _names(meta)) + ")",
                  "fq": PARENT_FQ, "rows": ROWS, "sort": "racValidityDatetime desc", "fl": FIELDS}
        docs = self._select(params)["response"]["docs"]
        time.sleep(SLEEP)
        # The register matches loosely; keep only the issuers asked for, so "Ireland" cannot
        # collect "Bank of Ireland" and "United Kingdom" cannot collect a UK company.
        return [d for d in docs if (d.get("issuerName") or "").strip().lower() in want] or None

    # A sovereign's rating is filed under names the bank mapper calls "other": Scope writes
    # "Long-term rating", JCR files no name at all, and a government's "Senior Unsecured Debt
    # Rating" is a rating of its own bonds rather than of some instrument it sponsors. Rank them
    # instead of discarding them, and keep the best one an agency publishes.
    @staticmethod
    def _rank(name: str) -> int | None:
        low = (name or "").strip().lower()
        if not low:
            return 0                                    # unnamed: the agency's headline rating
        if any(w in low for w in ("short", "covered", "structured", "subordinated", "counterparty")):
            return None
        if "issuer" in low or low in ("long-term rating", "long term rating", "lt rating"):
            return 0
        if "senior unsecured" in low or "government bond" in low:
            return 1
        return None

    def parse(self, item, raw) -> list[Rating]:
        cc, meta = item
        candidates: dict[tuple, list[tuple]] = {}
        for d in raw:
            if (d.get("lastActionTypeLabel") or "").lower() == "removed from erp":
                continue
            if (d.get("ratingStatusLabel") or "").strip() == WITHDRAWN:
                continue
            name_rank = self._rank(d.get("issuerRatingName", ""))
            hz = horizon(d.get("timeHorizonDescr", ""))
            if name_rank is None or hz != "long":
                continue
            if agency_code(d.get("craName", "")) not in AGENCY_ALLOW:
                continue
            rtype = "issuer"                            # one row per country per agency
            rec = Rating(
                entity_id=cc,                       # the country code is the key here, not a bank
                agency=agency_code(d.get("craName", "")),
                rating_type=rtype,
                horizon=hz,
                value=(d.get("ratingValueLabel") or "").strip(),
                outlook=outlook(d.get("ratingStatusLabel", "")),
                action=d.get("lastActionTypeLabel") or "",
                action_date=parse_date(d.get("racValidityDatetimeStr", "")),
                source_id=d.get("id", ""),
            )
            if not rec.value:
                continue
            ccy = (d.get("localForeignCurrencyValue") or "").lower()
            ccy_rank = 0 if ccy.startswith("foreign") else (1 if ccy.startswith("local") else 2)
            key = (rec.agency, rtype, hz)
            candidates.setdefault(key, []).append(
                ((ccy_rank, name_rank, -(rec.action_date.toordinal() if rec.action_date else 0)), rec))
        # Foreign currency first, then the headline rating name, then the newest: one per agency.
        return [min(v, key=lambda t: t[0])[1] for v in candidates.values()]

    def validate(self, records: list[Rating]) -> list[Rating]:
        return [r for r in records if r.value and r.action_date]

    def load(self, records: list[Rating]) -> int:
        return store.upsert("sovereign_ratings", records)
