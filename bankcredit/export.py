"""Turn the Parquet tables into the JSON the static site reads.

Outputs (data/json/):
  board.json      one row per entity with latest metrics, score, ratings summary, market signal, data age
  banks/<id>.json full per-entity payload: metric series, ratings, prices, events, sources
  status.json     last runs per source
"""
from __future__ import annotations

import calendar
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
                "total_assets", "deposits", "uninsured_deposits", "htm_unrealised_loss", "nim", "tier1_leverage", "cost_of_risk"]
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


import os
DEBUG_DATA = bool(os.environ.get("BANKCREDIT_DEBUG_DATA"))   # beta: every driving input on a Data tab per profile
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
    # Provisional weights (6 September 2026, ratings removed 7 September when they became the public
    # score's anchor): three market signals, each worth at most 2.5 points either way, inside the ±10 cap.
    # CDS: level band plus 30-day change. Volatility: 30-day realised. Drawdown: from the 52-week high.
    # A COUNTERPARTY_OVERLAY secret with the same keys replaces this dict at build time.
    "cds_bands": [[40, 1.5], [60, 0.5], [90, 0], [150, -0.5], [1e9, -1.5]],      # [upper bp, adjustment]
    "cds_change_widen_bp": 15, "cds_change_widen_adj": -1.0, "cds_change_tighten_bp": -10, "cds_change_tighten_adj": 1.0,
    # Bonds stand in for the CDS change (never the level) when no fresh CDS exists: 30-day yield change against peers.
    "bond_change_widen_bp": 20, "bond_change_widen_adj": -1.0, "bond_change_tighten_bp": -15, "bond_change_tighten_adj": 1.0,
    "vol_high": 45, "vol_high_adj": -2.5, "vol_low": 25, "vol_low_adj": 2.5,
    "drawdown_adj_threshold": -25, "drawdown_adj": -2.5,
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


def overlay_parts(market: dict, ratings: list[dict]) -> list[tuple[str, float]]:
    """The overlay's components, named, before capping (for the debug view and the Method page)."""
    cfg = overlay_config()
    parts = []
    if market.get("cds5y") is not None:
        c = market["cds5y"]
        for upper, a in cfg["cds_bands"]:
            if c < upper:
                parts.append((f"CDS level {c:.0f} bp (band under {upper:.0f})", a)); break
        chg = market.get("cds_change30")
        if chg is not None:
            if chg > cfg["cds_change_widen_bp"]:
                parts.append((f"CDS 30-day change +{chg:.0f} bp", cfg["cds_change_widen_adj"]))
            elif chg < cfg["cds_change_tighten_bp"]:
                parts.append((f"CDS 30-day change {chg:.0f} bp", cfg["cds_change_tighten_adj"]))
    elif market.get("bond_change30") is not None:
        b = market["bond_change30"]
        if b > cfg["bond_change_widen_bp"]:
            parts.append((f"bond yields vs peers +{b:.0f} bp", cfg["bond_change_widen_adj"]))
        elif b < cfg["bond_change_tighten_bp"]:
            parts.append((f"bond yields vs peers {b:.0f} bp", cfg["bond_change_tighten_adj"]))
    if market.get("vol30") is not None:
        v = market["vol30"]
        parts.append((f"30-day volatility {v:.0f}%", cfg["vol_high_adj"] if v > cfg["vol_high"] else (cfg["vol_low_adj"] if v < cfg["vol_low"] else 0)))
    if market.get("drawdown52") is not None and market["drawdown52"] < cfg["drawdown_adj_threshold"]:
        parts.append((f"drawdown {market['drawdown52']:.0f}% from 52-week high", cfg["drawdown_adj"]))
    return parts


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


AUDIT_METRICS = ["cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "lcr", "nsfr",
                 "overall_capital_requirement", "npl_ratio", "roe", "roa", "efficiency_ratio", "total_assets"]


