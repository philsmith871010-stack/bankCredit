"""Turn the Parquet tables into the JSON the static site reads.

Outputs (data/json/):
  board.json      one row per entity with latest metrics, score, ratings summary, market signal, data age
  banks/<id>.json full per-entity payload: metric series, ratings, prices, events, sources
  status.json     last runs per source
"""
from __future__ import annotations

import math
import re
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
        g = g.assign(_basis_rank=(g.basis == "consolidated").astype(int), _src_rank=(g.source != "eba_te").astype(int))
        g = g.sort_values(["reference_date", "_basis_rank", "_src_rank", "confidence"]).drop_duplicates("reference_date", keep="last")
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


# One numeric scale across agencies (1 = AAA/Aaa ... 10 = BBB-/Baa3 ... 17 = CCC and below), lower is stronger.
_SP_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC"]
_MOODYS = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3", "Ba1", "Ba2", "Ba3", "B1", "B2", "B3", "Caa"]


def rating_grade(value: str | None) -> int | None:
    """Map any agency's long-term symbol to the common 1..17 scale; None when unrated or withdrawn."""
    if not value:
        return None
    v = str(value).strip().replace(" ", "")
    v = v.replace("(high)", "+").replace("(H)", "+").replace("(low)", "-").replace("(L)", "-").replace("(hyb)", "")
    v = v.rstrip("u").split("/")[0]
    if v in _MOODYS:
        return _MOODYS.index(v) + 1
    if v.startswith(("Caa", "Ca", "C")) and v[:1] == "C" and not v.startswith("CCC"):
        return 17 if v[:2] in ("Ca", "Caa") else None
    if v.startswith("CCC") or v in ("CC", "C", "D", "RD", "SD"):
        return 17
    return _SP_SCALE.index(v) + 1 if v in _SP_SCALE else None


def grade_letter(grade: float | None) -> str:
    if grade is None:
        return ""
    return _SP_SCALE[max(0, min(16, int(grade + 0.5) - 1))]


CDS_MAX_AGE_DAYS = 10     # a CDS level older than this is not used in the signal or the overlay
BOND_MAX_AGE_DAYS = 10    # a bond quote older than this says nothing about today either
BOND_MIN_WINDOW_DAYS = 5  # the shortest history a bond change may be measured over while quotes accumulate
BOND_WINDOW_DAYS = 30


def _story_key(title: str) -> str:
    """The same story from several outlets: strip the outlet suffix and punctuation, keep the first eight words."""
    t = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", str(title)).lower()
    words = re.findall(r"[a-z0-9€$£]+", t)
    return " ".join(w for w in words if w not in ("the", "a", "an", "of", "to", "and", "in", "on", "for", "with", "by", "at", "its"))[:80]


