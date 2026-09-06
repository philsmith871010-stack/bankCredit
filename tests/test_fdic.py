"""Smoke test: run the FDIC adapter for Wells Fargo (CERT 3511) against a temp data dir."""
import os
import tempfile
from datetime import date

os.environ.setdefault("BANKCREDIT_DATA", tempfile.mkdtemp(prefix="fdic-smoke-"))

from bankcredit import store  # noqa: E402  (must come after the env var is set)
from bankcredit.adapters.fdic import FDICAdapter  # noqa: E402


def test_wells_fargo_smoke():
    adapter = FDICAdapter()
    wfc = [e for e in adapter.discover() if e.fdic_cert == "3511"]
    assert len(wfc) == 1, "expected exactly one entity with CERT 3511 (Wells Fargo)"
    item = wfc[0]

    raw = adapter.fetch(item)
    records = adapter.validate(adapter.parse(item, raw))
    written = adapter.load(records)
    assert written == len(records) > 0

    facts = store.read("facts")
    cet1 = facts[(facts.entity_id == item.id) & (facts.metric == "cet1_ratio")]
    assert len(cet1) >= 10, f"only {len(cet1)} cet1_ratio facts"
    assert cet1.reference_date.nunique() == len(cet1)

    latest_date = date.fromisoformat(cet1.reference_date.max())
    assert latest_date >= date(2026, 6, 30), latest_date

    latest = facts[(facts.entity_id == item.id) & (facts.reference_date == cet1.reference_date.max())]
    print(f"\nWells Fargo (CERT 3511) latest quarter {latest_date}, {len(latest)} facts:")
    print(latest[["metric", "value", "unit", "currency", "basis"]].to_string(index=False))

    # second fetch on the same day must come from the on-disk cache
    assert adapter._cache_path("3511").exists()
