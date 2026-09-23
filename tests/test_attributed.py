"""The agencies' own ratings: current only, the three only, the basis attached."""
from __future__ import annotations

import json

import pandas as pd

from bankcredit import attributed
from bankcredit.entities import Entity


def ent(i):
    return Entity(id=i, name=i, short_name=i, country="GB", type="bank", region="uk", active=True)


def table(*spec):
    return pd.DataFrame([{"entity_id": e, "agency": a, "horizon": h, "rating_type": t, "value": v,
                          "outlook": o, "action_date": d} for e, a, h, t, v, o, d in spec])


def test_one_current_record_per_main_agency_with_the_source_named():
    r = table(("x", "fitch", "long", "idr", "A+", "stable", "2026-05-12"),
              ("x", "fitch", "long", "deposit", "AA-", "", "2026-05-12"),
              ("x", "fitch", "short", "idr", "F1", "", "2026-05-12"),
              ("x", "moodys", "long", "deposit", "A1", "negative", "2025-11-02"),
              ("x", "dbrs", "long", "issuer", "AA", "stable", "2026-01-01"),
              ("y", "sp", "long", "issuer", "BBB", "watch negative", "2026-09-16"))
    out = attributed.rows([ent("x"), ent("y"), ent("z")], r)
    assert set(out) == {"x", "y"}, "a name none of the three rates has no record"
    x = out["x"]
    assert [a["agency"] for a in x] == ["fitch", "moodys"], "DBRS is not quoted"
    assert x[0] == {"agency": "fitch", "name": "Fitch", "lt": "A+", "type": "issuer default rating", "outlook": "stable",
                    "st": "F1", "date": "2026-05-12", "url": attributed.AGENCY_URL["fitch"]}, "the issuer default rating ahead of the deposit rating"
    assert x[1]["lt"] == "A1" and x[1]["st"] == "" and x[1]["type"] == "deposit rating"
    assert out["y"][0]["outlook"] == "watch negative"
    assert attributed.rows([ent("x")], pd.DataFrame()) == {}


def test_the_members_file_carries_the_basis_and_nothing_historical(tmp_path):
    r = table(("x", "sp", "long", "issuer", "A", "stable", "2026-01-01"))
    n = attributed.write(tmp_path / "members" / "ratings.json", [ent("x")], r)
    j = json.loads((tmp_path / "members" / "ratings.json").read_text())
    assert n == 1 and set(j) == {"generated", "source", "basis", "rows"}
    assert "withdrawn without notice" in j["basis"] and "free of charge" in j["basis"]
    assert j["source"].startswith("https://registers.esma.europa.eu/")
    assert list(j["rows"]["x"][0]) == ["agency", "name", "lt", "type", "outlook", "st", "date", "url"], "no history, no actions"
