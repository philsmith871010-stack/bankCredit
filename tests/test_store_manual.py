from datetime import date

from bankcredit import store
from bankcredit.models import Fact


def test_manual_facts_survive_a_document_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    (tmp_path).mkdir(exist_ok=True)
    url = "https://example.org/p3.pdf"
    manual = [Fact("ubs", date(2026, 6, 30), "lcr", 190.0, source="pillar3", document=url, method="pdf_manual"),
              Fact("ubs", date(2026, 6, 30), "cet1_ratio", 14.4, source="pillar3", document=url, method="pdf_manual")]
    store.upsert("facts", manual)
    store.upsert("facts", [Fact("ubs", date(2026, 3, 31), "cet1_ratio", 14.6, source="pillar3", document=url, method="pdf_rules")])
    assert store.drop("facts", ne={"method": "pdf_manual"}, document=url, source="pillar3") == 1
    left = store.read("facts")
    assert sorted(left.metric) == ["cet1_ratio", "lcr"] and set(left.method) == {"pdf_manual"}
