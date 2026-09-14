import xml.etree.ElementTree as ET
from email.utils import format_datetime
from datetime import datetime, timezone

from bankcredit.adapters import events as E
from bankcredit.models import Entity


def _item(title, link="https://news.example/x"):
    now = format_datetime(datetime.now(timezone.utc))
    return ET.fromstring(f"<item><title>{title}</title><link>{link}</link><pubDate>{now}</pubDate><source>Reuters</source></item>")


def test_agency_sweep_attributes_headlines_to_named_entities():
    ents = [Entity(id="metro-bank", name="Metro Bank PLC", short_name="Metro Bank", country="GB", type="bank", region="uk", group="", lei="", tickers="", fdic_cert="", peer_group="uk_mid", active=True),
            Entity(id="tsb", name="TSB Bank plc", short_name="TSB", country="GB", type="bank", region="uk", group="", lei="", tickers="", fdic_cert="", peer_group="uk_mid", active=True)]
    rows = E.sweep_rows(ents, [_item("Fitch downgrades Metro Bank to BB- on capital shortfall"), _item("Moody's upgrades TSB Bank outlook to positive", "https://news.example/y"),
                               _item("Bank of England holds rates", "https://news.example/z")])
    by = {r["entity_id"]: r for r in rows}
    assert set(by) == {"metro-bank", "tsb"}
    assert by["metro-bank"]["severity"] in ("bad", "warn") and by["tsb"]["severity"] in ("good", "info")
    assert by["metro-bank"]["event_id"].startswith("news:")


def test_generic_first_words_need_the_full_name_and_analyst_calls_are_dropped():
    boS = Entity(id="bank-of-scotland", name="Bank of Scotland plc", short_name="Bank of Scotland", country="GB", type="bank", region="uk", group="", lei="", tickers="", fdic_cert="", peer_group="uk_large", active=True)
    barc = Entity(id="barclays", name="Barclays PLC", short_name="Barclays", country="GB", type="holding", region="uk", group="", lei="", tickers="", fdic_cert="", peer_group="uk_large", active=True)
    assert not E.keep_headline(boS, "Woori Bank leaps forward with improving credit ratings", "x")
    assert E.keep_headline(boS, "Moody's affirms Bank of Scotland deposit ratings", "x")
    assert not E.keep_headline(barc, "Barclays upgrades AutoStore on Amazon deal", "x")
    assert E.keep_headline(barc, "Fitch upgrades Barclays to A+", "x")
    assert not E.keep_headline(barc, "ASOS Plc : Upgraded to Neutral by Barclays", "x")


def test_routine_housekeeping_and_promotional_sources_are_dropped():
    hsbc = Entity(id="hsbc-holdings", name="HSBC Holdings plc", short_name="HSBC", country="GB", type="holding", region="uk", group="", lei="", tickers="", fdic_cert="", peer_group="uk_large", active=True)
    assert not E.keep_headline(hsbc, "HSBC Holdings plc share buy-back programme: transactions in week 36", "Reuters")
    assert not E.keep_headline(hsbc, "Edison International $EIX Shares Acquired by HSBC Holdings PLC", "marketbeat.com")
    assert not E.keep_headline(hsbc, "Over 2,000 runners warm up for HSBC Nairobi Marathon", "Capital FM")
    assert not E.keep_headline(hsbc, "Euro: limited gains from ECB tightening – HSBC", "fxstreet.com")
    assert E.keep_headline(hsbc, "HSBC fined £57m by PRA over deposit protection failings", "Financial Times")
    assert E.blocked_source("Kalkine Media") and E.blocked_source("TipRanks") and not E.blocked_source("Financial Times")
    gs = Entity(id="goldman-sachs", name="The Goldman Sachs Group", short_name="Goldman Sachs", country="US", type="holding", region="us_ch", group="", lei="", tickers="", fdic_cert="", peer_group="us", active=True)
    assert not E.keep_headline(gs, "Goldman Sachs backs KOSPI 12,000 as Korea earnings rise", "Chosunbiz")
    assert not E.keep_headline(gs, "Goldman Sachs Research Report Analysis: AI server upgrade", "x")
    assert E.keep_headline(gs, "Goldman Sachs fined $2bn over 1MDB fraud findings", "Reuters")


