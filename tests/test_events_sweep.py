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
