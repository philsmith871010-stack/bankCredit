"""Proof of concept: read EBA Pillar 3 Data Hub (P3DH) data from the public EDAP portal.

The portal is a Power BI report embedded in an ASP.NET app. The page inlines a public embed
token; with it, read-only semantic queries can be sent to the Power BI cluster. This is an
unofficial route (no EBA API exists as of September 2026) and may break without notice.
Encoding logic follows the public notebook at github.com/at621/snippets (pillar3_hub_overview).

Usage: python research/p3dh_probe.py [reference_date]   (default 2025-12-31)
Requires only `requests`.
"""
import collections
import datetime as dt
import json
import sys
import uuid

import requests

P3DH_URL = "https://edap-public.eba.europa.eu/Report/index/MTE1"
REPORT = "f0de0c7c-c532-4b55-9bef-da99423cf672"
DATASET = "d9c4b646-c0e6-4b73-887f-8f6702855ae2"
MODEL = 5131315
HOST = "https://wabi-west-europe-d-primary-redirect.analysis.windows.net"
KM1 = "K_61.00"

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0 Safari/537.36"


def get_token() -> str:
    page = S.get(P3DH_URL, allow_redirects=True, timeout=120)
    page.raise_for_status()
    i = page.text.find("H4sI")
    if i < 0:
        raise RuntimeError("no embed token found in page")
    return page.text[i:page.text.index('"', i)]


def src(alias, entity):
    return {"Name": alias, "Entity": entity, "Type": 0}


def col(alias, prop):
    return {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}, "Name": f"{alias}.{prop}"}


def measure(alias, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}, "Name": f"{alias}.{prop}"}


def eq(alias, prop, literal):
    return {"Condition": {"Comparison": {"ComparisonKind": 0,
            "Left": {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}},
            "Right": {"Literal": {"Value": literal}}}}}


def decode_rows(text):
    payload = json.loads(text.lstrip("﻿"))
    shapes = payload["results"][0]["result"]["data"].get("dsr", {}).get("DataShapes")
    if shapes and "odata.error" in shapes[0]:
        raise RuntimeError(shapes[0]["odata.error"]["message"]["value"])
    out = []
    for result in payload["results"]:
        for ds in result["result"]["data"].get("dsr", {}).get("DS", []):
            dicts, specs = ds.get("ValueDicts", {}), None
            for phase in ds.get("PH", []):
                for rows in phase.values():
                    prev = []
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

                        row = []
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
    def __init__(self):
        self.headers = {"Authorization": f"EmbedToken {get_token()}",
                        "Content-Type": "application/json;charset=UTF-8",
                        "X-PowerBI-ResourceKey": REPORT}

    def query(self, sources, selections, filters=(), limit=30000):
        cmd = {"SemanticQueryDataShapeCommand": {
            "Query": {"Version": 2, "From": list(sources), "Select": list(selections), "Where": list(filters)},
            "Binding": {"Primary": {"Groupings": [{"Projections": list(range(len(selections)))}]},
                        "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": limit}}},
                        "Version": 1}}}
        body = {"version": "1.0.0",
                "queries": [{"Query": {"Commands": [cmd]}, "QueryId": "",
                             "ApplicationContext": {"DatasetId": DATASET, "Sources": [{"ReportId": REPORT, "VisualId": "v"}]}}],
                "cancelQueries": [], "modelId": MODEL}
        h = dict(self.headers, ActivityId=str(uuid.uuid4()), RequestId=str(uuid.uuid4()))
        r = S.post(f"{HOST}/explore/querydata?synchronous=true", headers=h, json=body, timeout=180)
        r.raise_for_status()
        return decode_rows(r.text)


FACT_SOURCES = [src(a, e) for a, e in [("e", "dm_Entity"), ("t", "dm_Template"), ("i", "dm_ReportInstance"),
                                       ("tb", "dm_Table"), ("r", "dm_Row"), ("c", "dm_Column"),
                                       ("f", "fact_Value"), ("v", "Measure P3")]]
FACT_SELECT = [col("e", "ENT_NAM"), col("e", "EntityCode"), col("e", "Country"), col("i", "ReferenceDate"),
               col("i", "IsCurrent"), col("i", "IsAccepted"), col("tb", "TableCode"), col("r", "HeaderCode"),
               col("c", "HeaderCode"), measure("v", "FactValue")]


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else "2025-12-31"
    hub = Hub()
    ents = hub.query([src("e", "dm_Entity")], [col("e", "ENT_NAM"), col("e", "EntityCode"), col("e", "Country"), col("e", "InstitutionType")])
    print(f"entities: {len(ents)}")
    print("by country:", collections.Counter(r[2] for r in ents).most_common(10))
    templates = hub.query([src("t", "dm_Template")], [col("t", "TemplateCode"), col("t", "TemplateName")])
    print(f"templates: {len(templates)}; KM1 is", [r for r in templates if r[0] == KM1])
    inst = hub.query([src("i", "dm_ReportInstance")], [col("i", "ReferenceDate"), col("i", "IsCurrent"), col("i", "IsAccepted")])
    dates = sorted({dt.datetime.utcfromtimestamp(r[0] / 1000).date().isoformat() for r in inst if r[1] == 1 and r[2] == 1})
    print("reference dates with current accepted instances:", dates)
    km1 = hub.query(FACT_SOURCES, FACT_SELECT,
                    [eq("t", "TemplateCode", f"'{KM1}'"), eq("i", "ReferenceDate", f"datetime'{ref}T00:00:00'"), eq("i", "IsCurrent", "1L")])
    banks = {r[1] for r in km1}
    print(f"KM1 facts at {ref}: {len(km1)} (window-capped at 30000; page by country for full pull), banks: {len(banks)}")
    # CET1 ratio is KM1 row 0050, current period column 0010; ratios are decimals, amounts in EUR
    cet1 = {r[0]: r[9] for r in km1 if r[7] == "0050" and r[8] == "0010" and r[0]}
    for name in sorted(cet1)[:10]:
        print(f"  {name[:50]:50s} CET1 ratio {cet1[name]}")
    json.dump(km1, open(f"km1_{ref}.json", "w"))


if __name__ == "__main__":
    main()