def _dedupe_events(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.sort_values("date", ascending=False).drop_duplicates(["date", "title"])
    news = ev.type == "news"
    key = ev.title.map(_story_key)
    week = pd.to_datetime(ev.date).dt.to_period("W").astype(str)
    dup = news & ev.assign(_k=key, _w=week).duplicated(["_k", "_w"])
    return ev[~dup]


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




def _index_change(index: pd.DataFrame | None, start: str, end: str) -> float | None:
    """Change in an index series between the last print on or before each of two dates."""
    if index is None or index.empty:
        return None
    ix = index.sort_values("date")
    a = ix[ix.date.astype(str) <= start[:10]]
    b = ix[ix.date.astype(str) <= end[:10]]
    if a.empty or b.empty:
        return None
    return float(b.value.iloc[-1]) - float(a.value.iloc[-1])


def _market(prices: pd.DataFrame, cds: pd.DataFrame, bond: dict | None = None, index: pd.DataFrame | None = None) -> dict:
    """Direction of the market's view over 30 days. Precedence: a fresh senior CDS, then the bank's own bonds
    against peers in the same currency, then the share price. Each rung is used only when the one above is absent.
    A CDS move is also split into the part shared with iTraxx Senior Financials and the part that is the bank's own."""
    sig = {"direction": "none", "label": "No market data", "vol30": None, "drawdown52": None, "cds5y": None, "cds_change30": None,
           "cds_index_change30": None, "cds_excess30": None,
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
        # The 30-day change is measured within one source: settlement against settlement, or trade medians
        # against trade medians on days with at least three trades. Mixing the two would turn the basis
        # difference between a cleared settlement price and a thin day's trades into a spurious move.
        chg, ref = None, c.iloc[0:0]
        full = cds.sort_values("date")
        full = full[full.tier == "senior"] if "tier" in full and (full.tier == "senior").any() else full
        for src in ("ice", "dtcc"):
            h = full[full.source == src] if "source" in full else full
            if src == "dtcc" and "trades" in h:
                h = h[h.trades.fillna(0) >= 3]
            if h.empty or (date.today() - date.fromisoformat(str(h.date.iloc[-1])[:10])).days > CDS_MAX_AGE_DAYS:
                continue
            ref = h[h.date <= str(date.fromisoformat(str(h.date.iloc[-1])[:10]) - timedelta(days=30))]
            if not ref.empty:
                chg = float(h.level_bp.iloc[-1]) - float(ref.level_bp.iloc[-1])
                c = h
                break
        sig.update({"cds5y": round(last, 1), "cds_change30": round(chg, 1) if chg is not None else None})
        if chg is not None:
            sig["direction"] = "down" if chg > 5 else ("up" if chg < -5 else "flat")
            sig["label"] = {"down": "Widening", "up": "Tightening", "flat": "Stable"}[sig["direction"]]
            ixc = _index_change(index, str(ref.date.iloc[-1]), str(c.date.iloc[-1]))
            if ixc is not None:
                sig["cds_index_change30"] = round(ixc, 1)
                sig["cds_excess30"] = round(chg - ixc, 1)
                # the public label says whether the move is the bank's own or the whole sector's, never the size
                if sig["direction"] == "down":
                    sig["label"] = "Widening (bank-specific)" if chg - ixc > 5 else "Widening (with the market)"
                elif sig["direction"] == "up":
                    sig["label"] = "Tightening (bank-specific)" if chg - ixc < -5 else "Tightening (with the market)"
                elif chg - ixc > 5:
                    sig["direction"], sig["label"] = "down", "Lagging the market"          # flat while the sector tightened
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


PREF_TYPE = {"idr": 0, "issuer": 1, "deposit": 2, "counterparty": 3, "resolution_counterparty": 4}


def ratings_summary(active, ratings: pd.DataFrame, events: pd.DataFrame) -> dict:
    """The ratings page: every entity's latest long and short-term rating by agency with outlook and the date of the
    last action, a composite grade, and the rating actions of the last 90 days that were not affirmations."""
    rows = []
    for e in active:
        r = ratings[ratings.entity_id == e.id] if not ratings.empty else ratings
        agencies = {}
        if not r.empty:
            rr = r.assign(_pref=r.rating_type.map(PREF_TYPE).fillna(9)).sort_values(["_pref", "action_date"], ascending=[True, False])
            for ag in AGENCY_ORDER:
                g = rr[rr.agency == ag]
                if g.empty:
                    continue
                lt = g[g.horizon == "long"]
                st = g[g.horizon == "short"]
                l0 = lt.iloc[0] if not lt.empty else None
                agencies[ag] = {"lt": l0.value if l0 is not None else None, "lt_type": l0.rating_type if l0 is not None else None,
                                "outlook": (l0.outlook or "") if l0 is not None else "", "st": st.iloc[0].value if not st.empty else None,
                                "date": str(g.action_date.max())[:10], "action": (l0.action or "") if l0 is not None else ""}
        grades = [gr for gr in (rating_grade(a["lt"]) for a in agencies.values()) if gr is not None]
        grade = round(float(pd.Series(grades).median()), 1) if grades else None
        rows.append({"id": e.id, "short": e.short_name, "name": e.name, "country": e.country, "region": e.region, "type": e.type,
                     "grade": grade, "composite": grade_letter(grade), "agencies": agencies,
                     "last_action": max((a["date"] for a in agencies.values()), default=None)})
    actions = []
    if not events.empty:
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        ev = events[(events.type == "rating") & (events.date.astype(str) >= cutoff)]
        ev = ev[~ev.title.str.contains("affirm|maintained under stable|placed under stable|removed under stable|initial reporting|new:", case=False, na=False)]
        short = {e.id: e.short_name for e in active}
        ev = ev.assign(_k=ev.title.str.split(":").str[0].str.strip())          # "DBRS upgrade" once per bank per day, not per rating type
        for x in ev.sort_values("date", ascending=False).drop_duplicates(["entity_id", "date", "_k"]).head(80).itertuples():
            if x.entity_id in short:
                actions.append({"date": str(x.date)[:10], "id": x.entity_id, "short": short[x.entity_id], "title": str(x.title)[:160], "severity": x.severity})
    return {"rows": rows, "actions": actions}


def data_audit(active, facts, ratings, prices, cds, bonds) -> list[dict]:
    """What we hold for each entity: regulatory history (periods, first, last, sources), ratings, prices, CDS, bonds."""
    rows = []
    core = facts[facts.metric == "cet1_ratio"] if not facts.empty else facts
    for e in active:
        g = core[core.entity_id == e.id] if not core.empty else core
        r = ratings[ratings.entity_id == e.id] if not ratings.empty else ratings
        p = prices[prices.entity_id == e.id] if not prices.empty else prices
        c = cds[cds.entity_id == e.id] if not cds.empty else cds
        b = bonds[bonds.entity_id == e.id] if bonds is not None and not bonds.empty else None
        dates = sorted({str(d)[:10] for d in g.reference_date}) if not g.empty else []
        rows.append({"id": e.id, "short": e.short_name, "region": e.region, "type": e.type,
                     "periods": len(dates), "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
                     "years": round((date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25, 1) if len(dates) > 1 else 0,
                     "sources": sorted(set(g.source)) if not g.empty else [],
                     "agencies": int(r.agency.nunique()) if not r.empty else 0,
                     "price_days": int(p.date.nunique()) if not p.empty else 0,
                     "cds_days": int(c.date.nunique()) if not c.empty else 0,
                     "bonds": int(len(b)) if b is not None else 0,
                     "ticker": bool(e.tickers)})
    return rows


def export_json() -> None:
    entities = load_entities()
    facts, ratings, prices, cds, events, runs = (store.read(t) for t in ["facts", "ratings", "prices", "cds", "events", "runs"])
    bond_changes = _bond_changes(store.read("bonds"), store.read("bond_quotes"))
    series_tbl = store.read("series")
    snrfin = series_tbl[series_tbl.series_id == "ITRAXX_SNRFIN_5Y"] if not series_tbl.empty else None
    board, today, details, policy_rows = [], date.today(), {}, []
    active = [e for e in entities if e.active]
    series_all = {e.id: _series(facts[facts.entity_id == e.id] if not facts.empty else facts) for e in active}
    market_all = {e.id: _market(prices[prices.entity_id == e.id] if not prices.empty else prices,
                                cds[cds.entity_id == e.id] if not cds.empty else cds, bond_changes.get(e.id), snrfin) for e in active}
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
        grades = [g for g in (rating_grade(x["value"]) for x in rsum) if g is not None]
        row["rating_grade"] = round(float(pd.Series(grades).median()), 1) if grades else None
        row["rating_composite"] = grade_letter(row["rating_grade"])
        board.append(row)
        # the policy page carries everything a treasurer checks on an approved name, in one record
        short_ratings = []
        if not r.empty:
            sh = r[r.horizon == "short"].sort_values("action_date", ascending=False)
            for ag in AGENCY_ORDER:
                g = sh[sh.agency == ag]
                if not g.empty:
                    short_ratings.append({"letter": AGENCY_LETTER.get(ag, ag[:1].upper()), "value": g.iloc[0].value})
        recent, negative, news30 = [], [], {"bad": 0, "warn": 0, "good": 0}
        if not ev.empty:
            cutoff30 = (today - timedelta(days=30)).isoformat()
            e2 = ev.sort_values("date", ascending=False).drop_duplicates(["date", "title"])
            for x in e2.itertuples():
                if x.type == "news" and str(x.date)[:10] >= cutoff30 and x.severity in news30:
                    news30[x.severity] += 1
                if x.type == "rating" and re.search(r"downgrade|negative|under review for downgrade|withdraw", str(x.title), re.I):
                    negative.append({"date": str(x.date)[:10], "title": str(x.title)[:140]})
                if x.severity != "info" and len(recent) < 8:
                    recent.append({"date": str(x.date)[:10], "type": x.type, "severity": x.severity, "title": str(x.title)[:160], "url": _clean(getattr(x, "url", "")) or ""})
        policy_rows.append({**{k: row[k] for k in ("id", "name", "short", "country", "type", "region", "group", "peer_group", "public_score", "band",
                                                    "coverage", "cet1", "leverage", "leverage_basis", "lcr", "nsfr", "ratings", "market", "asof", "age_days",
                                                    "rating_grade", "rating_composite", "inherited")},
                            "score": row["public_score"], "short_ratings": short_ratings, "recent": recent, "negative": negative[:6], "news30": news30,
                            "market_detail": {k: market.get(k) for k in ("vol30", "drawdown52", "bond_change30", "bond_count")}})
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
            "events": [{k: _clean(v) for k, v in x.items()} for x in _dedupe_events(ev).head(60).to_dict("records")] if not ev.empty else [],
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
    generated = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    store.write_json("board", {"generated": generated, "rows": board, "benchmarks": benchmarks})
    store.write_json("policy", {"generated": generated, "rows": policy_rows})
    store.write_json("audit", {"generated": generated, "rows": data_audit(active, facts, ratings, prices, cds, store.read("bonds"))})
    store.write_json("ratings", {"generated": generated, **ratings_summary(active, ratings, events)})
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
                                "documents": doc_rows, "document_counts": counts, "review": queue,
                                "learning": __import__("bankcredit.learn", fromlist=["summary"]).summary()})
