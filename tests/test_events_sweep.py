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
