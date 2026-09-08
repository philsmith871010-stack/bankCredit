"""ESMA European Rating Platform: current issuer-level ratings for every entity.

Public Solr endpoint behind registers.esma.europa.eu. Coverage is global because
Moody's, S&P, Fitch, DBRS, KBRA, Scope and JCR endorse their ratings into the EU.

Query notes (docs/data-sources-investigation.md, 12.3):
  type_s:parent            current state of each rating; type_s:child = action history
  ratedObjectCode:ISR      issuer-level (INT = individual instruments)
  ratingStatusLabel        outlook / watch status; withdrawn ratings are read but kept apart
  issuerRatingName         distinguishes deposit / issuer / IDR / counterparty ratings
  issuerLeiCode            LEI, the preferred match key; issuerName is a tokenised text
                           field (accented spellings do not match, plain ASCII does)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime

import requests

from .. import store
from ..models import Entity, Rating
from .base import Adapter, register

log = logging.getLogger("bankcredit")

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_radar/select"
FIELDS = ("craName,ratingValueLabel,timeHorizonDescr,issuerRatingName,ratingStatusLabel,"
          "lastActionTypeLabel,racValidityDatetimeStr,issuerLeiCode,issuerName,id,"
          "localForeignCurrencyValue,solicitationStatus")
PARENT_FQ = ["type_s:parent", "ratedObjectCode:ISR"]
# A withdrawn rating is not a rating, so it never scores; but "Moody's withdrew its Baa2 in
# October 2024" tells a treasurer far more than a bare "unrated", so it is kept and shown.
WITHDRAWN = "Withdrawal"
SLEEP = 0.5          # seconds between requests
TIMEOUT = 120
ROWS = 500

# Extra spellings tried (OR-ed into the same query) when an entity has no LEI and
# the name in entities.csv differs from what ESMA holds.
ALIASES: dict[str, list[str]] = {
    "rabobank": ["Coöperatieve Rabobank U.A.", "Cooperatieve Rabobank U.A."],
    "credit-agricole": ["Crédit Agricole S.A.", "Credit Agricole S.A."],
    "societe-generale": ["Société Générale", "Societe Generale", "Société Générale S.A."],
    "helaba": ["Landesbank Hessen-Thüringen Girozentrale", "Landesbank Hessen-Thueringen Girozentrale"],
    "lbbw": ["Landesbank Baden-Württemberg", "Landesbank Baden-Wuerttemberg"],
    "credit-mutuel": ["Confédération Nationale du Crédit Mutuel", "Confederation Nationale du Credit Mutuel",
                      "Banque Fédérative du Crédit Mutuel", "Banque Federative du Credit Mutuel"],
    "bpce": ["BPCE", "Groupe BPCE", "BPCE S.A."],
    "op-financial-group": ["OP Osuuskunta", "OP Corporate Bank plc"],
    "banco-santander": ["Banco Santander, S.A.", "Banco Santander S.A."],
    "bbva": ["Banco Bilbao Vizcaya Argentaria, S.A.", "Banco Bilbao Vizcaya Argentaria S.A."],
    "caixabank": ["CaixaBank, S.A.", "CaixaBank S.A."],
    "mufg": ["Mitsubishi UFJ Financial Group, Inc."],
    "smfg": ["Sumitomo Mitsui Financial Group, Inc."],
    "mizuho": ["Mizuho Financial Group, Inc."],
    "sumitomo-mitsui-trust": ["Sumitomo Mitsui Trust Group, Inc.", "Sumitomo Mitsui Trust Holdings, Inc."],
    "goldman-sachs": ["The Goldman Sachs Group, Inc.", "Goldman Sachs Group, Inc."],
}

AGENCIES = [("fitch", "fitch"), ("standard & poor", "sp"), ("moody", "moodys"), ("dbrs", "dbrs"),
            ("kroll", "kbra"), ("scope", "scope"), ("japan credit", "jcr")]
SKIP_TYPES = ("(xgs)", "derivative counterparty", "certificate of deposit")
# Ordered: first match wins.
RATING_TYPES = [("issuer default", "idr"), ("deposit", "deposit"), ("resolution counterparty", "resolution_counterparty"),
                ("counterparty risk", "counterparty"), ("issuer", "issuer")]
# When several parent docs share agency/type/horizon, prefer the headline name over debt-class variants.
NAME_RANK = {"issuer credit rating": 0, "issuer rating": 0, "lt issuer credit rating": 0,
             "long term issuer default rating": 0, "short term issuer default rating": 0,
             "deposit rating": 0, "counterparty risk rating": 0, "resolution counterparty rating": 0}


def agency_code(cra_name: str) -> str:
    low = (cra_name or "").lower()
    for needle, code in AGENCIES:
        if needle in low:
            return code
    first = low.replace("'", "").split()
    return first[0] if first else ""


def rating_type(issuer_rating_name: str) -> str:
    low = (issuer_rating_name or "").lower()
    if any(s in low for s in SKIP_TYPES):
        return "other"
    for needle, code in RATING_TYPES:
        if needle in low:
            return code
    return "other"


def horizon(time_horizon: str) -> str:
    low = (time_horizon or "").lower()
    if low.startswith("long"):
        return "long"
    if low.startswith("short"):
        return "short"
    return ""


def outlook(status_label: str) -> str:
    """'Maintained under stable outlook' -> stable; 'Placed under negative watch' -> watch negative."""
    low = (status_label or "").lower()
    if not low or low.startswith("removed"):
        return ""
    direction = next((d for d in ("positive", "negative", "stable") if d in low), "")
    if "watch" in low:
        return f"watch {direction}" if direction in ("positive", "negative") else ""
    return direction if "outlook" in low else ""


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _quote(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


@register
class ESMARatingsAdapter(Adapter):
    name = "esma"
    cadence = "daily"
    regions: tuple[str, ...] = ()

    # ---- pipeline ----
    def discover(self):
        return self.entities

    def query_for(self, entity: Entity) -> str:
        if entity.lei:
            return f"issuerLeiCode:{entity.lei}"
        names = [entity.name] + [a for a in ALIASES.get(entity.id, []) if a != entity.name]
        return "issuerName:(" + " OR ".join(_quote(n) for n in names) + ")"

    def _select(self, params: dict, post: bool = False) -> dict:
        """One Solr call, retried once on a 5xx or connection error."""
        params = {"wt": "json", **params}
        for attempt in (1, 2):
            try:
                r = (self.session.post(SOLR, data=params, timeout=TIMEOUT) if post
                     else self.session.get(SOLR, params=params, timeout=TIMEOUT))
                if r.status_code >= 500 and attempt == 1:
                    log.warning("esma %s on attempt 1, retrying", r.status_code)
                    time.sleep(2)
                    continue
                r.raise_for_status()
                return r.json()
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(2)
        raise RuntimeError("unreachable")

    def fetch(self, entity: Entity) -> list[dict] | None:
        params = {"q": self.query_for(entity), "fq": PARENT_FQ, "rows": ROWS,
                  "sort": "racValidityDatetime desc", "fl": FIELDS}
        docs = self._select(params)["response"]["docs"]
        time.sleep(SLEEP)
        return docs or None

    def parse(self, entity: Entity, raw: list[dict]) -> list[Rating]:
        candidates: dict[tuple, list[tuple]] = {}
        withdrawn: dict[tuple, list[tuple]] = {}
        for d in raw:
            if (d.get("lastActionTypeLabel") or "").lower() == "removed from erp":
                continue
            rtype = rating_type(d.get("issuerRatingName", ""))
            hz = horizon(d.get("timeHorizonDescr", ""))
            if rtype == "other" or not hz:
                continue
            rec = Rating(
                entity_id=entity.id,
                agency=agency_code(d.get("craName", "")),
                rating_type=rtype,
                horizon=hz,
                value=(d.get("ratingValueLabel") or "").strip(),
                outlook=outlook(d.get("ratingStatusLabel", "")),
                action=d.get("lastActionTypeLabel") or "",
                action_date=parse_date(d.get("racValidityDatetimeStr", "")),
                source_id=d.get("id", ""),
            )
            ccy = (d.get("localForeignCurrencyValue") or "").lower()
            ccy_rank = 0 if ccy.startswith("foreign") else (1 if ccy.startswith("local") else 2)
            name_rank = NAME_RANK.get((d.get("issuerRatingName") or "").lower().strip(), 1)
            sort_key = (ccy_rank, name_rank, -(rec.action_date.toordinal() if rec.action_date else 0))
            bucket = withdrawn if (d.get("ratingStatusLabel") or "").strip() == WITHDRAWN else candidates
            bucket.setdefault((rec.agency, rtype, hz), []).append((sort_key, rec))
        # Foreign currency beats local; headline rating name beats debt-class variants; newest wins.
        pick = lambda bucket: [min(v, key=lambda t: t[0])[1] for v in bucket.values()]
        self._withdrawn = pick(withdrawn)
        return pick(candidates)

    def validate(self, records: list[Rating]) -> list[Rating]:
        self._withdrawn = [r for r in getattr(self, "_withdrawn", []) if r.value]
        return [r for r in records if r.value]

    def load(self, records: list[Rating]) -> int:
        """A rating the register now reports as withdrawn is kept apart from the live ones, and
        never in both places: a live rating for the same agency, type and horizon always wins."""
        n = store.upsert("ratings", records)
        if self._withdrawn:
            live = {(r.entity_id, r.agency, r.rating_type, r.horizon) for r in records}
            fresh = [r for r in self._withdrawn
                     if (r.entity_id, r.agency, r.rating_type, r.horizon) not in live]
            store.upsert("withdrawn_ratings", fresh)
        self._withdrawn = []
        return n

    # ---- action history (events feed; not wired into run() yet) ----
    def actions(self, entity: Entity, since: date | str) -> list[dict]:
        """Rating actions on the entity's live issuer-level ratings since `since` (child docs)."""
        since_s = since.isoformat() if isinstance(since, date) else str(since)[:10]
        parents = self.fetch(entity) or []
        by_id = {p["id"]: p for p in parents}
        if not by_id:
            return []
        params = {"q": "*:*",
                  "fq": ["type_s:child", "{!terms f=_root_}" + ",".join(by_id),
                         f"actionsRacValidityDatetime:[{since_s}T00:00:00Z TO *]"],
                  "rows": 1000, "sort": "actionsRacValidityDatetime desc",
                  "fl": "id,parent_id,actionsActionTypeLabel,actionsRatingValueLabel,actionsRacValidityDatetimeStr"}
        docs = self._select(params, post=True)["response"]["docs"]
        time.sleep(SLEEP)
        out = []
        for c in docs:
            p = by_id.get(c.get("parent_id") or "", {})
            out.append({
                "entity_id": entity.id,
                "event_id": c.get("id", ""),
                "date": parse_date(c.get("actionsRacValidityDatetimeStr", "")),
                "action": c.get("actionsActionTypeLabel") or "",
                "value": c.get("actionsRatingValueLabel") or "",
                "agency": agency_code(p.get("craName", "")),
                "rating_type": rating_type(p.get("issuerRatingName", "")),
                "horizon": horizon(p.get("timeHorizonDescr", "")),
                "rating_name": p.get("issuerRatingName", ""),
                "parent_id": c.get("parent_id", ""),
            })
        return out
