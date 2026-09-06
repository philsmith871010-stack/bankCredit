"""Read-only client for the Power BI model behind the EBA Pillar 3 Data Hub (P3DH).

The public EDAP page inlines a Power BI embed token (rotates roughly hourly). With it,
semantic queries can be POSTed to the Power BI cluster against the hub's star schema
(fact_Value, dm_Entity, dm_ReportInstance, dm_Template, dm_Table, dm_Row, dm_Column).
This is an unofficial route (no EBA API exists as of September 2026) and may break without
notice. Encoding follows the public notebook at github.com/at621/snippets and the working
proof of concept in research/p3dh_probe.py.

Every query is capped at a 30,000-row window by the service; callers must page.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

import requests

log = logging.getLogger("bankcredit.powerbi")

P3DH_URL = "https://edap-public.eba.europa.eu/Report/index/MTE1"
REPORT = "f0de0c7c-c532-4b55-9bef-da99423cf672"
DATASET = "d9c4b646-c0e6-4b73-887f-8f6702855ae2"
MODEL = 5131315
HOST = "https://wabi-west-europe-d-primary-redirect.analysis.windows.net"
WINDOW = 30000


def get_token(session: requests.Session) -> str:
    """Scrape the public embed token from the EDAP report page."""
    page = session.get(P3DH_URL, allow_redirects=True, timeout=120)
    page.raise_for_status()
    i = page.text.find("H4sI")
    if i < 0:
        raise RuntimeError("no Power BI embed token found in the EDAP page")
    return page.text[i:page.text.index('"', i)]


# ---- query-building helpers -------------------------------------------------------

def src(alias: str, entity: str) -> dict:
    return {"Name": alias, "Entity": entity, "Type": 0}


def col(alias: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}, "Name": f"{alias}.{prop}"}


def measure(alias: str, prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}, "Name": f"{alias}.{prop}"}


def eq(alias: str, prop: str, literal: str) -> dict:
    """Equality filter. `literal` is a DAX-style literal: 'text', 1L, true, datetime'2026-03-31T00:00:00'."""
    return {"Condition": {"Comparison": {"ComparisonKind": 0,
            "Left": {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}},
            "Right": {"Literal": {"Value": literal}}}}}


def text(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def datetime_lit(iso_date: str) -> str:
    return f"datetime'{iso_date}T00:00:00'"


# ---- response decoding ------------------------------------------------------------

def decode_rows(payload_text: str) -> list[list]:
    """Expand Power BI's compressed DSR row encoding into plain lists (one per row)."""
    payload = json.loads(payload_text.lstrip("﻿"))
    shapes = payload["results"][0]["result"]["data"].get("dsr", {}).get("DataShapes")
    if shapes and "odata.error" in shapes[0]:
        raise RuntimeError(shapes[0]["odata.error"]["message"]["value"])
    out: list[list] = []
    for result in payload["results"]:
        for ds in result["result"]["data"].get("dsr", {}).get("DS", []):
            dicts, specs = ds.get("ValueDicts", {}), None
            for phase in ds.get("PH", []):
                for rows in phase.values():
                    prev: list = []
                    for enc in rows:
                        specs = enc.get("S", specs)
                        if specs is None:
                            continue
                        rep = enc.get("R", 0)
                        nulls = next((enc[k] for k in ("Ø", "�") if k in enc), 0)

                        def res(v, sp):
                            n = sp.get("DN")
                            if n in dicts and isinstance(v, int) and 0 <= v < len(dicts[n]):
                                return dicts[n][v]
                            return v

                        row: list = []
                        if "C" in enc:
                            vals, t = enc["C"], 0
                            for pos, sp in enumerate(specs):
                                if nulls >> pos & 1:
                                    row.append(None)
                                elif rep >> pos & 1 or t >= len(vals):
                                    row.append(prev[pos] if pos < len(prev) else None)
                                else:
                                    row.append(res(vals[t], sp))
                                    t += 1
                        else:
                            for pos, sp in enumerate(specs):
                                k = sp.get("N", f"G{pos}")
                                if k in enc:
                                    row.append(res(enc[k], sp))
                                elif nulls >> pos & 1:
                                    row.append(None)
                                else:
                                    row.append(prev[pos] if pos < len(prev) else None)
                        out.append(row)
                        prev = row
    return out


class Hub:
    """Thin client: one embed token, refreshed on 401/403, plus a `query` method."""

    def __init__(self, session: requests.Session | None = None, host: str = HOST):
        self.session = session or requests.Session()
        self.host = host
        self.token: str | None = None
        self.calls = 0

    def _headers(self) -> dict:
        if self.token is None:
            self.token = get_token(self.session)
        return {"Authorization": f"EmbedToken {self.token}",
                "Content-Type": "application/json;charset=UTF-8",
                "X-PowerBI-ResourceKey": REPORT,
                "ActivityId": str(uuid.uuid4()), "RequestId": str(uuid.uuid4())}

    def query(self, sources, selections, filters=(), limit: int = WINDOW) -> list[list]:
        """Run one semantic query; returns rows ordered like `selections` (max `limit` rows)."""
        cmd = {"SemanticQueryDataShapeCommand": {
            "Query": {"Version": 2, "From": list(sources), "Select": list(selections), "Where": list(filters)},
            "Binding": {"Primary": {"Groupings": [{"Projections": list(range(len(selections)))}]},
                        "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": limit}}},
                        "Version": 1}}}
        body = {"version": "1.0.0",
                "queries": [{"Query": {"Commands": [cmd]}, "QueryId": "",
                             "ApplicationContext": {"DatasetId": DATASET,
                                                    "Sources": [{"ReportId": REPORT, "VisualId": "v"}]}}],
                "cancelQueries": [], "modelId": MODEL}
        last: Exception | None = None
        for attempt in range(3):
            try:
                self.calls += 1
                r = self.session.post(f"{self.host}/explore/querydata?synchronous=true",
                                      headers=self._headers(), json=body, timeout=180)
                if r.status_code in (401, 403):
                    self.token = None          # token expired or rotated; fetch a fresh one
                    r.raise_for_status()
                if r.status_code == 429 or r.status_code >= 500:
                    r.raise_for_status()
                r.raise_for_status()
                return decode_rows(r.text)
            except (requests.RequestException, ValueError, KeyError) as exc:
                last = exc
                log.warning("power bi query failed (attempt %d): %s", attempt + 1, exc)
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"power bi query failed after retries: {last}")
