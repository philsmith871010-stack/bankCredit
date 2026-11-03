"""The events feed is the record and nothing else: the agencies' own actions from the ESMA register
and the Pillar 3 reports collected. Headlines were collected too, from Google News, until
3 November 2026, when a review of the 3,214 held found about one in fourteen bore on a deposit
decision (docs/news-removed.md). These tests hold the line that none comes back by a side door."""
from __future__ import annotations

from datetime import date

import pandas as pd

from bankcredit.adapters import events as E


def test_the_collector_asks_the_register_and_the_documents_and_nothing_else(monkeypatch):
    adapter = E.EventsAdapter.__new__(E.EventsAdapter)
    adapter.entities = []
    assert list(adapter.discover()) == ["documents"], "no headline search, no agency sweep"
    assert not hasattr(E, "GNEWS"), "the Google News endpoint is gone"


def test_a_rating_action_is_parsed_with_the_agencys_own_severity():
    from bankcredit.models import Entity
    e = Entity(id="tsb", name="TSB Bank plc", short_name="TSB", country="GB", type="bank", region="uk", group="",
               lei="", tickers="", fdic_cert="", peer_group="uk_mid", active=True)
    adapter = E.EventsAdapter.__new__(E.EventsAdapter)
    rows = adapter.parse(e, {"actions": [{"date": date(2026, 10, 1), "agency": "fitch", "action": "Downgrade",
                                          "rating_name": "Long-term issuer default rating", "value": "A-",
                                          "event_id": "x1", "horizon": "long"}]})
    assert [r["type"] for r in rows] == ["rating"]
    assert rows[0]["severity"] == "warn" and rows[0]["source"] == "ESMA European Rating Platform"


def test_stored_headlines_never_reach_a_page(monkeypatch, tmp_path):
    """The rows collected before the change stay in the table; the export drops them, once."""
    from bankcredit import export
    ev = pd.DataFrame([
        {"entity_id": "tsb", "event_id": "news:1", "date": "2026-10-20", "type": "news", "title": "TSB fined - FT",
         "source": "FT", "severity": "warn", "url": "https://x", "detail": ""},
        {"entity_id": "tsb", "event_id": "esma:1", "date": "2026-10-21", "type": "rating", "title": "Fitch downgrade: A-",
         "source": "ESMA European Rating Platform", "url": "https://y", "severity": "warn", "detail": "long"},
    ])
    kept = export.public_events(ev)
    kept = kept[kept.type != "news"]      # the line export_json applies, checked against the source below
    assert list(kept.type) == ["rating"]
    src = (export.__file__)
    assert 'events = events[events.type != "news"]' in open(src).read()
