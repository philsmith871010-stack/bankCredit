"""The agencies' own ratings, quoted beside the average.

The public site shows the average and the weakest of the three main agencies and never says
which said what (composite.py). This module is the other view: for each name, the current
long-term rating and outlook, and the current short-term rating, that Fitch, S&P and Moody's
each publish, with the agency named, the date, and a link to the source.

It is built as a quotation, not a feed, because that is the shape the law and the precedents
support (docs/attributed-ratings.md): current ratings only, the three main agencies only, one
record per agency per name, the agency acknowledged, no history by agency, no download. It is
written to one file outside the public data, `members/ratings.json`, only when the build is
asked for it, so a build can be made without it, and a login later has one path to protect.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .composite import AGENCIES

ENV = "COUNTERPARTY_ATTRIBUTED"        # set to any value at build time to write the members file
AGENCY_NAME = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's"}
# Where a reader is sent for the source: the agencies' own public sites, and the register
# every rating here was read from.
AGENCY_URL = {"fitch": "https://www.fitchratings.com/", "sp": "https://www.spglobal.com/ratings/",
              "moodys": "https://ratings.moodys.com/"}
ERP_URL = "https://registers.esma.europa.eu/publication/searchRegister?core=esma_registers_radar"
PREF = {"idr": 0, "issuer": 1, "deposit": 2, "counterparty": 3, "resolution_counterparty": 4}
TYPE_WORD = {"idr": "issuer default rating", "issuer": "issuer credit rating", "deposit": "deposit rating",
             "counterparty": "counterparty rating", "resolution_counterparty": "resolution counterparty rating"}

# Shown beside the ratings, on the page and in the file, so the basis travels with the data.
BASIS = (
    "These are the current ratings Fitch, S&P and Moody's each publish on this name, quoted from "
    "the public record: every rating is filed on the ESMA European Rating Platform under Article 10 "
    "of the Credit Rating Agencies Regulation, which requires it to be disclosed publicly and "
    "non-selectively, and Article 13, which requires that disclosure to be free of charge. They are "
    "shown as a quotation, current ratings only, with the agency acknowledged and a link to the "
    "source, for the reader's own use in checking a counterparty. No history by agency "
    "is shown and no download is offered. Nothing here is licensed, approved or endorsed by any "
    "agency; a rating is the agency's opinion, not a recommendation, and the agency may change or "
    "withdraw it at any time. This basis is our own reading of the law and of the agencies' terms "
    "and has not been agreed with any agency. If an agency objects, or the law or the terms change "
    "so that this view can no longer be shown, it will be withdrawn without notice, and no process "
    "should depend on it remaining. What you do with what you see here, including any onward use, "
    "is your own responsibility."
)


def rows(active, ratings: pd.DataFrame) -> dict[str, list[dict]]:
    """{entity id: [{agency, name, lt, type, outlook, st, date, url}]}, the three main agencies
    only, the headline long-term rating each holds today and its latest short-term rating."""
    out: dict[str, list[dict]] = {}
    if ratings is None or ratings.empty:
        return out
    r = ratings[ratings.agency.isin(AGENCIES)]
    for e in active:
        mine = r[r.entity_id == e.id]
        if mine.empty:
            continue
        recs = []
        for ag in AGENCIES:
            g = mine[mine.agency == ag]
            lt = g[g.horizon == "long"].assign(_p=lambda x: x.rating_type.map(PREF).fillna(9))
            lt = lt.sort_values(["_p", "action_date"], ascending=[True, False])
            if lt.empty:
                continue
            l0 = lt.iloc[0]
            st = g[g.horizon == "short"].sort_values("action_date", ascending=False)
            recs.append({"agency": ag, "name": AGENCY_NAME[ag], "lt": l0.value,
                         "type": TYPE_WORD.get(l0.rating_type, str(l0.rating_type or "").replace("_", " ")),
                         "outlook": l0.outlook or "", "st": st.iloc[0].value if not st.empty else "",
                         "date": str(l0.action_date)[:10], "url": AGENCY_URL[ag]})
        if recs:
            out[e.id] = recs
    return out


def write(path: Path, active, ratings: pd.DataFrame) -> int:
    """The members file: one small JSON the profile and the dialog fetch. Returns the count."""
    data = rows(active, ratings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                                "source": ERP_URL, "basis": BASIS, "rows": data},
                               separators=(",", ":"), ensure_ascii=False))
    return len(data)
