"""The source health check: does anything notice when a locator quietly stops working?"""
from datetime import date

from bankcredit import health


def test_every_shipped_locator_compiles_and_names_a_real_entity():
    """A pattern with a typo in it never matches and never errors: the bank simply stops being
    collected. This is the only thing standing between that and silence."""
    assert health._faults() == []


def test_states_follow_the_evidence(monkeypatch):
    import pandas as pd
    from bankcredit.models import Entity

    ents = [Entity(id=i, name=i, short_name=i, country="GB", type="bank", region="uk", active=True)
            for i in ("fresh", "stale", "nodocs", "nolocator", "excused")]
    facts = pd.DataFrame([
        {"entity_id": "fresh", "metric": "cet1_ratio", "value": 14.0, "reference_date": "2026-06-30", "source": "pillar3"},
        {"entity_id": "stale", "metric": "cet1_ratio", "value": 14.0, "reference_date": "2023-06-30", "source": "pillar3"},
        {"entity_id": "excused", "metric": "cet1_ratio", "value": 40.0, "reference_date": "2018-06-30", "source": "pillar3"},
    ])
    monkeypatch.setattr(health, "load_entities", lambda: ents)
    monkeypatch.setattr(health.store, "read", lambda t: facts if t == "facts" else pd.DataFrame())
    monkeypatch.setattr(health, "LOCATORS", [{"entity": e, "page": "https://x", "match": "y"}
                                             for e in ("fresh", "stale", "nodocs", "excused")])
    monkeypatch.setattr("bankcredit.export.capital_not_published", lambda: {"excused": {"short": "by design"}})

    state = {r["entity"]: r["state"] for r in health.report(date(2026, 9, 8))["entities"]}
    assert state == {"fresh": "ok", "stale": "overdue", "nodocs": "never",
                     "nolocator": "no source", "excused": "by design"}


def test_capital_means_what_the_score_means_by_it():
    """A US bank reporting Tier 1 leverage on average assets has capital in the score's terms;
    reporting it as a gap here would send someone chasing a document that does not exist."""
    from bankcredit.score import ALTERNATES, PILLARS
    assert set(PILLARS["capital"][1]) <= set(health.CAPITAL)
    assert ALTERNATES["leverage_ratio"][0] in health.CAPITAL
