"""Turn the Parquet tables into the JSON the static site reads.

Outputs (data/json/):
  board.json      one row per entity with latest metrics, score, ratings summary, market signal, data age
  banks/<id>.json full per-entity payload: metric series, ratings, prices, events, sources
  status.json     last runs per source
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd

from . import store
from .entities import load as load_entities
from .models import METRICS
from .score import compute

SITE_METRICS = ["cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "lcr", "nsfr", "rwa",
                "overall_capital_requirement", "cet1_requirement", "npl_ratio", "roe", "roa", "efficiency_ratio",
                "total_assets", "deposits", "uninsured_deposits", "htm_unrealised_loss"]
AGENCY_ORDER = ["fitch", "sp", "moodys", "dbrs", "kbra", "scope", "jcr"]
AGENCY_LETTER = {"fitch": "F", "sp": "S", "moodys": "M", "dbrs": "D", "kbra": "K", "scope": "Sc", "jcr": "J"}


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _series(facts: pd.DataFrame) -> dict:
    out = {}
    if facts.empty:
        return out
    for metric, g in facts.groupby("metric"):
        g = g.sort_values("reference_date")
        # keep one value per reference date, preferring the most confident source
        g = g.sort_values(["reference_date", "confidence"]).drop_duplicates("reference_date", keep="last")
        out[metric] = [{"d": str(r.reference_date)[:10], "v": _clean(float(r.value)), "src": r.source,
                        "doc": r.document, "page": _clean(r.page) if hasattr(r, "page") else None,
                        "method": r.method, "conf": _clean(float(r.confidence))} for r in g.itertuples()]
    return out


def _latest(series: dict) -> dict:
    return {m: pts[-1]["v"] for m, pts in series.items() if pts and pts[-1]["v"] is not None}


def _ratings_summary(r: pd.DataFrame) -> list[dict]:
    """One headline long-term rating per agency: prefer idr/issuer, then deposit."""
    if r.empty:
        return []
    pref = {"idr": 0, "issuer": 1, "deposit": 2, "counterparty": 3, "resolution_counterparty": 4}
    out = []
    long = r[r.horizon == "long"].copy()
    long["pref"] = long.rating_type.map(pref).fillna(9)
    for ag in AGENCY_ORDER:
        g = long[long.agency == ag].sort_values(["pref", "action_date"], ascending=[True, False])
        if not g.empty:
            row = g.iloc[0]
            out.append({"agency": ag, "letter": AGENCY_LETTER.get(ag, ag[:1].upper()), "value": row.value,
                        "type": row.rating_type, "outlook": row.outlook or "", "date": str(row.action_date)[:10]})
    return out


def _market(prices: pd.DataFrame, cds: pd.DataFrame) -> dict:
    sig = {"direction": "none", "label": "No market data", "vol30": None, "drawdown52": None, "cds5y": None, "cds_change30": None}
    if not prices.empty:
        p = prices.sort_values("date")
        closes = p.close.astype(float).values
        if len(closes) > 31:
            import numpy as np
            rets = np.diff(np.log(closes[-31:]))
            sig["vol30"] = round(float(rets.std() * math.sqrt(252) * 100), 1)
        if len(closes) > 5:
            hi = max(closes[-252:])
            sig["drawdown52"] = round(float((closes[-1] / hi - 1) * 100), 1)
        sig["last_price_date"] = str(p.date.iloc[-1])[:10]
    if not cds.empty:
        c = cds.sort_values("date")
        c = c[c.tier == "senior"] if "tier" in c and (c.tier == "senior").any() else c
        last = float(c.level_bp.iloc[-1])
        ref = c[c.date <= str(date.fromisoformat(str(c.date.iloc[-1])[:10]) - timedelta(days=30))]
        chg = last - float(ref.level_bp.iloc[-1]) if not ref.empty else None
        sig.update({"cds5y": round(last, 1), "cds_change30": round(chg, 1) if chg is not None else None})
        if chg is not None:
            sig["direction"] = "down" if chg > 5 else ("up" if chg < -5 else "flat")
            sig["label"] = {"down": "Widening", "up": "Tightening", "flat": "Stable"}[sig["direction"]]
    elif sig["drawdown52"] is not None:
        dd = sig["drawdown52"]
        sig["direction"] = "down" if dd < -15 else "flat"
        sig["label"] = "Equity weak" if dd < -15 else "Stable"
    return sig


OVERLAY_DEFAULT = {
    # Provisional equal weights (decided 6 September 2026): four signals, each worth at most 2.5 points
    # either way, so the overlay stays inside the ±10 cap. Ratings: grade value averaged across agencies.
    # CDS: level band plus 30-day change. Volatility: 30-day realised. Drawdown: from the 52-week high.
    # A COUNTERPARTY_OVERLAY secret with the same keys replaces this dict at build time.
    "cds_bands": [[40, 1.5], [60, 0.5], [90, 0], [150, -0.5], [1e9, -1.5]],      # [upper bp, adjustment]
    "cds_change_widen_bp": 15, "cds_change_widen_adj": -1.0, "cds_change_tighten_bp": -10, "cds_change_tighten_adj": 1.0,
    "vol_high": 45, "vol_high_adj": -2.5, "vol_low": 25, "vol_low_adj": 2.5,
    "drawdown_adj_threshold": -25, "drawdown_adj": -2.5,
    "rating_grades": {"AAA": 2.5, "AA": 2.0, "A": 1.0, "BBB": 0, "BB": -1.5, "B": -2.5},
    "cap": 10.0,
}


def overlay_config() -> dict:
    import json, os
    raw = os.environ.get("COUNTERPARTY_OVERLAY")
    if not raw:
        return OVERLAY_DEFAULT
    try:
        cfg = dict(OVERLAY_DEFAULT); cfg.update(json.loads(raw)); return cfg
    except Exception:
        return OVERLAY_DEFAULT


def _overlay(market: dict, ratings: list[dict]) -> float:
    """Bounded market layer. Weights come from the COUNTERPARTY_OVERLAY secret when set; otherwise the
    published provisional equal weights in OVERLAY_DEFAULT."""
    cfg = overlay_config()
    adj = 0.0
    if market.get("cds5y") is not None:
        c = market["cds5y"]
        for upper, a in cfg["cds_bands"]:
            if c < upper:
                adj += a; break
        chg = market.get("cds_change30")
        if chg is not None:
            if chg > cfg["cds_change_widen_bp"]:
                adj += cfg["cds_change_widen_adj"]
            elif chg < cfg["cds_change_tighten_bp"]:
                adj += cfg["cds_change_tighten_adj"]
    if market.get("vol30") is not None:
        adj += cfg["vol_high_adj"] if market["vol30"] > cfg["vol_high"] else (cfg["vol_low_adj"] if market["vol30"] < cfg["vol_low"] else 0)
    if market.get("drawdown52") is not None and market["drawdown52"] < cfg["drawdown_adj_threshold"]:
        adj += cfg["drawdown_adj"]
    grades = cfg["rating_grades"]
    for r in ratings:
        v = r["value"].replace("(H)", "").replace("(L)", "").replace("(high)", "").replace("(low)", "").strip()
        key = v.rstrip("+-").rstrip("1234").upper()
        key = {"AA": "AA", "AAA": "AAA", "A": "A", "BAA": "BBB", "BBB": "BBB", "BA": "BB", "BB": "BB", "B": "B"}.get(key, key)
        if key in grades:
            adj += grades[key] / max(1, len(ratings))
    cap = float(cfg.get("cap", 10.0))
    return round(max(-cap, min(cap, adj)), 1)


def export_json() -> None:
    entities = load_entities()
    facts, ratings, prices, cds, events, runs = (store.read(t) for t in ["facts", "ratings", "prices", "cds", "events", "runs"])
    board, today, details = [], date.today(), {}
    for e in entities:
        if not e.active:
            continue
        f = facts[facts.entity_id == e.id] if not facts.empty else facts
        r = ratings[ratings.entity_id == e.id] if not ratings.empty else ratings
        p = prices[prices.entity_id == e.id] if not prices.empty else prices
        c = cds[cds.entity_id == e.id] if not cds.empty else cds
        ev = events[events.entity_id == e.id] if not events.empty else events
        series = _series(f)
        latest = _latest(series)
        rsum = _ratings_summary(r)
        market = _market(p, c)
        overlay = _overlay(market, rsum)
        sc = compute(latest, overlay)
        asof = max((pts[-1]["d"] for pts in series.values() if pts), default=None)
        age = (today - date.fromisoformat(asof)).days if asof else None
        row = {
            "id": e.id, "name": e.name, "short": e.short_name, "country": e.country, "type": e.type,
            "region": e.region, "group": e.group, "peer_group": e.peer_group, "lei": e.lei,
            "score": sc.final_score, "public_score": sc.public_score, "band": sc.band, "coverage": sc.coverage,
            "overlay": sc.overlay if sc.final_score is not None else None,
            "cet1": latest.get("cet1_ratio"), "leverage": latest.get("leverage_ratio"), "lcr": latest.get("lcr"),
            "nsfr": latest.get("nsfr"), "ratings": rsum,
            "market": {k: market[k] for k in ("direction", "label")},
            "events90": int(len(ev)) if not ev.empty else 0, "asof": asof, "age_days": age,
            "basis": (f.sort_values("reference_date").basis.iloc[-1] if not f.empty else ""),
        }
        board.append(row)
        details[e.id] = (row, {
            "series": {m: series[m] for m in series if m in SITE_METRICS},
            "metric_labels": {m: METRICS.get(m, m) for m in series},
            "score_detail": {"pillars": sc.pillars, "inputs": sc.inputs},
            "ratings_all": [{"agency": x.agency, "type": x.rating_type, "horizon": x.horizon, "value": x.value,
                             "outlook": x.outlook or "", "date": str(x.action_date)[:10], "action": x.action or ""}
                            for x in r.sort_values(["agency", "horizon", "rating_type"]).itertuples()] if not r.empty else [],
            "prices": [{"d": str(x.date)[:10], "c": float(x.close)} for x in p.sort_values("date").tail(260).itertuples()] if not p.empty else [],
            "price_currency": (p.currency.iloc[-1] if not p.empty else None),
            "market_public": {k: market.get(k) for k in ("direction", "label", "vol30", "drawdown52", "last_price_date")},
            "events": [{k: _clean(v) for k, v in x.items()} for x in ev.sort_values("date", ascending=False).drop_duplicates(["date", "title"]).head(60).to_dict("records")] if not ev.empty else [],
        })
    # peer bands for the ribbon: 25th, 50th, 75th percentile of final score within peer group
    df = pd.DataFrame(board)
    if not df.empty and df.score.notna().any():
        for pg, g in df[df.score.notna()].groupby("peer_group"):
            q = g.score.quantile([0.25, 0.5, 0.75]).tolist()
            for row in board:
                if row["peer_group"] == pg:
                    row["peer"] = {"p25": round(q[0], 1), "p50": round(q[1], 1), "p75": round(q[2], 1), "n": int(len(g))}
                    if row["score"] is not None:
                        row["percentile"] = int(round((g.score < row["score"]).mean() * 100))
    for eid, (row, extra) in details.items():
        detail = dict(row); detail.update(extra); store.write_json(f"banks/{eid}", detail)
    benchmarks = []
    series = store.read("series")
    if not series.empty:
        for sid, g in series.sort_values("date").groupby("series_id"):
            g = g.dropna(subset=["value"])
            if g.empty:
                continue
            last = g.iloc[-1]
            month_ago = g[g.date <= (pd.Timestamp(last.date) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")]
            prev = float(month_ago.iloc[-1].value) if not month_ago.empty else None
            benchmarks.append({"id": sid, "label": last.label, "date": str(last.date)[:10], "value": float(last.value),
                               "change30": round(float(last.value) - prev, 1) if prev is not None else None,
                               "spark": [float(v) for v in g.value.tail(60)]})
    store.write_json("board", {"generated": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": board, "benchmarks": benchmarks})
    status = []
    if not runs.empty:
        for src, g in runs.sort_values("finished").groupby("source"):
            last = g.iloc[-1]
            status.append({"source": src, "status": last.status, "rows": int(last.rows), "finished": str(last.finished), "message": last.message})
    docs = store.read("documents")
    doc_rows, counts = [], {}
    if not docs.empty:
        docs = docs.sort_values("fetched_at", ascending=False)
        counts = {k: int(v) for k, v in docs.status.value_counts().items()}
        short = {e.id: e.short_name for e in entities}
        for r in docs.head(80).itertuples():
            doc_rows.append({"entity_id": r.entity_id, "short": short.get(r.entity_id, r.entity_id), "status": r.status,
                             "reference_date": _clean(r.reference_date), "confidence": _clean(float(r.confidence)) or 0.0,
                             "title": r.title, "url": r.url, "fetched_at": str(r.fetched_at)})
    from . import review
    queue = [{k: i.get(k) for k in ("id", "entity_id", "reference_date", "page", "reason", "url")} for i in review.load()]
    store.write_json("status", {"generated": datetime.utcnow().isoformat(timespec="seconds") + "Z", "runs": status,
                                "documents": doc_rows, "document_counts": counts, "review": queue})
