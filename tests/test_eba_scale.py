"""Offline: the hub's amounts are EUR units, except from the few filers that send millions."""
import datetime as dt

from bankcredit.adapters import eba


def test_a_filing_already_in_millions_is_not_divided_again(monkeypatch):
    a = eba.EBAHubAdapter.__new__(eba.EBAHubAdapter)
    monkeypatch.setattr(a, "load_row_labels", lambda: {}, raising=False)
    a.match = lambda name, lei, country: {"LBP": "la-banque-postale", "BIG": "big-bank"}[name]
    a.unmatched, a.matched, a.entities, a.stats = __import__("collections").Counter(), {}, [], {}
    code = {m: c for c, (m, k) in eba.ROW_MAP.items()}
    rows = []
    for name, rwa, cet1 in (("LBP", "96061", "17516"), ("BIG", "100031084057", "18641608655")):
        for metric, v in (("rwa", rwa), ("cet1_capital", cet1), ("cet1_ratio", "0.182")):
            rows.append({"table": eba.TEMPLATE, "column": eba.CURRENT_COLUMN, "row": code[metric], "value": v,
                         "name": name, "lei": "", "type": "", "country": "France"})
    got = {(f.entity_id, f.metric): f.value for f in a.parse(dt.date(2025, 6, 30), rows)}
    assert got[("la-banque-postale", "rwa")] == 96061 and got[("la-banque-postale", "cet1_capital")] == 17516
    assert round(got[("big-bank", "rwa")]) == 100031
    assert got[("la-banque-postale", "cet1_ratio")] == 18.2