def test_same_story_from_many_outlets_collapses():
    import pandas as pd
    from bankcredit.export import _dedupe_events
    ev = pd.DataFrame([{"date": "2026-09-07", "type": "news", "title": "Deutsche Bank settles €152mn lawsuit with former executive - Financial Times", "severity": "warn"},
                       {"date": "2026-09-07", "type": "news", "title": "Deutsche Bank settles €152mn lawsuit with former executive - Reuters", "severity": "warn"},
                       {"date": "2026-09-06", "type": "news", "title": "Deutsche Bank cuts 500 jobs in Frankfurt - Reuters", "severity": "warn"},
                       {"date": "2026-09-07", "type": "rating", "title": "Fitch affirmation: Long Term IDR A", "severity": "info"}])
    out = _dedupe_events(ev)
    assert len(out) == 3


def _news(eid, when, title, severity="info"):
    return {"entity_id": eid, "event_id": f"news:{abs(hash(title)):016x}", "date": when, "type": "news",
            "title": title, "source": "Reuters", "severity": severity, "url": "https://news.example/x"}


def test_the_unjudged_headlines_are_published_for_a_run_that_has_no_checkout(monkeypatch):
    """The news review is the one job that needs a judgement rather than a rule, and the scheduled
    run that does it has no repository and no pandas. Publishing its worklist as plain JSON is what
    lets it fetch one file, judge what is in it, and write the verdicts back."""
    import pandas as pd
    from bankcredit import export

    ev = pd.DataFrame([_news("tsb", "2026-09-10", "TSB fined over outage", "warn"),
                       _news("metro-bank", "2026-09-14", "Metro Bank downgraded", "bad"),
                       _news("tsb", "2026-09-12", "TSB sponsors a football club"),
                       {"entity_id": "tsb", "event_id": "rating:1", "date": "2026-09-13", "type": "rating",
                        "title": "Fitch affirms", "source": "Fitch", "severity": "info", "url": ""}])
    judged = {ev.event_id[0]: {"keep": False, "severity": None, "why": "old news"}}
    monkeypatch.setattr("bankcredit.adapters.events.load_verdicts", lambda: judged)

    out = export.news_todo(ev, {"tsb": "TSB", "metro-bank": "Metro Bank"})
    assert out["unjudged"] == 2, "the judged headline and the rating action are not work"
    assert [r["date"] for r in out["rows"]] == ["2026-09-14", "2026-09-12"], "newest first"
    assert out["rows"][0]["short"] == "Metro Bank", "named, because the judge reads this"
    assert set(out["rows"][0]) == {"event_id", "entity_id", "short", "date", "severity", "source", "title"}
    assert all("url" not in r for r in out["rows"]), "400 Google News redirects is most of the file"


def test_the_worklist_is_capped_so_one_run_is_one_sitting():
    import pandas as pd
    from bankcredit import export
    ev = pd.DataFrame([_news("tsb", f"2026-09-{d:02d}", f"headline {d}") for d in range(1, 29)])
    out = export.news_todo(ev, {}, limit=10)
    assert out["unjudged"] == 28, "it still says how much is really owed"
    assert len(out["rows"]) == 10


def test_a_sitting_of_verdicts_can_be_written_as_its_own_file(tmp_path, monkeypatch):
    """The cloud run that judges headlines has no checkout. Rewriting the shared 100 KB book to add
    forty entries means reading it, holding it and racing whoever else is writing it; a fragment is
    write-only. The book and the fragments read as one, later files winning."""
    import json
    from bankcredit.adapters import events as E
    book = tmp_path / "news_verdicts.json"
    parts = tmp_path / "verdicts"
    parts.mkdir()
    book.write_text(json.dumps({"news:1": {"keep": True, "why": "downgrade"},
                                "news:2": {"keep": False, "why": "buy-back"}}))
    (parts / "2026-09-15.json").write_text(json.dumps({"news:3": {"keep": True, "why": "fine"}}))
    (parts / "2026-09-16.json").write_text(json.dumps({"news:2": {"keep": True, "why": "on reflection"}}))
    (parts / "broken.json").write_text("{not json")
    monkeypatch.setattr(E, "VERDICTS", book)
    monkeypatch.setattr(E, "VERDICT_PARTS", parts)

    got = E.load_verdicts()
    assert set(got) == {"news:1", "news:2", "news:3"}
    assert got["news:2"]["why"] == "on reflection", "a judgement can be revisited"
    assert got["news:3"]["keep"] is True, "one unreadable sitting must not cost the others"


def test_no_verdicts_anywhere_is_not_an_error(tmp_path, monkeypatch):
    from bankcredit.adapters import events as E
    monkeypatch.setattr(E, "VERDICTS", tmp_path / "nothing.json")
    monkeypatch.setattr(E, "VERDICT_PARTS", tmp_path / "nowhere")
    assert E.load_verdicts() == {}
