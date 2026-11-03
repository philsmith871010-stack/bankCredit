"""Events feed: rating actions and new disclosures, from the public record, no AI service.

Two collectors write to the `events` table (key: entity_id + event_id):

  rating      ESMA European Rating Platform action history (type_s:child records on the
              entity's live issuer-level ratings), last 400 days
  disclosure  every Pillar 3 document the pillar3 adapter loaded (documents table)

Severity is rules-based on the agency's own action: default -> bad; downgrade, negative outlook or
watch -> warn; upgrade, positive -> good; everything else info.

Headlines were collected here too, from Google News, until 3 November 2026. A review of the 3,214
held found about one in fourteen bore on a deposit decision, and those few reached the ratings, the
filings or the market signal within days, so the site keeps to the record and the prices. Rows of
type "news" already stored are left in the table and never read.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from .. import store
from ..models import Entity
from .base import Adapter, register
from .esma import ESMARatingsAdapter

log = logging.getLogger("bankcredit.events")

SINCE_DAYS = 400
AGENCY = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's", "dbrs": "DBRS", "kbra": "KBRA", "scope": "Scope", "jcr": "JCR"}


def rating_severity(action: str, value: str = "") -> str:
    low = (action or "").lower()
    if "default" in low:
        return "bad"
    if "downgrade" in low or ("watch" in low and "negative" in low) or "negative" in low:
        return "warn"
    if "upgrade" in low or "positive" in low:
        return "good"
    return "info"


@register
class EventsAdapter(Adapter):
    name = "events"
    cadence = "daily"
    # the register is one service: three at a time is a courtesy, not a limit
    workers = 3

    def __init__(self):
        super().__init__()
        self.esma = ESMARatingsAdapter()

    def discover(self):
        only = {x for x in os.environ.get("BANKCREDIT_ONLY", "").split(",") if x}
        for e in self.entities:
            if not only or e.id in only:
                yield e
        yield "documents"

    # ---- fetch ----
    def fetch(self, item):
        if item == "documents":
            return {"documents": store.read("documents")}
        e: Entity = item
        try:
            return {"actions": self.esma.actions(e, date.today() - timedelta(days=SINCE_DAYS))}
        except Exception as exc:
            log.warning("events %s: esma actions failed: %s", e.id, exc)
            return {"actions": []}

    # ---- parse ----
    def parse(self, item, raw) -> list[dict]:
        rows = []
        if item == "documents":
            docs = raw["documents"]
            if docs.empty:
                return rows
            for d in docs[docs.status.isin(["loaded", "unverified"])].itertuples():
                pub = str(getattr(d, "published", "") or "")[:10]
                ref = str(d.reference_date or "")[:10]
                pub = pub if pub[:2] == "20" else ""                  # a missing stamp reads as "nan" or "None"
                ref = ref if ref[:2] == "20" else ""
                when = pub if pub and pub >= ref else ref            # the PDF's own stamp, else the period end; never our fetch time
                if not when:
                    continue
                rows.append({"entity_id": d.entity_id, "event_id": f"doc:{(d.sha256 or d.url)[:16]}",
                             "date": when, "type": "disclosure",
                             "title": f"Pillar 3 report" + (f" for the period to {ref}" if ref else "") + (" published" if pub else "") + f": {d.title}",
                             "source": "FCA NSM" if d.origin == "nsm" else "firm website", "url": d.url,
                             "severity": "info", "detail": d.status})
            return rows
        e: Entity = item
        for a in raw["actions"]:
            if not a.get("date"):
                continue
            agency = AGENCY.get(a["agency"], a["agency"])
            rows.append({"entity_id": e.id, "event_id": f"esma:{a['event_id']}", "date": a["date"].isoformat(), "type": "rating",
                         "title": f"{agency} {a['action'].lower()}: {a['rating_name']} {a['value']}".strip(),
                         "source": "ESMA European Rating Platform", "url": "https://registers.esma.europa.eu/publication/searchRegister?core=esma_registers_radar",
                         "severity": rating_severity(a["action"], a["value"]), "detail": a.get("horizon", "")})
        return rows

    def validate(self, records):
        return [r for r in records if r["title"] and r["date"]]

    def load(self, records) -> int:
        return store.upsert("events", records)
