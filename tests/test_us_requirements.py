"""US capital requirements: every US entity has one, built from its parts, in force from its date."""
import csv
import json
from pathlib import Path

from bankcredit import us_requirements as ur

REF = Path(__file__).resolve().parents[1] / "data" / "reference" / "us-capital-requirements.json"
TABLE = ur.load(REF)


def _us_entities():
    rows = csv.DictReader(open(Path(__file__).resolve().parents[1] / "data" / "entities.csv"))
    return {r["id"]: r for r in rows if r["country"] == "US" and r["region"] == "us_ch"}


def test_every_us_entity_has_a_requirement_and_nothing_else_does():
    assert set(TABLE) == set(_us_entities())


def test_each_requirement_is_the_sum_of_its_parts():
    """CET1 4.5 + SCB + GSIB and total 8 + SCB + GSIB for a holding company (the Fed's own CET1 column
    is that sum); 7.0 / 10.5 for an insured bank, which carries only the 2.5 conservation buffer."""
    ents = _us_entities()
    for ent, periods in TABLE.items():
        for p in periods:
            assert p["source"].startswith("https://"), ent
            if ents[ent]["fdic_cert"]:
                assert (p["cet1_requirement"], p["overall_capital_requirement"]) == (7.0, 10.5), ent
            else:
                buf = p["scb"] + p["gsib_surcharge"]
                assert p["scb"] >= 2.5, ent
                assert abs(p["cet1_requirement"] - (4.5 + buf)) < 1e-9, ent
                assert abs(p["overall_capital_requirement"] - (8 + buf)) < 1e-9, ent
                assert "federalreserve.gov" in p["source"], ent


def test_a_period_holds_from_its_effective_date_until_the_next():
    """Goldman's surcharge rose from 3.0 to 3.5 on 1 January 2026; its SCB of 3.4 dates from 1 October 2025."""
    got = ur.series_for("goldman-sachs", ["2025-06-30", "2025-12-31", "2026-03-31", "2026-06-30"], TABLE)
    assert [(p["d"], p["v"]) for p in got["cet1_requirement"]] == [("2025-12-31", 10.9), ("2026-03-31", 11.4), ("2026-06-30", 11.4)]
    assert [p["v"] for p in got["overall_capital_requirement"]] == [14.4, 14.9, 14.9]
    assert all(p["doc"].startswith("https://www.federalreserve.gov/") for p in got["cet1_requirement"])


def test_series_points_have_the_export_shape():
    pts = ur.series_for("citibank", ["2026-06-30"], TABLE)["overall_capital_requirement"]
    assert set(pts[0]) == {"d", "v", "src", "basis", "doc", "page", "method", "conf"}
    assert pts[0]["v"] == 10.5


def test_an_entity_without_a_requirement_gets_nothing(tmp_path):
    assert ur.series_for("barclays", ["2026-06-30"], TABLE) == {}
    assert ur.load(tmp_path / "missing.json") == {}
    p = tmp_path / "one.json"
    p.write_text(json.dumps({"_note": "x", "a": {"effective": "2026-01-01", "cet1_requirement": 7.0, "overall_capital_requirement": 10.5}}))
    assert ur.load(p)["a"][0]["cet1_requirement"] == 7.0, "a single period need not be a list"


def test_facts_for_gives_fact_records():
    fs = ur.facts_for("citigroup", ["2026-06-30"], TABLE)
    assert {(f.metric, f.value) for f in fs} == {("cet1_requirement", 11.6), ("overall_capital_requirement", 15.1)}