COMPARE_METRICS = [("score", "Counterparty score", "", 1, True), ("rating_grade", "Composite rating (grade, 1 = AAA)", "", 1, False), ("cet1_ratio", "CET1 ratio", "%", 1, True), ("leverage_ratio", "Leverage ratio", "%", 1, True),
                   ("total_capital_ratio", "Total capital ratio", "%", 1, True), ("lcr", "LCR", "%", 0, True), ("nsfr", "NSFR", "%", 0, True),
                   ("roe", "Return on equity", "%", 1, True), ("roa", "Return on assets", "%", 2, True), ("nim", "Net interest margin", "%", 2, True),
                   ("efficiency_ratio", "Cost to income", "%", 0, False), ("npl_ratio", "Non-performing loans", "%", 2, False),
                   ("cost_of_risk", "Cost of risk", "%", 2, False), ("total_assets", "Total assets", "m", 0, True)]
COMPARE_POINTS = 32


def compare_rows(board: list[dict], series_all: dict) -> list[dict]:
    """Compact per-entity series for the Compare page: the last COMPARE_POINTS periods of each metric."""
    rows = []
    for r in board:
        ser = {}
        for m, *_ in COMPARE_METRICS:
            if m == "score":
                continue
            pts = series_all.get(r["id"], {}).get(m) or []
            if pts:
                ser[m] = [[p["d"], p["v"]] for p in pts[-COMPARE_POINTS:] if p["v"] is not None]
        h = r.get("history") or {}
        sc_series = list(h.get("score") or [])
        last_back = sc_series[-1][0] if sc_series else ""
        sc_series += [[d, v] for d, v, _g in (h.get("snapshots") or []) if d > last_back and v is not None]
        if len(sc_series) >= 2:
            ser["score"] = sc_series[-COMPARE_POINTS:]
        grades = [[d, g] for d, _v, g in (h.get("snapshots") or []) if g is not None]
        if len({d for d, _ in grades}) >= 2:
            ser["rating_grade"] = grades[-COMPARE_POINTS:]
        rows.append({"id": r["id"], "short": r["short"], "name": r["name"], "region": r["region"], "type": r["type"], "country": r["country"],
                     "peer_group": r["peer_group"], "band": r["band"], "score": r["score"], "grade": r["rating_grade"], "rating": r["rating_composite"],
                     "assets": (series_all.get(r["id"], {}).get("total_assets") or [{}])[-1].get("v"), "series": ser})
    return rows


BACKCAST_QUARTERS = 24
STALE_DAYS = 550              # capital ratios older than this cannot carry a score


