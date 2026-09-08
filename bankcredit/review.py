"""Review queue for PDF extractions that did not pass validation.

The queue is a JSON file committed with the data so the Mac (running Claude Code
on the user's subscription, no API key) can work through it offline:

  data/review/queue.json            open items, one per document
  data/review/resolved/<id>.json    answers written by the reviewer (person or local skill)

`python -m bankcredit.cli review list`    show open items
`python -m bankcredit.cli review ingest`  load resolved answers as facts, close the items
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from . import learn, store
from .models import Fact

log = logging.getLogger("bankcredit.review")

QUEUE = store.DATA / "review" / "queue.json"
RESOLVED = store.DATA / "review" / "resolved"


def load() -> list[dict]:
    return json.loads(QUEUE.read_text()) if QUEUE.exists() else []


def save(items: list[dict]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(items, indent=1, ensure_ascii=False, default=str))


def add(item: dict) -> bool:
    """Queue an item keyed on its id; returns False if already queued or already answered.

    The id is the document's content hash, so an answer under that id was written against these
    exact bytes and stays true. Without this check a document whose extraction still fails the
    rules comes back to the reviewer on every collection run, for ever; a document republished
    with different bytes hashes differently and is queued as the new document it is."""
    items = load()
    if any(i["id"] == item["id"] for i in items):
        return False
    if (RESOLVED / f"{item['id']}.json").exists():
        return False
    item.setdefault("status", "open")
    item.setdefault("created", datetime.utcnow().isoformat(timespec="seconds"))
    items.append(item)
    save(items)
    return True


def remove(item_id: str) -> bool:
    items = load()
    kept = [i for i in items if i["id"] != item_id]
    if len(kept) != len(items):
        save(kept)
        return True
    return False


def ingest() -> int:
    """Load every resolved answer into facts and drop it from the queue. Returns facts written."""
    if not RESOLVED.exists():
        return 0
    items = load()
    by_id = {i["id"]: i for i in items}
    written = 0
    for f in sorted(RESOLVED.glob("*.json")):
        try:
            ans = json.loads(f.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # a half-written answer must not take the other 140 down with it: an ingest that
            # aborts here leaves every later answer unloaded and says nothing about which file
            log.warning("review: %s is not readable (%s); skipped", f.name, exc)
            continue
        if not isinstance(ans, dict):
            log.warning("review: %s is not an answer object; skipped", f.name)
            continue
        item = by_id.get(ans.get("id") or f.stem)
        learn.record_answer(item, ans)          # hints for next time, and a record of how the rules did
        if ans.get("skip"):
            if item:
                item["status"] = "skipped"
            continue
        ref = ans.get("reference_date") or (item or {}).get("reference_date")
        if not ref or not ans.get("values"):
            continue
        ref = date.fromisoformat(str(ref)[:10])
        entity = ans.get("entity_id") or (item or {}).get("entity_id")
        url = ans.get("url") or (item or {}).get("url", "")
        ccy = ans.get("currency") or (item or {}).get("currency", "")
        facts = []
        from .extract.km1 import ROWS, PUBLISH
        from .extract.km1 import KIND as kinds
        for metric, value in ans["values"].items():
            if metric not in PUBLISH or value is None:
                continue
            facts.append(Fact(entity_id=entity, reference_date=ref, metric=metric, value=float(value),
                              unit="pct" if kinds.get(metric) == "pct" else "ccy_m",
                              currency="" if kinds.get(metric) == "pct" else ccy, basis="consolidated",
                              source="pillar3", document=url, page=ans.get("page") or (item or {}).get("page"),
                              method="pdf_manual", confidence=float(ans.get("confidence", 0.98))))
        written += store.upsert("facts", facts)
        docs = store.read("documents")
        if not docs.empty and url:
            docs.loc[(docs.url == url), ["status", "reference_date", "confidence"]] = ["loaded", ref.isoformat(), 0.98]
            docs.to_parquet(store.path("documents"), index=False)
        if item:
            item["status"] = "resolved"
    save([i for i in items if i.get("status") == "open"])
    return written
