import json
from datetime import date

from bankcredit import learn, store


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(learn, "HINTS", tmp_path / "review" / "hints.json")
    monkeypatch.setattr(learn, "LEARNING", tmp_path / "review" / "learning.json")


def test_answer_updates_hints_and_scores_the_rules(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    item = {"id": "abc", "entity_id": "skipton-bs", "url": "https://x/p3-2025.pdf", "page": 6, "reference_date": "2025-12-31",
            "values": {"cet1_ratio": 27.9, "rwa": 9100.0, "leverage_ratio": 6.7}, "checks": [["warn", "rows identified by label only (no row numbers)"]],
            "reason": "warn:rows identified by label only"}
    ans = {"id": "abc", "entity_id": "skipton-bs", "url": "https://x/p3-2025.pdf", "page": 7, "reference_date": "2025-12-31", "currency": "GBP",
           "values": {"cet1_ratio": 28.2, "rwa": 9141.4, "leverage_ratio": 6.7}}
    rec = learn.record_answer(item, ans)
    assert rec["compared"] == 3 and rec["matched"] == 1 and set(rec["mismatches"]) == {"cet1_ratio", "rwa"}
    h = learn.hint_for("skipton-bs")
    assert h["page"] == 7 and h["currency"] == "GBP" and h["trust_labels"] is True
    assert h["last_verified"]["values"]["cet1_ratio"] == 28.2
    s = learn.summary()
    assert s["answers"] == 1 and s["agreement"] == round(1 / 3, 3) and s["entities_with_hints"] == 1


def test_skip_answer_teaches_a_filename_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    learn.record_answer({"id": "d1", "entity_id": "leeds-bs"}, {"id": "d1", "skip": True, "url": "https://x/remuneration-disclosure-2025.pdf", "note": "remuneration only"})
    assert learn.skip_matches("leeds-bs", "https://x/remuneration-disclosure-2026.pdf")
    assert not learn.skip_matches("leeds-bs", "https://x/pillar-3-2026.pdf")
    assert not learn.skip_matches("skipton-bs", "https://x/remuneration-disclosure-2026.pdf")


def test_continuity_verdicts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    learn.remember_verified("aib", date(2026, 3, 31), {"cet1_ratio": 15.1, "rwa": 60000.0, "leverage_ratio": 7.0})
    ok, msg = learn.continuity("aib", {"cet1_ratio": 15.6, "rwa": 61000.0, "leverage_ratio": 7.1}, date(2026, 6, 30))
    assert ok == "ok" and "consistent" in msg
    bad, msg = learn.continuity("aib", {"cet1_ratio": 15.6, "rwa": 6100.0}, date(2026, 6, 30))    # units slip: RWA a tenth
    assert bad == "contradiction" and "RWA" in msg
    assert learn.continuity("aib", {"cet1_ratio": 40.0}, date(2025, 6, 30)) == (None, "")          # an older document
    assert learn.continuity("nobody", {"cet1_ratio": 40.0}, date(2026, 6, 30)) == (None, "")
    # an older verified answer never overwrites a newer baseline
    learn.remember_verified("aib", date(2025, 12, 31), {"cet1_ratio": 14.0})
    assert learn.hint_for("aib")["last_verified"]["reference_date"] == "2026-03-31"


def test_answer_is_learned_once(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ans = {"id": "z9", "entity_id": "tsb", "url": "https://x/p3.pdf", "page": 3, "reference_date": "2026-06-30", "values": {"cet1_ratio": 16.0}}
    assert learn.record_answer({"id": "z9", "entity_id": "tsb", "values": {"cet1_ratio": 16.0}}, ans)["matched"] == 1
    assert learn.record_answer(None, ans) == {}
    assert learn.summary()["answers"] == 1
