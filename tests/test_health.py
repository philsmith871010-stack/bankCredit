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


def test_the_overdue_window_follows_the_filers_cadence(monkeypatch):
    """An annual filer is between reports for most of the year and a quarterly filer two quarters
    behind has broken; one flat window cannot say both. The cadence is read from the gaps between
    the reference dates of the documents whose figures were loaded."""
    import pandas as pd
    from bankcredit.models import Entity

    ents = [Entity(id=i, name=i, short_name=i, country="GB", type="bank", region="uk", active=True)
            for i in ("annual", "quarterly", "lone")]
    today = date(2026, 11, 3)
    facts = pd.DataFrame([
        {"entity_id": "annual", "metric": "cet1_ratio", "value": 20.0, "reference_date": "2025-09-29", "source": "pillar3"},     # 400 days
        {"entity_id": "quarterly", "metric": "cet1_ratio", "value": 14.0, "reference_date": "2026-02-26", "source": "pillar3"},  # 250 days
        {"entity_id": "lone", "metric": "cet1_ratio", "value": 14.0, "reference_date": "2026-02-26", "source": "pillar3"},       # 250 days
    ])
    docs = pd.DataFrame(
        [{"entity_id": "annual", "status": "loaded", "reference_date": d} for d in ("2022-09-30", "2023-09-30", "2024-09-30", "2025-09-29")]
        + [{"entity_id": "quarterly", "status": "loaded", "reference_date": d} for d in ("2025-05-31", "2025-08-31", "2025-11-30", "2026-02-26")]
        + [{"entity_id": "quarterly", "status": "no_km1", "reference_date": None}]
        + [{"entity_id": "lone", "status": "loaded", "reference_date": "2026-02-26"}])
    monkeypatch.setattr(health, "load_entities", lambda: ents)
    monkeypatch.setattr(health.store, "read", lambda t: facts if t == "facts" else docs if t == "documents" else pd.DataFrame())
    monkeypatch.setattr(health, "LOCATORS", [{"entity": e, "page": "https://x", "match": "y"} for e in ("annual", "quarterly", "lone")])
    monkeypatch.setattr("bankcredit.export.capital_not_published", lambda: {})

    rows = {r["entity"]: r for r in health.report(today)["entities"]}
    assert (rows["annual"]["cadence"], rows["annual"]["age_days"], rows["annual"]["state"]) == ("annual", 400, "ok")
    assert (rows["quarterly"]["cadence"], rows["quarterly"]["age_days"], rows["quarterly"]["state"]) == ("quarterly", 250, "overdue")
    # one dated document is too few to tell, so the flat 300-day window still applies
    assert (rows["lone"]["cadence"], rows["lone"]["state"]) == ("unknown", "ok")


def test_cadence_reads_the_median_gap():
    assert health.cadence(["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]) == "quarterly"
    assert health.cadence(["2024-12-31", "2025-06-30", "2025-12-31"]) == "half-yearly"
    assert health.cadence(["2023-12-31", "2024-12-31", "2025-12-31"]) == "annual"
    assert health.cadence(["2025-12-31"]) == "unknown"
    assert health.cadence([]) == "unknown"


def test_capital_means_what_the_score_means_by_it():
    """A US bank reporting Tier 1 leverage on average assets has capital in the score's terms;
    reporting it as a gap here would send someone chasing a document that does not exist."""
    from bankcredit.score import ALTERNATES, PILLARS
    assert set(PILLARS["capital"][1]) <= set(health.CAPITAL)
    assert ALTERNATES["leverage_ratio"][0] in health.CAPITAL
