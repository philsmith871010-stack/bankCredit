"""Smoke test for the EBA Pillar 3 Data Hub adapter (live network).

Pulls KM1 for the Netherlands and Ireland only, for the most recent reference date that
already carries the four reference banks (the newest date in the model is still inside its
four-month submission window and holds only early filers), and checks their CET1 ratios.

Run: python -m pytest tests/test_eba.py -q      (add -s to see the printed ratios and row labels)
"""
import os
import tempfile

os.environ.setdefault("BANKCREDIT_DATA", tempfile.mkdtemp(prefix="smoke-"))
os.environ.setdefault("BANKCREDIT_EBA_COUNTRIES", "Netherlands,Ireland")

import pytest  # noqa: E402

from bankcredit import store  # noqa: E402
from bankcredit.adapters.eba import EBAHubAdapter  # noqa: E402

BANKS = ["rabobank", "abn-amro", "aib", "bank-of-ireland"]


def test_km1_cet1_ratios():
    p = store.path("facts")
    if p.exists():
        p.unlink()
    adapter = EBAHubAdapter()
    dates = list(adapter.discover())
    assert dates, "no accepted reference dates discovered"
    assert dates == sorted(dates, reverse=True)

    used, cet1 = None, {}
    for ref in dates[:3]:
        raw = adapter.fetch(ref)
        recs = adapter.validate(adapter.parse(ref, raw))
        n = adapter.load(recs)
        print(f"{ref}: {len(raw)} raw facts, {len(recs)} validated, {n} loaded, stats {adapter.stats[ref]}")
        cet1 = {r.entity_id: r.value for r in recs if r.metric == "cet1_ratio" and r.entity_id in BANKS}
        if all(b in cet1 for b in BANKS):
            used = ref
            break
    assert used is not None, f"no reference date among {dates[:3]} has CET1 for all of {BANKS}; last: {cet1}"

    facts = store.read("facts")
    assert not facts.empty
    sel = facts[(facts.metric == "cet1_ratio") & (facts.reference_date == used.isoformat())]
    got = dict(zip(sel.entity_id, sel.value))
    print(f"reference date used: {used}")
    for b in BANKS:
        assert b in got, f"missing cet1_ratio for {b}"
        print(f"  {b:16s} CET1 ratio {got[b]:.2f}%")
        assert 10 <= got[b] <= 30, f"{b} cet1_ratio {got[b]} outside 10..30 percent"
    print(f"matched hub names: {sorted(adapter.matched.items())}")
    print(f"unmatched hub entities: {len(adapter.unmatched)}")