def _quarter_ends(n: int, today: date) -> list[date]:
    out, y, m = [], today.year, ((today.month - 1) // 3) * 3 + 3
    d = date(y, m, calendar.monthrange(y, m)[1])
    if d > today:
        m -= 3
        if m == 0:
            y, m = y - 1, 12
        d = date(y, m, calendar.monthrange(y, m)[1])
    while len(out) < n:
        out.append(d)
        y, m = (d.year, d.month - 3) if d.month > 3 else (d.year - 1, 12)
        d = date(y, m, calendar.monthrange(y, m)[1])
    return sorted(out)


def score_history(series: dict, composite: float | None, today: date) -> list[dict]:
    """The score recomputed at each of the last quarter ends on the ratios as they stood then, with today's
    method and today's composite rating: a like-for-like path of the ratio pillars through time."""
    out = []
    for q in _quarter_ends(BACKCAST_QUARTERS, today):
        latest = {}
        for m, pts in series.items():
            for p in reversed(pts):
                if p["v"] is not None and p["d"] <= q.isoformat():
                    if (q - date.fromisoformat(p["d"])).days <= 550:
                        latest[m] = p["v"]
                    break
        if not latest:
            continue
        sc = compute(latest, 0.0, composite)
        if sc.public_score is None or sc.coverage < 0.5:          # a half-empty quarter is not a comparable point
            continue
        out.append({"date": q.isoformat(), "score": sc.public_score, "band": sc.band, "coverage": sc.coverage})
    return out


def data_audit(active, facts, ratings, prices, cds, bonds, events=None, board=None) -> list[dict]:
    """What we hold for each entity: regulatory history (periods, first, last, sources) overall and per
    metric, ratings by agency, prices, CDS, bonds and news, with the score the board gives it."""
    rows = []
    core = facts[facts.metric == "cet1_ratio"] if not facts.empty else facts
    by_board = {r["id"]: r for r in (board or [])}
    cutoff90 = (date.today() - timedelta(days=90)).isoformat()
    for e in active:
        f = facts[facts.entity_id == e.id] if not facts.empty else facts
        g = core[core.entity_id == e.id] if not core.empty else core
        r = ratings[ratings.entity_id == e.id] if not ratings.empty else ratings
        p = prices[prices.entity_id == e.id] if not prices.empty else prices
        c = cds[cds.entity_id == e.id] if not cds.empty else cds
        b = bonds[bonds.entity_id == e.id] if bonds is not None and not bonds.empty else None
        ev = events[events.entity_id == e.id] if events is not None and not events.empty else None
        dates = sorted({str(d)[:10] for d in g.reference_date}) if not g.empty else []
        metrics = {}
        for m in AUDIT_METRICS:
            md = sorted({str(d)[:10] for d in f[f.metric == m].reference_date}) if not f.empty else []
            metrics[m] = {"n": len(md), "first": md[0] if md else None, "last": md[-1] if md else None}
        lt = r[r.horizon == "long"] if not r.empty else r           # any long-term rating type: issuer, IDR, deposit, counterparty
        agencies = sorted(set(lt.agency)) if not lt.empty else []
        bd = by_board.get(e.id, {})
        rows.append({"id": e.id, "short": e.short_name, "region": e.region, "type": e.type, "peer_group": e.peer_group,
                     "periods": len(dates), "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
                     "years": round((date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25, 1) if len(dates) > 1 else 0,
                     "sources": sorted(set(f.source)) if not f.empty else [],
                     "metrics": metrics,
                     "agencies": len(agencies), "agency_list": agencies,
                     "rating": bd.get("rating_composite") or "",
                     "price_days": int(p.date.nunique()) if not p.empty else 0,
                     "price_first": str(p.date.min())[:10] if not p.empty else None,
                     "symbol": str(p.symbol.iloc[-1]) if not p.empty and "symbol" in p else "",
                     "cds_days": int(c.date.nunique()) if not c.empty else 0,
                     "bonds": int(len(b)) if b is not None else 0,
                     "news90": int(((ev.type == "news") & (ev.date.astype(str).str[:10] >= cutoff90)).sum()) if ev is not None else 0,
                     "events": int(len(ev)) if ev is not None else 0,
                     "ticker": bool(e.tickers),
                     "score": bd.get("score"), "band": bd.get("band", ""), "coverage": bd.get("coverage")})
    return rows


def export_json() -> None:
    entities = load_entities()
    facts, ratings, prices, cds, events, runs = (store.read(t) for t in ["facts", "ratings", "prices", "cds", "events", "runs"])
    bonds_tbl, quotes_tbl = store.read("bonds"), store.read("bond_quotes")
    bond_changes = _bond_changes(bonds_tbl, quotes_tbl)
    bond_quotes_all = quotes_tbl.merge(bonds_tbl[["isin", "entity_id", "name", "currency"]], on="isin") if not quotes_tbl.empty and not bonds_tbl.empty else None
    series_tbl = store.read("series")
    snrfin = series_tbl[series_tbl.series_id == "ITRAXX_SNRFIN_5Y"] if not series_tbl.empty else None
    board, today, details, policy_rows = [], date.today(), {}, []
    hist_tbl = store.read("history")
    hist_all: dict[str, list] = {}
    if not hist_tbl.empty:
        for r in hist_tbl[hist_tbl.kind == "snapshot"].sort_values("date").itertuples():
            hist_all.setdefault(r.entity_id, []).append({"date": str(r.date)[:10], "score": _clean(r.score), "rating_grade": _clean(r.rating_grade)})
    new_hist: list[dict] = []
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
        grades = [g for g in (rating_grade(x["value"]) for x in rsum) if g is not None]
        composite = round(float(pd.Series(grades).median()), 1) if grades else None
        sc = compute(latest, overlay, composite)
        asof = max((pts[-1]["d"] for pts in series.values() if pts), default=None)
        age = (today - date.fromisoformat(asof)).days if asof else None
        cap_pts = series.get("cet1_ratio") or []
        cap_age = (today - date.fromisoformat(cap_pts[-1]["d"])).days if cap_pts else None
        if sc.final_score is not None and cap_age is not None and cap_age > STALE_DAYS:
            sc.final_score, sc.public_score, sc.band, sc.reason = None, None, "", f"capital ratios from {cap_pts[-1]['d'][:7]}"
        row = {
            "id": e.id, "name": e.name, "short": e.short_name, "country": e.country, "type": e.type,
            "region": e.region, "group": e.group, "peer_group": e.peer_group, "lei": e.lei,
            "score": sc.final_score, "public_score": sc.public_score, "band": sc.band, "coverage": sc.coverage, "unscored": sc.reason,
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
        row["rating_grade"] = composite
        row["rating_composite"] = grade_letter(composite)
        row["unrated"] = sc.unrated
        back = score_history(series, composite, today)
        snaps = hist_all.get(e.id, [])
        row["history"] = {"score": [[h["date"], h["score"]] for h in back],
                          "snapshots": [[h["date"], h["score"], h["rating_grade"]] for h in snaps]}
        new_hist.append({"entity_id": e.id, "date": today, "kind": "snapshot", "score": sc.final_score, "band": sc.band,
                         "rating_grade": composite, "coverage": sc.coverage})
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
        debug = {}
        if DEBUG_DATA:
            cd = cds[cds.entity_id == e.id].sort_values("date") if not cds.empty else cds
            bq = bond_quotes_all[bond_quotes_all.entity_id == e.id].sort_values(["isin", "date"]) if bond_quotes_all is not None and not bond_quotes_all.empty else None
            debug = {
                "cds": [{"date": str(x.date)[:10], "tier": x.tier, "source": x.source, "level_bp": _clean(float(x.level_bp)),
                         "trades": _clean(float(x.trades)) if hasattr(x, "trades") and x.trades == x.trades else None} for x in cd.tail(200).itertuples()] if not cd.empty else [],
                "bonds": [{"isin": x.isin, "name": x.name, "currency": x.currency, "date": str(x.date)[:10], "price": _clean(float(x.price)), "yield": _clean(float(x["yield"]))}
                          for _, x in bq.iterrows()] if bq is not None else [],
                "market": {k: _clean(v) for k, v in market.items()},
                "overlay": [{"part": k, "adj": v} for k, v in overlay_parts(market, rsum)],
                "overlay_total": sc.overlay, "score_public": sc.public_score, "score_final": sc.final_score,
                "facts": [{"metric": x.metric, "date": str(x.reference_date)[:10], "value": _clean(float(x.value)), "unit": x.unit, "basis": x.basis,
                           "source": x.source, "method": x.method, "confidence": _clean(float(x.confidence)), "document": x.document, "page": _clean(x.page)}
                          for x in f.sort_values(["metric", "reference_date"]).itertuples()] if not f.empty else [],
            }
        details[e.id] = (row, {
            "debug": debug,
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
    if new_hist:
        store.upsert("history", pd.DataFrame(new_hist))
    store.write_json("board", {"generated": generated, "rows": [{k: v for k, v in r.items() if k != "history"} for r in board], "benchmarks": benchmarks})
    store.write_json("policy", {"generated": generated, "rows": policy_rows})
    store.write_json("audit", {"generated": generated, "rows": data_audit(active, facts, ratings, prices, cds, store.read("bonds"), events, board)})
    store.write_json("compare", {"generated": generated, "metrics": COMPARE_METRICS, "rows": compare_rows(board, series_all)})
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
