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
        # A consolidated (holding company) series replaces a lead-bank proxy when it is reasonably current;
        # otherwise both are kept and the latest date wins, each point carrying its basis.
        cons = g[g.basis == "consolidated"]
        if not cons.empty and (pd.Timestamp(g.reference_date.max()) - pd.Timestamp(cons.reference_date.max())).days <= 120:
            g = cons
        g = g.assign(_basis_rank=(g.basis == "consolidated").astype(int))
        g = g.sort_values(["reference_date", "_basis_rank", "confidence"]).drop_duplicates("reference_date", keep="last")
        out[metric] = [{"d": str(r.reference_date)[:10], "v": _clean(float(r.value)), "src": r.source, "basis": r.basis,
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


CDS_MAX_AGE_DAYS = 10     # a CDS level older than this is not used in the signal or the overlay
BOND_MAX_AGE_DAYS = 10    # a bond quote older than this says nothing about today either
BOND_MIN_WINDOW_DAYS = 5  # the shortest history a bond change may be measured over while quotes accumulate
BOND_WINDOW_DAYS = 30


def _bond_changes(bonds: pd.DataFrame, quotes: pd.DataFrame) -> dict[str, dict]:
    """Per entity: median yield change of its reference bonds over the last 30 days, less the median change
    of every bank bond in the same currency, so rate moves cancel and what remains is the bank's own credit.
    Levels are never exported; only the relative change in basis points."""
    if bonds is None or quotes is None or bonds.empty or quotes.empty:
        return {}
    q = quotes.merge(bonds[["isin", "entity_id", "currency"]], on="isin").sort_values("date")
    q = q[q["yield"].notna()]
    today = date.today()
    rows = []
    for isin, g in q.groupby("isin"):
        last = g.iloc[-1]
        last_d = date.fromisoformat(str(last.date)[:10])
        if (today - last_d).days > BOND_MAX_AGE_DAYS:
            continue
        ref_cut = str(last_d - timedelta(days=BOND_WINDOW_DAYS))
        ref = g[g.date.astype(str) <= ref_cut]
        ref_row = ref.iloc[-1] if not ref.empty else g.iloc[0]
        window = (last_d - date.fromisoformat(str(ref_row.date)[:10])).days
        if window < BOND_MIN_WINDOW_DAYS:
            continue
        rows.append({"isin": isin, "entity_id": last.entity_id, "currency": last.currency, "asof": str(last_d),
                     "window": window, "chg_bp": (float(last["yield"]) - float(ref_row["yield"])) * 100})
    if not rows:
        return {}
    d = pd.DataFrame(rows)
    peer = d.groupby("currency").chg_bp.median()
    d["rel_bp"] = d.chg_bp - d.currency.map(peer)
    out = {}
    for ent, g in d.groupby("entity_id"):
        out[ent] = {"bond_change30": round(float(g.rel_bp.median()), 1), "bond_count": int(len(g)),
                    "bond_asof": str(g["asof"].max()), "bond_window": int(g.window.median())}
    return out




def _market(prices: pd.DataFrame, cds: pd.DataFrame, bond: dict | None = None) -> dict:
    """Direction of the market's view over 30 days. Precedence: a fresh senior CDS, then the bank's own bonds
    against peers in the same currency, then the share price. Each rung is used only when the one above is absent."""
    sig = {"direction": "none", "label": "No market data", "vol30": None, "drawdown52": None, "cds5y": None, "cds_change30": None,
           "bond_change30": None, "bond_count": 0, "bond_asof": None, "bond_window": None}
    if bond:
        sig.update(bond)
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
    c = cds.iloc[0:0]
    if not cds.empty:
        c = cds.sort_values("date")
        c = c[c.tier == "senior"] if "tier" in c and (c.tier == "senior").any() else c
        # a settlement price (ice) beats a trade-derived level (dtcc) on the same day
        if "source" in c:
            c = c.assign(_rank=(c.source == "ice").astype(int)).sort_values(["date", "_rank"]).drop_duplicates("date", keep="last")
        last_date = date.fromisoformat(str(c.date.iloc[-1])[:10])
        if (date.today() - last_date).days > CDS_MAX_AGE_DAYS:
            c = c.iloc[0:0]                     # stale: the CDS says nothing about today, fall through to equity
    if not cds.empty and not c.empty:
        last = float(c.level_bp.iloc[-1])
        ref = c[c.date <= str(date.fromisoformat(str(c.date.iloc[-1])[:10]) - timedelta(days=30))]
        chg = last - float(ref.level_bp.iloc[-1]) if not ref.empty else None
        sig.update({"cds5y": round(last, 1), "cds_change30": round(chg, 1) if chg is not None else None})
        if chg is not None:
            sig["direction"] = "down" if chg > 5 else ("up" if chg < -5 else "flat")
            sig["label"] = {"down": "Widening", "up": "Tightening", "flat": "Stable"}[sig["direction"]]
    if sig["direction"] != "none":
        pass                                     # a CDS with a 30-day history has spoken
    elif sig["bond_change30"] is not None:       # a CDS too young for a change, or none at all: the bonds
        b = sig["bond_change30"]
        bar = 20 if (sig.get("bond_count") or 0) >= 2 else 30      # one quoted line is noisier than a median of several
        sig["direction"] = "down" if b > bar else ("up" if b < -bar else "flat")
        sig["label"] = {"down": "Bonds widening", "up": "Bonds tightening", "flat": "Stable (bonds)"}[sig["direction"]]
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
    # Bonds stand in for the CDS change (never the level) when no fresh CDS exists: 30-day yield change against peers.
    "bond_change_widen_bp": 20, "bond_change_widen_adj": -1.0, "bond_change_tighten_bp": -15, "bond_change_tighten_adj": 1.0,
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
    elif market.get("bond_change30") is not None:
        b = market["bond_change30"]
        if b > cfg["bond_change_widen_bp"]:
            adj += cfg["bond_change_widen_adj"]
        elif b < cfg["bond_change_tighten_bp"]:
            adj += cfg["bond_change_tighten_adj"]
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
    bond_changes = _bond_changes(store.read("bonds"), store.read("bond_quotes"))
    board, today, details = [], date.today(), {}
    active = [e for e in entities if e.active]
    series_all = {e.id: _series(facts[facts.entity_id == e.id] if not facts.empty else facts) for e in active}
    market_all = {e.id: _market(prices[prices.entity_id == e.id] if not prices.empty else prices,
                                cds[cds.entity_id == e.id] if not cds.empty else cds, bond_changes.get(e.id)) for e in active}
    for e in active:
        f = facts[facts.entity_id == e.id] if not facts.empty else facts
        r = ratings[ratings.entity_id == e.id] if not ratings.empty else ratings
        p = prices[prices.entity_id == e.id] if not prices.empty else prices
        ev = events[events.entity_id == e.id] if not events.empty else events
        series = dict(series_all[e.id])
        inherited = []
        subs = [x for x in active if x.group == e.id and x.type == "bank"]
        if subs:
            # a holding company inherits bank-level asset quality, profitability and deposit figures from its
            # principal bank (the one with the largest deposits), labelled as the lead bank's
            def _dep(x):
                pts = series_all[x.id].get("deposits") or []
                return pts[-1]["v"] or 0 if pts else 0
            lead = max(subs, key=_dep)
            for m in ("npl_ratio", "roa", "roe", "nim", "efficiency_ratio", "deposits", "uninsured_deposits",
                      "htm_unrealised_loss", "total_assets", "tier1_leverage"):
                if m not in series and m in series_all[lead.id]:
                    series[m] = [dict(pt, basis="lead_bank", src=pt["src"] + " (lead bank)") for pt in series_all[lead.id][m]]
                    inherited.append(m)
        if e.group and e.group in series_all:
            # liquidity ratios are often disclosed only at group level; show the group's, labelled as such
            for m in ("lcr", "nsfr"):
                if m not in series and m in series_all[e.group]:
                    series[m] = [dict(pt, basis="group", src=pt["src"] + " (group)") for pt in series_all[e.group][m]]
                    inherited.append(m)
        latest = _latest(series)
        rsum = _ratings_summary(r)
        market = market_all[e.id]
        if market["direction"] == "none" and e.group in market_all and market_all[e.group]["direction"] != "none":
            market = dict(market_all[e.group], label=market_all[e.group]["label"] + " (group)")
            inherited.append("market")
        overlay = _overlay(market, rsum)
        sc = compute(latest, overlay)
        asof = max((pts[-1]["d"] for pts in series.values() if pts), default=None)
        age = (today - date.fromisoformat(asof)).days if asof else None
        row = {
            "id": e.id, "name": e.name, "short": e.short_name, "country": e.country, "type": e.type,
            "region": e.region, "group": e.group, "peer_group": e.peer_group, "lei": e.lei,
            "score": sc.final_score, "public_score": sc.public_score, "band": sc.band, "coverage": sc.coverage,
            "overlay": sc.overlay if sc.final_score is not None else None,
            "cet1": latest.get("cet1_ratio"), "leverage": latest.get("leverage_ratio", latest.get("tier1_leverage")),
            "leverage_basis": "basel" if "leverage_ratio" in latest else ("us_tier1" if "tier1_leverage" in latest else ""),
            "lcr": latest.get("lcr"),
            "nsfr": latest.get("nsfr"), "ratings": rsum,
            "market": {k: market[k] for k in ("direction", "label")},
            "events90": int(len(ev)) if not ev.empty else 0, "asof": asof, "age_days": age,
            "basis": (f.sort_values("reference_date").basis.iloc[-1] if not f.empty else ""),
            "inherited": inherited,
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
            "market_public": {k: market.get(k) for k in ("direction", "label", "vol30", "drawdown52", "last_price_date",
                                                         "bond_change30", "bond_count", "bond_asof", "bond_window")},
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
