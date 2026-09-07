"""What the pipeline learns from the review queue, without any AI service.

Every answer the reviewer writes (a person, or the local skill on the maintainer's Mac) teaches the
rules-based extractor something about that bank's documents. Three things are kept, all committed with
the data so the GitHub pipeline benefits the next quarter:

  data/review/hints.json     per entity: the page the KM1 template was found on, the currency, whether
                             the table carries row numbers, filename patterns of documents that hold no
                             KM1 table, and the last verified figures (for continuity checks)
  data/review/learning.json  one record per answer: where the extractor agreed with the reviewer and
                             where it did not, so the failure modes worth fixing are visible over time

Continuity: a newly extracted set of figures is compared with the entity's last verified set. Figures
that sit where the last ones did earn a little confidence; figures that contradict them go to review.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from . import store

HINTS = store.DATA / "review" / "hints.json"
LEARNING = store.DATA / "review" / "learning.json"

PCT_TOL = 0.15          # percentage points: extractor and reviewer agree on a ratio
AMOUNT_TOL = 0.002      # relative: agree on a currency amount (rounding, not a different figure)
CONTINUITY_BONUS = 0.05
CONTINUITY_WINDOW_DAYS = 550     # about six quarters either way


def _read(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def load_hints() -> dict:
    return _read(HINTS, {})


def hint_for(entity_id: str) -> dict:
    return load_hints().get(entity_id, {})


def url_pattern(url: str) -> str:
    """A filename pattern with the digits generalised, so '...remuneration-2025.pdf' also matches 2026."""
    stem = url.rsplit("/", 1)[-1].lower()
    stem = re.sub(r"\.pdf.*$", "", stem)
    return re.sub(r"\d+", r"\\d+", re.escape(stem).replace(r"\\d", "d"))


def skip_matches(entity_id: str, url: str) -> bool:
    """True when the reviewer has marked a document with this filename shape as holding no KM1 table."""
    pats = hint_for(entity_id).get("skip_patterns") or []
    stem = url.rsplit("/", 1)[-1].lower()
    return any(re.fullmatch(p, re.sub(r"\.pdf.*$", "", stem)) for p in pats)


def _agree(metric: str, a, b) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    from .extract.km1 import KIND
    if KIND.get(metric) == "pct":
        return abs(a - b) <= PCT_TOL
    return abs(a - b) <= AMOUNT_TOL * max(abs(b), 1.0)


def record_answer(item: dict | None, ans: dict) -> dict:
    """Update the hints from a resolved answer and log how the extractor did against it."""
    item = dict(item or {})
    ent = ans.get("entity_id") or item.get("entity_id")
    if not ent:
        return {}
    log = _read(LEARNING, [])
    aid = ans.get("id") or item.get("id")
    if aid and any(r.get("id") == aid for r in log):
        return {}                                  # already learned from (the runner re-reads resolved files daily)
    url = ans.get("url") or item.get("url", "")
    if not item.get("values") and url:
        # the queue item may be gone (ingested elsewhere); the documents table kept what the rules read
        docs = store.read("documents")
        if not docs.empty and (docs.url == url).any():
            d = docs[docs.url == url].iloc[-1]
            try:
                item.setdefault("values", json.loads(d.get("values") or "{}"))
            except Exception:
                pass
            item.setdefault("page", d.get("page"))
            item.setdefault("reference_date", d.get("reference_date"))
            item.setdefault("reason", d.get("message") or "")
    hints = load_hints()
    h = hints.setdefault(ent, {})
    rec = {"date": datetime.utcnow().isoformat(timespec="seconds"), "id": ans.get("id") or item.get("id"), "entity_id": ent,
           "reason": (item.get("reason") or "")[:80], "skip": bool(ans.get("skip"))}
    if ans.get("skip"):
        pat = url_pattern(url) if url else ""
        if pat and pat not in h.setdefault("skip_patterns", []):
            h["skip_patterns"].append(pat)
    else:
        if ans.get("page"):
            h["page"] = int(ans["page"])
        if ans.get("currency"):
            h["currency"] = ans["currency"]
        if any("label only" in str(c) for c in (item.get("checks") or [])):
            h["trust_labels"] = True            # the reviewer confirmed a table that carries no row numbers
        if ans.get("values") and ans.get("reference_date"):
            last = h.get("last_verified") or {}
            if not last.get("reference_date") or str(ans["reference_date"]) >= str(last["reference_date"]):
                h["last_verified"] = {"reference_date": str(ans["reference_date"])[:10], "values": ans["values"], "method": "pdf_manual"}
        ext = item.get("values") or {}
        compared, matched, mism = 0, 0, {}
        for m, v in (ans.get("values") or {}).items():
            if m in ext and ext[m] is not None:
                compared += 1
                if _agree(m, ext[m], v):
                    matched += 1
                else:
                    mism[m] = [ext[m], v]
        rec.update({"compared": compared, "matched": matched, "mismatches": mism,
                    "page_extractor": item.get("page"), "page_reviewer": ans.get("page"),
                    "date_extractor": item.get("reference_date"), "date_reviewer": str(ans.get("reference_date"))[:10] if ans.get("reference_date") else None})
    _write(HINTS, hints)
    log.append(rec)
    _write(LEARNING, log)
    return rec


def remember_verified(entity_id: str, reference_date: date, values: dict) -> None:
    """A high-confidence extraction also becomes the baseline for the next continuity check."""
    hints = load_hints()
    h = hints.setdefault(entity_id, {})
    last = h.get("last_verified") or {}
    if not last.get("reference_date") or reference_date.isoformat() >= str(last["reference_date"]):
        h["last_verified"] = {"reference_date": reference_date.isoformat(), "values": values, "method": "pdf_rules"}
        _write(HINTS, hints)


def remember_browser_page(entity_id: str, page: str) -> None:
    """The page where the browser collector last found documents; the next run starts there."""
    hints = load_hints()
    h = hints.setdefault(entity_id, {})
    if h.get("browser_page") != page:
        h["browser_page"] = page
        h["browser_page_found"] = date.today().isoformat()
        _write(HINTS, hints)


def continuity(entity_id: str, values: dict, reference_date: date | None) -> tuple[str | None, str]:
    """Compare freshly extracted figures with the entity's last verified set.
    Returns ('ok' | 'contradiction' | None, message)."""
    last = hint_for(entity_id).get("last_verified") or {}
    lv = last.get("values") or {}
    if not lv or not values:
        return None, ""
    # a baseline is only a baseline while it is recent: five years of balance-sheet growth is not a contradiction
    if reference_date and last.get("reference_date"):
        gap = abs((reference_date - date.fromisoformat(str(last["reference_date"])[:10])).days)
        if gap > CONTINUITY_WINDOW_DAYS:
            return None, ""
    notes, bad = [], []
    if "cet1_ratio" in values and "cet1_ratio" in lv:
        d = abs(float(values["cet1_ratio"]) - float(lv["cet1_ratio"]))
        (bad if d > 10 else notes).append(f"CET1 ratio moved {d:.1f} points from {last['reference_date']}")
    if "rwa" in values and "rwa" in lv and float(lv["rwa"]) > 0:
        r = float(values["rwa"]) / float(lv["rwa"])
        (bad if (r > 2.5 or r < 0.4) else notes).append(f"RWA is {r:.2f}x the last verified figure")
    if "leverage_ratio" in values and "leverage_ratio" in lv:
        d = abs(float(values["leverage_ratio"]) - float(lv["leverage_ratio"]))
        (bad if d > 4 else notes).append(f"leverage ratio moved {d:.1f} points")
    if reference_date and last.get("reference_date") and reference_date.isoformat() < str(last["reference_date"]):
        return None, ""                       # an older document says nothing about drift
    if bad:
        return "contradiction", "; ".join(bad)
    if notes:
        return "ok", "consistent with the last verified disclosure (" + "; ".join(notes) + ")"
    return None, ""


def summary() -> dict:
    """Agreement between extractor and reviewer, by metric and by failure reason, plus hint coverage."""
    log = _read(LEARNING, [])
    hints = load_hints()
    answered = [r for r in log if not r.get("skip")]
    compared = sum(r.get("compared", 0) for r in answered)
    matched = sum(r.get("matched", 0) for r in answered)
    by_metric: dict[str, dict] = {}
    for r in answered:
        for m, pair in (r.get("mismatches") or {}).items():
            by_metric.setdefault(m, {"mismatches": 0, "examples": []})
            by_metric[m]["mismatches"] += 1
            if len(by_metric[m]["examples"]) < 3:
                by_metric[m]["examples"].append({"entity": r["entity_id"], "extractor": pair[0], "reviewer": pair[1]})
    by_reason: dict[str, int] = {}
    for r in log:
        key = (r.get("reason") or "").split(";")[0][:60] or "(no reason)"
        by_reason[key] = by_reason.get(key, 0) + 1
    page_right = sum(1 for r in answered if r.get("page_extractor") and r.get("page_reviewer") and int(r["page_extractor"]) == int(r["page_reviewer"]))
    date_right = sum(1 for r in answered if r.get("date_extractor") and r.get("date_reviewer") and str(r["date_extractor"])[:10] == r["date_reviewer"])
    return {"answers": len(log), "skipped": len(log) - len(answered), "values_compared": compared, "values_matched": matched,
            "agreement": round(matched / compared, 3) if compared else None,
            "page_right": page_right, "date_right": date_right, "answered": len(answered),
            "by_metric": dict(sorted(by_metric.items(), key=lambda kv: -kv[1]["mismatches"])),
            "by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
            "entities_with_hints": len(hints), "skip_patterns": sum(len(h.get("skip_patterns") or []) for h in hints.values()),
            "entities_with_baseline": sum(1 for h in hints.values() if h.get("last_verified"))}
