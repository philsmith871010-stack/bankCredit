"""A source nobody has turned on is not a source that failed.

FRED's keyless CSV endpoint answers a laptop and not a hosted runner: from the pipeline it hangs
and then closes the connection. So every scheduled run logged this adapter as failed, collected
nothing, and printed a red line on the status page every morning. There are no FRED rows in the
store at all and there never were - and a red line that is always there is the one nobody reads.
"""
from __future__ import annotations

import pandas as pd
import pytest

from bankcredit import store
from bankcredit.adapters.base import Adapter
from bankcredit.adapters.fred import FredAdapter


def last_run(source: str) -> dict:
    runs = store.read("runs")
    mine = runs[runs["source"] == source].sort_values("finished")
    return mine.iloc[-1].to_dict() if len(mine) else {}


def test_without_a_key_the_adapter_skips_and_says_why(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    rows, status = FredAdapter().run()
    assert (rows, status) == (0, "skipped")
    run = last_run("fred")
    assert run["status"] == "skipped", "not a failure: nobody has configured it"
    assert "FRED_API_KEY" in run["message"], run["message"]


def test_with_a_key_it_asks_the_api_and_stores_basis_points(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    a = FredAdapter()
    assert a.skip() is None
    asked = {}

    class Reply:
        def raise_for_status(self): pass
        def json(self): return {"observations": [
            {"date": "2026-09-10", "value": "0.83"},
            {"date": "2026-09-09", "value": "."},          # FRED's own marker for no observation
            {"date": "2026-09-08", "value": "0.85"}]}

    def get(url, **kw):
        asked.update(url=url, **kw.get("params", {}))
        return Reply()

    a.session = type("S", (), {"get": staticmethod(get)})()
    rows = a.validate(a.parse("BAMLC0A0CM", a.fetch("BAMLC0A0CM")))
    assert asked["url"].startswith("https://api.stlouisfed.org/fred/series/observations")
    assert asked["api_key"] == "test-key" and asked["series_id"] == "BAMLC0A0CM"
    # percent on the wire, basis points in the store, and a "." is not an observation
    assert [(r["date"], r["value"], r["unit"]) for r in rows] == [
        ("2026-09-10", 83.0, "bp"), ("2026-09-08", 85.0, "bp")]
    assert {r["source"] for r in rows} == {"FRED"}


def test_a_skip_is_reported_apart_from_ok_and_from_failed():
    """The three states have to stay distinguishable, because the status page colours them."""
    class Fine(Adapter):
        name = "fine-source"
        def discover(self): return ["x"]
        def fetch(self, item): return "raw"
        def parse(self, item, raw): return [{"series_id": "S", "date": "2026-01-01", "value": 1.0,
                                             "unit": "bp", "label": "l", "source": "T"}]
        def load(self, records): return len(records)

    class Off(Fine):
        name = "off-source"
        def skip(self): return "no credential"

    assert Fine().run() == (1, "ok")
    assert Off().run() == (0, "skipped")
    assert last_run("off-source")["message"] == "no credential"
    assert last_run("off-source")["rows"] == 0


def test_the_site_reports_a_skip_apart_from_a_failure():
    """The status table colours the three states, and a skip must not read as a red line."""
    from bankcredit.site import build
    rows = [{"source": "fred", "status": "skipped", "rows": 0, "message": "no FRED_API_KEY",
             "finished": "2026-09-11T09:48:00"},
            {"source": "esma", "status": "ok", "rows": 1136, "message": "",
             "finished": "2026-09-11T09:41:00"}]
    html = build.page_status({"runs": rows, "documents": [], "review": []},
                             {"rows": []}, "2026-09-11T10:00:00Z", inner=True)
    assert "chip-muted" in html and "skipped" in html
    assert "chip-bad" not in html, "nobody has configured it; that is not a failure"
