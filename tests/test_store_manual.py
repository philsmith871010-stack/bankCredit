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


def test_reprocess_does_not_delete_a_reviewers_answers(tmp_path, monkeypatch):
    """A cached document that stops extracting still holds the figures a person read from it.
    Dropping every fact for the document takes those with it, and nothing puts them back."""
    from datetime import date
    from bankcredit import store
    from bankcredit.models import Fact

    monkeypatch.setattr(store, "DATA", tmp_path)
    url = "https://x/pillar-3.pdf"
    store.upsert("facts", [
        Fact(entity_id="somebank", reference_date=date(2026, 3, 31), metric="cet1_ratio", value=19.6,
             source="pillar3", document=url, method="pdf_manual"),
        Fact(entity_id="somebank", reference_date=date(2026, 3, 31), metric="lcr", value=232.6,
             source="pillar3", document=url, method="pdf_rules"),
    ])
    store.drop("facts", ne={"method": "pdf_manual"}, document=url, source="pillar3")
    left = store.read("facts")
    assert list(left.metric) == ["cet1_ratio"] and list(left.method) == ["pdf_manual"]


def test_new_rows_take_the_timestamp_form_the_table_already_has(tmp_path, monkeypatch):
    """The merge driver had left facts.parquet with loaded_at as text; the next Fact carried a
    datetime, and pyarrow refused the mixed column. That stopped every pipeline run for a day."""
    import pandas as pd
    monkeypatch.setattr(store, "DATA", tmp_path)
    text = pd.DataFrame([{"entity_id": "ubs", "reference_date": "2026-03-31", "metric": "lcr", "value": 180.0, "unit": "pct",
                          "currency": "", "basis": "consolidated", "source": "pillar3", "document": "d", "page": 1,
                          "method": "pdf_rules", "confidence": 0.9, "loaded_at": "2026-09-15T10:10:00"}])
    text.to_parquet(store.path("facts"), index=False)
    store.upsert("facts", [Fact("ubs", date(2026, 6, 30), "lcr", 190.0, source="pillar3", document="d", method="pdf_manual")])
    got = store.read("facts")
    assert len(got) == 2 and not pd.api.types.is_datetime64_any_dtype(got["loaded_at"])
    assert all(isinstance(v, str) for v in got["loaded_at"]), "the newcomer took the table's form"
    # and the other way round: a datetime table stays a datetime table
    stamped = pd.DataFrame([{"entity_id": "ubs", "event_id": "e1", "loaded_at": pd.Timestamp("2026-09-15T10:10:00")}])
    stamped.to_parquet(store.path("rating_actions"), index=False)
    store.upsert("rating_actions", [{"entity_id": "ubs", "event_id": "e2", "loaded_at": "2026-09-16T10:10:00"}])
    assert pd.api.types.is_datetime64_any_dtype(store.read("rating_actions")["loaded_at"])
