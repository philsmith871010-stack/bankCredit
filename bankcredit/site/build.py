"""Static site generator. Reads data/json, writes site/."""
from __future__ import annotations

import json
import re
import shutil

from .. import store
from datetime import date, datetime, timedelta
from pathlib import Path

from ..export import AGENCY_LETTER
from ..models import METRICS
from ..score import PILLARS, BANDS, OVERLAY_CAP, RATING_WEIGHT, RATING_SCORE, UNRATED_SCORE, UNRATED_CAP, VERSION, score_cap
from ..export import _SP_SCALE as GRADE_LETTERS
from . import components as c

ROOT = Path(__file__).resolve().parent.parent.parent
JSON = ROOT / "data" / "json"
OUT = ROOT / "site"
ASSETS = Path(__file__).resolve().parent / "assets"
REGION_LABEL = {"uk": "UK", "eu": "EU and EEA", "aus_can": "Australia and Canada", "asia": "Asia", "gulf": "Gulf", "us_ch": "US and Swiss"}
TYPE_LABEL = {"bank": "Bank", "building_society": "Building society", "subsidiary": "Overseas-owned bank", "holding": "Group"}
COUNTRY = {"GB": "UK", "FI": "Finland", "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "NL": "Netherlands", "DE": "Germany", "FR": "France", "BE": "Belgium", "ES": "Spain", "IT": "Italy", "AT": "Austria", "IE": "Ireland", "AU": "Australia", "CA": "Canada", "SG": "Singapore", "HK": "Hong Kong", "JP": "Japan", "QA": "Qatar", "AE": "UAE", "SA": "Saudi Arabia", "US": "US", "CH": "Switzerland"}
TILE_METRICS = [("cet1_ratio", "CET1 ratio", "%", 1), ("leverage_ratio", "Leverage ratio", "%", 1), ("total_capital_ratio", "Total capital", "%", 1),
                ("lcr", "LCR", "%", 0), ("nsfr", "NSFR", "%", 0), ("rwa", "Risk-weighted assets", "m", 0)]


def sc(r):
    return "" if r["score"] is None else f"{r['score']:.0f}"


def load(name):
    return json.loads((JSON / f"{name}.json").read_text())


def qlabel(d: str) -> str:
    dt = date.fromisoformat(d[:10])
    return dt.strftime("%b %y")


def age_badge(asof, age):
    if not asof:
        return '<span class="age age-none">no data</span>'
    late = age is not None and age > 150
    return f'<span class="age{" age-late" if late else ""}" title="Reference date of the latest regulatory figures">{c.esc(asof)}</span>'


def benchmark_strip(board):
    bm = board.get("benchmarks") or []
    if not bm:
        return ""
    cells = "".join(f'<div class="bm"><div class="bm-label">{c.esc(b["label"])}</div><div class="bm-val"><span class="mono big-sm">{b["value"]:.0f}</span><span class="unit">bp</span>{c.chg(b["change30"], 0, "bp") if b.get("change30") is not None else ""}</div>{c.spark(b["spark"])}<div class="muted small mono">{c.esc(b["date"])}</div></div>' for b in bm)
    return f'<div class="card pad bm-strip"><div class="bm-head"><h3>Credit benchmarks</h3><span class="muted small">ICE BofA option-adjusted spreads via FRED · 30-day change</span></div><div class="bm-grid">{cells}</div></div>'


def today_strip(board) -> str:
    """The board's opening row: what the universe looks like today and what moved this week."""
    rows = board["rows"]
    today = datetime.utcnow().date()
    since7 = (today - timedelta(days=7)).isoformat()
    bands = {b: sum(1 for r in rows if r["band"] == b) for b in "ABCDE"}
    bands["?"] = sum(1 for r in rows if r["score"] is not None and r["band"] in ("?", ""))
    scored = sum(bands.values())
    bar = "".join(f'<i class="band-{b if b != "?" else "x"}" style="flex:{n}" title="{"Band " + b if b != "?" else "Provisional, no band"}: {n}"></i>' for b, n in bands.items() if n)
    legend = " ".join(f'<span><b class="band-{b if b != "?" else "x"}"></b>{b if b != "?" else "no band"} {n}</span>' for b, n in bands.items() if n)
    try:
        acts = [a for a in load("ratings").get("actions", []) if str(a.get("date", ""))[:10] >= since7]
    except Exception:
        acts = []
    up = sum(1 for a in acts if a.get("severity") == "good")
    down = sum(1 for a in acts if a.get("severity") == "bad")
    flagged = {"bad": 0, "warn": 0, "good": 0}
    for r in rows:
        for e in (load(f"banks/{r['id']}").get("events") or []):
            if e.get("type") == "news" and str(e.get("date"))[:10] >= since7 and e.get("severity") in flagged:
                flagged[e["severity"]] += 1
    ages = sorted(r["age_days"] for r in rows if r.get("age_days") is not None)
    med_age = ages[len(ages) // 2] if ages else None
    stale = sum(1 for a in ages if a > 150)
    widening = sum(1 for r in rows if (r.get("market") or {}).get("direction") == "down")
    return f'''<div class="today">
<a class="tcard" href="#board"><span class="tl">Scored</span><span class="tv mono">{scored}<small> of {len(rows)}</small></span><span class="tbar">{bar}</span><span class="tlegend small">{legend}</span></a>
<a class="tcard" href="ratings/index.html"><span class="tl">Rating actions, 7 days</span><span class="tv mono">{len(acts)}</span><span class="small"><span class="good">▲ {up} up or positive</span> · <span class="bad">▼ {down} down or negative</span></span></a>
<a class="tcard" href="events/index.html"><span class="tl">Flagged headlines, 7 days</span><span class="tv mono">{sum(flagged.values())}</span><span class="small"><span class="bad">{flagged["bad"]} adverse</span> · <span style="color:#b35900">{flagged["warn"]} watch</span> · <span class="good">{flagged["good"]} positive</span></span></a>
<a class="tcard" href="compare/index.html"><span class="tl">Market signal widening</span><span class="tv mono">{widening}</span><span class="small muted">names whose CDS, bonds or equity moved the wrong way in 30 days</span></a>
<a class="tcard" href="coverage/index.html"><span class="tl">Figures as of</span><span class="tv mono">{med_age if med_age is not None else "—"}<small> days, median</small></span><span class="small {"bad" if stale > 20 else "muted"}">{stale} names older than 150 days</span></a>
</div>'''


def page_board(board, generated):
    rows = sorted(board["rows"], key=lambda r: (r["score"] is None, -(r["score"] or 0), r["name"]))
    counts = {}
    for r in rows:
        counts[r["region"]] = counts.get(r["region"], 0) + 1
    filters = f'<button class="filter active" data-region="all">All · {len(rows)}</button>' + "".join(
        f'<button class="filter" data-region="{k}">{REGION_LABEL[k]} · {counts.get(k, 0)}</button>' for k in REGION_LABEL if counts.get(k)) + \
        '<button class="filter" data-region="watch">Watchlist</button>'
    trs = []
    for r in rows:
        peer = r.get("peer") or {}
        sub = f'{TYPE_LABEL.get(r["type"], r["type"])} · {COUNTRY.get(r["country"], r["country"])}'
        trs.append(f'''<tr data-id="{r["id"]}" data-region="{r["region"]}" data-score="{r["score"] if r["score"] is not None else -1}" data-name="{c.esc(r["name"])}">
<td class="col-name"><button class="watch" data-id="{r["id"]}" aria-label="Watch">{c.use_icon("star", 15, "#cbd3dc")}</button><a href="banks/{r["id"]}.html"><span class="nm">{c.esc(r["name"])}</span><span class="sub">{sub}</span></a></td>
<td class="col-score"><span class="mono score{" score-prov" if r["band"] in ("?", "") and r["score"] is not None else ""}"{' title="Provisional: too little ratio data for a band"' if r["band"] in ("?", "") and r["score"] is not None else ""}>{sc(r)}</span>{c.ribbon(r["score"], peer.get("p25"), peer.get("p50"), peer.get("p75"))}</td>
<td class="col-band">{c.band_chip(r["band"])}</td>
<td class="num">{c.fmt(r["cet1"], 1, "%")}</td><td class="num">{c.fmt(r["leverage"], 1, "%")}{'<sup class="muted" title="US Tier 1 leverage ratio on average assets, not the Basel leverage ratio">T1</sup>' if r.get("leverage_basis") == "us_tier1" else ""}</td><td class="num">{c.fmt(r["lcr"], 0, "%")}</td>
<td>{c.agency_chips(r["ratings"])}</td><td class="col-mkt">{c.market_glyph(r["market"])}</td>
<td class="col-asof">{age_badge(r["asof"], r["age_days"])}</td></tr>''')
    n_scored = sum(1 for r in rows if r["score"] is not None)
    content = f'''<div class="page-head"><div><h1>Board</h1><div class="lede">{len(rows)} banks and building societies · {n_scored} with enough data to score · figures as of the date on each row</div></div>
<div class="actions"><label class="search">{c.ico("search", 16, c.MUTED)}<input id="q" type="search" placeholder="Search bank or country" aria-label="Search"></label></div></div>
{today_strip(board)}
{benchmark_strip(board)}
<div class="filters" id="filters">{filters}</div>
<div class="card table-card"><div class="table-wrap"><table class="board" id="board"><thead><tr>
<th data-sort="name">Bank</th><th data-sort="score">Score · peers</th><th>Band</th><th class="num" data-sort="cet1">CET1</th><th class="num" data-sort="leverage">Lev.</th><th class="num" data-sort="lcr">LCR</th><th>Ratings</th><th>Mkt</th><th data-sort="asof">As of</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>
<div class="table-foot"><span>Ratings from the ESMA register with agency attribution · Mkt is the 30-day direction of the market signal, never a level · a grey band means not enough data yet · Lev. marked T1 is the US Tier 1 leverage ratio, scored on its own scale</span><span class="legend">{c.ribbon(72, 52, 64, 74, 60, 8)} peer 25th to 75th percentile, median in orange</span></div></div>'''
    return c.shell("Board", content, "board", "", generated)


NAV_TYPES = [("bank", "Banks"), ("building_society", "Building societies"), ("holding", "Groups"), ("subsidiary", "Overseas-owned banks")]
NAV_GRADES = [("top", "AA- and above"), ("a", "A range"), ("bbb", "BBB range"), ("sub", "Below BBB-"), ("nr", "Unrated")]


def _grade_bucket(r) -> str:
    g = r.get("rating_grade")
    if g is None:
        return "nr"
    return "top" if g <= 4 else "a" if g <= 7 else "bbb" if g <= 10 else "sub"


def page_banks_index(board, generated):
    rows = board["rows"]
    by_id = {r["id"]: r for r in rows}
    # families: a parent first, its subsidiaries beneath it; an entity whose group is not covered stands alone
    order = []
    for r in sorted(rows, key=lambda r: r["name"].lower()):
        if r["group"] and r["group"] in by_id:
            continue
        order.append((r, 0))
        for ch in sorted((x for x in rows if x["group"] == r["id"]), key=lambda x: x["name"].lower()):
            order.append((ch, 1))
    items = []
    for i, (r, depth) in enumerate(order):
        rating = (f'<b>{c.esc(r["rating_composite"])}</b><span class="muted small"> {len(r["ratings"])} ag.</span>' if r["ratings"]
                  else '<span class="muted small">unrated</span>')
        age = r["age_days"]
        asof = (f'<span class="age {"age-late" if age and age > 150 else ""}">{c.esc(r["asof"])}</span>' if r["asof"] else '<span class="muted">—</span>')
        news = r.get("events90") or 0
        items.append(
            f'<div class="nv-row{" nv-child" if depth else ""}" data-id="{c.esc(r["id"])}" data-i="{i}" data-name="{c.esc(r["name"].lower())} {c.esc(r["short"].lower())} {c.esc(r["id"])}" '
            f'data-region="{c.esc(r["region"])}" data-type="{c.esc(r["type"])}" data-band="{c.esc(r["band"] or "?")}" data-grade="{_grade_bucket(r)}" '
            f'data-score="{r["score"] if r["score"] is not None else -1}" data-g="{r["rating_grade"] if r["rating_grade"] is not None else 99}" data-asof="{c.esc(r["asof"] or "")}" data-group="{c.esc(r["group"] or "")}">'
            f'<button class="watch" data-id="{c.esc(r["id"])}" aria-label="Watch">{c.use_icon("star", 15, "#cbd3dc")}</button>'
            f'<a class="nv-name" href="{c.esc(r["id"])}.html"><span class="nm">{c.esc(r["name"])}</span><span class="sub">{TYPE_LABEL.get(r["type"], r["type"])} · {COUNTRY.get(r["country"], r["country"])}{(" · part of " + c.esc(by_id[r["group"]]["short"])) if r["group"] in by_id else ""}</span></a>'
            f'<span class="nv-band">{c.band_chip(r["band"])}</span><span class="nv-score mono">{sc(r) or "—"}</span>'
            f'<span class="nv-rating">{rating}</span><span class="nv-mkt">{c.market_glyph(r["market"])}</span>'
            f'<span class="nv-news mono small" title="headlines kept in 90 days">{news or ""}</span><span class="nv-asof mono small">{asof}</span></div>')
    regions = [("all", "All regions")] + [(k, v) for k, v in REGION_LABEL.items()]
    chips = lambda key, opts: "".join(f'<button class="filter nv-f" data-key="{key}" data-val="{k}">{c.esc(l)}<span class="cnt"></span></button>' for k, l in opts)
    content = f'''<div class="page-head"><div><h1>Bank navigator</h1><div class="lede">Every covered entity in one list. Type to search; combine the filters; families sit together, subsidiaries beneath their parent.</div></div></div>
<div class="card nv-card"><div class="nv-tools">
<div class="search">{c.ico("search", 16, c.MUTED)}<input id="nvq" placeholder="Name, short name or country" autocomplete="off"></div>
<label class="nv-sort small muted">Sort <select id="nvsort"><option value="family">Family, A to Z</option><option value="score">Score, high to low</option><option value="rating">Rating, strong to weak</option><option value="asof">Freshest figures</option><option value="name">Name</option></select></label>
<span class="nv-count small muted" id="nvcount"></span></div>
<div class="nv-facets">
<div class="filters" data-facet="region">{chips("region", regions)}</div>
<div class="filters" data-facet="type"><button class="filter nv-f" data-key="type" data-val="all">All types<span class="cnt"></span></button>{chips("type", NAV_TYPES)}</div>
<div class="filters" data-facet="band"><button class="filter nv-f" data-key="band" data-val="all">Any band<span class="cnt"></span></button>{chips("band", [(b, "Band " + b) for b in "ABCDE"] + [("?", "No band yet")])}</div>
<div class="filters" data-facet="grade"><button class="filter nv-f" data-key="grade" data-val="all">Any rating<span class="cnt"></span></button>{chips("grade", NAV_GRADES)}</div>
<div class="filters" data-facet="watch"><button class="filter nv-f" data-key="watch" data-val="all">Everyone<span class="cnt"></span></button><button class="filter nv-f" data-key="watch" data-val="watch">Watching<span class="cnt"></span></button></div>
</div>
<div class="nv-head"><span></span><span>Entity</span><span>Band</span><span>Score</span><span>Rating</span><span>Mkt</span><span title="headlines kept in 90 days">News</span><span>As of</span></div>
<div class="nv-list" id="nvlist">{"".join(items)}</div>
<div class="empty" id="nvempty" hidden>Nothing matches. Clear a filter or shorten the search.</div></div>'''
    return c.shell("Bank navigator", content, "banks", "../", generated).replace("</body>", '<script src="../assets/navigator.js"></script></body>')

def tile(metric, label, unit, dp, series, peer_median=None):
    pts = series.get(metric, [])
    if not pts:
        return f'<div class="tile tile-empty"><span class="tile-label">{label}</span><span class="na big">—</span><span class="tile-foot">not yet collected</span></div>'
    vals = [p["v"] for p in pts[-8:]]
    last, prev = pts[-1], (pts[-2] if len(pts) > 1 else None)
    v = last["v"]
    if unit == "m":
        shown, u = (v / 1000, "bn") if v and v > 5000 else (v, "m")
        dpv = 1
    else:
        shown, u, dpv = v, unit, dp
    delta = (v - prev["v"]) if prev and prev["v"] is not None and v is not None else None
    if delta is not None and unit == "m":
        delta = (v / prev["v"] - 1) * 100 if prev["v"] else None
    src = f'{last["src"]} · {last["method"]}' + (f' · p.{int(last["page"])}' if last.get("page") else "")
    unverified = c.chip("unverified", "warn") if (last.get("conf") or 1) < 0.9 and str(last.get("method", "")).startswith("pdf") else ""
    if last.get("basis") == "group":
        unverified += c.chip("group figure", "navy")
    return f'''<div class="tile"><div class="tile-head"><span class="tile-label">{label}</span><span class="tile-flags">{unverified}<span class="src-dot" title="{c.esc(src)}">{c.ico("info", 14, "#b8c2cc")}</span></span></div>
<div class="tile-body"><div><span class="mono big">{shown:,.{dpv}f}</span><span class="mono unit">{u}</span></div>{c.spark(vals)}</div>
<div class="tile-foot"><span>{c.chg(delta, 1, "%" if unit == "m" else "") if delta is not None else "<span class=na>first period</span>"}{" vs prior" if delta is not None else ""}</span><span class="mono">{c.esc(last["d"])}</span></div></div>'''


def debug_panel(b) -> str:
    """Beta only: every input that drives this profile, raw. Switched on by BANKCREDIT_DEBUG_DATA at build time."""
    D = b["debug"]
    def tbl(cols, rows, fmt=None):
        head = "".join(f"<th>{c.esc(h)}</th>" for h in cols)
        body = "".join("<tr>" + "".join(f'<td class="mono small">{c.esc("" if r.get(k) is None else (fmt or {}).get(k, str)(r.get(k)))}</td>' for k in cols) + "</tr>" for r in rows)
        return f'<div class="table-wrap"><table class="plain"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>' if rows else '<div class="empty">none</div>'
    m = D.get("market") or {}
    mrows = [{"key": k, "value": v} for k, v in m.items()]
    orows = [{"part": x["part"], "adj": f'{x["adj"]:+.2f}'} for x in D.get("overlay") or []]
    scores = f'<p class="small">Public score <span class="mono b">{D.get("score_public")}</span> · overlay total <span class="mono b">{D.get("overlay_total")}</span> (capped) · final <span class="mono b">{D.get("score_final")}</span></p>'
    cds = D.get("cds") or []
    bonds = D.get("bonds") or []
    facts = D.get("facts") or []
    return (f'<section class="panel" data-panel="data"><div class="note" style="margin-bottom:10px">Beta view for building and checking: every raw input behind this profile. CDS and bond quotes are shown here under the sources\' private-use terms and this tab is removed for production.</div>'
            f'<h3>Score</h3>{scores}<h4>Overlay components (before the ±cap)</h4>{tbl(["part", "adj"], orows)}'
            f'<h3>Market signal internals</h3>{tbl(["key", "value"], mrows)}'
            f'<h3>CDS ({len(cds)} rows, newest last)</h3>{tbl(["date", "tier", "source", "level_bp", "trades"], cds)}'
            f'<h3>Bond quotes ({len(bonds)} rows)</h3>{tbl(["isin", "name", "currency", "date", "price", "yield"], bonds)}'
            f'<h3>Facts ({len(facts)} rows)</h3>{tbl(["metric", "date", "value", "unit", "basis", "source", "method", "confidence", "page", "document"], facts)}</section>')


def ratings_tile(b) -> str:
    """Agency ratings as the first tile of the profile: long-term rating, outlook, short-term rating, date, per agency,
    with the composite grade and the market direction alongside the regulatory KPIs."""
    rs = b.get("ratings") or []
    if not rs:
        return '<div class="tile tile-ratings tile-empty"><span class="tile-label">Agency ratings</span><span class="na big">NR</span><span class="tile-foot">no public issuer rating in the ESMA register</span></div>'
    short = {}
    for x in b.get("ratings_all") or []:
        if x.get("horizon") == "short" and x["agency"] not in short:
            short[x["agency"]] = x["value"]
    names = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's", "dbrs": "DBRS", "kbra": "KBRA", "scope": "Scope", "jcr": "JCR"}
    cells = "".join(
        f'<div class="rcell"><div class="ragency">{c.esc(names.get(r["agency"], r["agency"]))}</div>'
        f'<div class="rlt"><span class="mono big">{c.esc(r["value"])}</span> {outlook_glyph(r.get("outlook"))}</div>'
        f'<div class="rst small muted">{("ST " + c.esc(short[r["agency"]])) if r["agency"] in short else ""}{(" · " if r["agency"] in short else "") + c.esc(str(r.get("type") or "").replace("_", " ")) if r.get("type") not in ("idr", "issuer") else ""}</div>'
        f'<div class="rdate mono small muted">{c.esc(r.get("date") or "")}</div></div>' for r in rs)
    grade = b.get("rating_grade")
    comp = f'<span class="band mono" style="background:{grade_colour(grade)};color:{"#fff" if grade is not None and grade <= 10 else "#243240"}">{c.esc(b.get("rating_composite") or "NR")}</span>'
    return (f'<div class="tile tile-ratings"><div class="tile-head"><span class="tile-label">Agency ratings</span><span class="tile-flags">composite {comp} {c.market_glyph(b.get("market") or {})} <span class="small muted">{c.esc((b.get("market") or {}).get("label") or "")}</span></span></div>'
            f'<div class="rcells">{cells}</div><div class="tile-foot"><span>ESMA European Rating Platform, checked daily · ▲ positive ▼ negative ◆ watch ▶ stable</span><span><a href="../ratings/index.html">All ratings</a></span></div></div>')


def page_bank(b, generated):
    series = b["series"]
    tiles = ratings_tile(b) + "".join(tile(m, l, u, dp, series) for m, l, u, dp in TILE_METRICS)
    peer = b.get("peer") or {}
    score = b["score"]
    score_html = f'<span class="mono huge">{score:.0f}</span>' if score is not None else '<span class="mono huge muted">—</span>'
    pct = f'<span class="mono">{b["percentile"]}th</span> percentile of {peer.get("n", 0)} peers' if b.get("percentile") is not None else "not enough data to place among peers"
    cov = b.get("coverage") or 0
    overlay = b.get("overlay")
    pillars = b["score_detail"]["pillars"]
    order = ["rating", "capital", "liquidity", "stability", "asset_quality", "profitability"]
    prow = "".join(f'<div class="pillar{" pillar-na" if pillars[k][0] is None else ""}"><span class="pl">{ {"rating": "Rating", "capital": "Capital", "liquidity": "Liquidity", "stability": "Stability", "asset_quality": "Assets", "profitability": "Profit"}[k]}</span>'
                   f'<span class="mono">{"—" if pillars[k][0] is None else f"{pillars[k][0]:.0f}"}</span><i><b style="width:{0 if pillars[k][0] is None else pillars[k][0]:.0f}%"></b></i>'
                   f'<span class="pw">w {pillars[k][1] if pillars[k][0] is not None else PILLARS.get(k, (0,))[0]}</span></div>' for k in order if k in pillars)
    # trends: small multiples grouped by theme, each opening a full-size chart
    TREND_GROUPS = [("Capital", [("cet1_ratio", "CET1 ratio", "%", 1), ("tier1_ratio", "Tier 1 ratio", "%", 1), ("total_capital_ratio", "Total capital ratio", "%", 1),
                                 ("leverage_ratio", "Leverage ratio", "%", 1), ("tier1_leverage", "Tier 1 leverage (US)", "%", 1), ("rwa", "Risk-weighted assets", "m", 0)]),
                    ("Liquidity and funding", [("lcr", "LCR", "%", 0), ("nsfr", "NSFR", "%", 0), ("deposits", "Deposits", "m", 0)]),
                    ("Profitability and efficiency", [("roe", "Return on equity", "%", 1), ("roa", "Return on assets", "%", 2), ("nim", "Net interest margin", "%", 2), ("efficiency_ratio", "Cost to income", "%", 0)]),
                    ("Asset quality", [("npl_ratio", "Non-performing loans", "%", 2), ("cost_of_risk", "Cost of risk", "%", 2)]),
                    ("Balance sheet", [("total_assets", "Total assets", "m", 0)])]
    LOWER_BETTER = {"efficiency_ratio", "npl_ratio", "cost_of_risk"}
    charts, n_charts = [], 0
    hist = b.get("history") or {}
    standing = []
    sc_pts = [(qlabel(d), v) for d, v in (hist.get("score") or []) if v is not None]
    if len(sc_pts) >= 2:
        last, prev = sc_pts[-1][1], sc_pts[-2][1]; delta = last - prev
        dchip = f'<span class="delta {"up" if delta >= 0 else "down"}">{"+" if delta > 0 else ("−" if delta < 0 else "")}{abs(delta):.1f}</span>' if abs(delta) > 0.05 else '<span class="delta flat">no change</span>'
        big = c.chart(sc_pts, unit="", dp=1, w=720, h=300, ymin=0, ymax=100, step=20)
        small = c.chart(sc_pts, unit="", dp=1, w=300, h=96, compact=True)
        standing.append(f'<button class="sm" type="button" data-title="Counterparty score, recomputed" data-sub="Today\'s method and composite rating applied to the ratios as they stood at each quarter end · {len(sc_pts)} quarters" aria-label="Expand score history">'
                        f'<div class="sm-head"><span class="sm-label">Score, recomputed</span><span class="sm-val mono">{last:.0f}</span></div><div class="sm-sub">{dchip}<span class="muted">vs {c.esc(sc_pts[-2][0])}</span></div>{small}<template>{big}</template></button>')
    snaps = [(d[5:], v) for d, v, _g in (hist.get("snapshots") or []) if v is not None]
    if len(snaps) >= 2:
        big = c.chart(snaps, unit="", dp=1, w=720, h=300, ymin=0, ymax=100, step=20)
        small = c.chart(snaps, unit="", dp=1, w=300, h=96, compact=True)
        standing.append(f'<button class="sm" type="button" data-title="Published score, daily" data-sub="The score as published on each build since snapshots began · {len(snaps)} days" aria-label="Expand published score">'
                        f'<div class="sm-head"><span class="sm-label">Published score</span><span class="sm-val mono">{snaps[-1][1]:.0f}</span></div><div class="sm-sub"><span class="muted">since {c.esc(hist["snapshots"][0][0])}</span></div>{small}<template>{big}</template></button>')
    if standing:
        charts.append(f'<div class="sm-group"><h4>Standing</h4><div class="sm-grid">{"".join(standing)}</div></div>')
        n_charts += len(standing)
    for group, metrics in TREND_GROUPS:
        cards = []
        for metric, label, unit, dp in metrics:
            pts = series.get(metric, [])
            if len(pts) < 2:
                continue
            req = None; req_label = "Requirement"
            if metric == "cet1_ratio":
                r = series.get("cet1_requirement") or series.get("overall_capital_requirement")
                if r:
                    req = r[-1]["v"]; req_label = "CET1 requirement" if series.get("cet1_requirement") else "Overall requirement"
            shown = pts if len(pts) <= 48 else pts[-48:]                       # up to twelve years of quarters
            u = unit
            if u == "m":
                u = "bn" if any(p["v"] and abs(p["v"]) > 5000 for p in shown) else "m"
            data = [(qlabel(p["d"]), (p["v"] / 1000 if u == "bn" else p["v"])) for p in shown]
            cdp = 0 if u != "%" or metric in ("lcr", "nsfr") else dp
            last, prev = data[-1][1], data[-2][1]
            delta = last - prev
            good = (delta >= 0) != (metric in LOWER_BETTER)
            dchip = f'<span class="delta {"up" if good else "down"}">{"+" if delta > 0 else ("−" if delta < 0 else "")}{abs(delta):.{cdp}f}{u if u == "%" else ""}</span>' if abs(delta) > 0 else '<span class="delta flat">no change</span>'
            big = c.chart(data, unit="" if u in ("m", "bn") else u, req=req, req_label=req_label, dp=cdp, w=720, h=300)
            small = c.chart(data, unit="" if u in ("m", "bn") else u, req=req, dp=cdp, w=300, h=96, compact=True)
            src = pts[-1].get("src", "")
            cards.append(f'<button class="sm" type="button" data-title="{c.esc(label)}" data-sub="{c.esc(METRICS.get(metric, ""))} · {len(data)} periods · {c.esc(src)}" aria-label="Expand {c.esc(label)}">'
                         f'<div class="sm-head"><span class="sm-label">{c.esc(label)}</span><span class="sm-val mono">{last:,.{cdp}f}<small>{u if u != "m" else "m"}</small></span></div>'
                         f'<div class="sm-sub">{dchip}<span class="muted">vs {c.esc(data[-2][0])}</span></div>{small}<template>{big}</template></button>')
            n_charts += 1
        if cards:
            charts.append(f'<div class="sm-group"><h4>{group}</h4><div class="sm-grid">{"".join(cards)}</div></div>')
    ratings_rows = "".join(f'<tr><td>{c.esc(r["agency"])}</td><td class="muted">{c.esc(r["type"].replace("_", " "))} · {c.esc(r["horizon"])}</td><td class="mono b">{c.esc(r["value"])}</td><td class="muted">{c.esc(r["outlook"])}</td><td class="mono muted">{c.esc(r["date"])}</td></tr>' for r in b["ratings_all"])
    ratings_html = f'<table class="plain"><thead><tr><th>Agency</th><th>Type</th><th>Rating</th><th>Outlook</th><th>Date</th></tr></thead><tbody>{ratings_rows}</tbody></table><div class="note">Source: ESMA European Rating Platform, checked daily. Symbols shown with agency attribution; histories are not redistributed.</div>' if ratings_rows else '<div class="empty">No issuer-level ratings found in the ESMA register for this entity.</div>'
    mp = b["market_public"]
    bond_line = ""
    if mp.get("bond_change30") is not None:
        n, w = mp.get("bond_count") or 0, mp.get("bond_window") or 0
        v = mp["bond_change30"]
        col = c.RED if v > 10 else (c.GREEN if v < -10 else c.MUTED)       # wider is worse, so the colours run the other way
        sign = "+" if v > 0 else ("−" if v < 0 else "")
        bond_line = f'<div><span>Bond yields vs peers, {w}-day</span><span class="mono" style="color:{col};font-weight:500">{sign}{abs(v):.0f} bp <span class="muted" style="font-weight:400">({n} bond{"s" if n != 1 else ""}, {c.esc(mp.get("bond_asof") or "")})</span></span></div>'
    prices = b["prices"]
    price_chart = c.chart([(p["d"][2:7], p["c"]) for p in prices[::max(1, len(prices)//60)]], unit="", dp=2) if len(prices) > 5 else '<div class="empty">Not listed, or no price data collected.</div>'
    market_html = f'''<div class="grid-2"><div class="chart-block"><div class="chart-head"><span>Share price, 12 months</span><span class="muted">{c.esc(b.get("price_currency") or "")}</span></div>{price_chart}</div>
<div class="kv"><div><span>30-day realised volatility</span>{c.fmt(mp.get("vol30"), 1, "%")}</div><div><span>Drawdown from 52-week high</span>{c.fmt(mp.get("drawdown52"), 1, "%")}</div><div><span>Market signal</span><span>{c.market_glyph(mp)} {c.esc(mp.get("label"))}</span></div><div><span>Last price</span><span class="mono">{c.esc(mp.get("last_price_date") or "—")}</span></div>{bond_line}
<div class="note">CDS levels, bond yields and agency ratings feed the private market overlay and are never shown as levels; only the direction and the change against peers are public.</div></div></div>'''
    # sources
    docs = {}
    for m, pts in series.items():
        for p in pts:
            key = (p["src"], p["doc"])
            docs.setdefault(key, {"metrics": set(), "dates": set(), "method": p["method"]})
            docs[key]["metrics"].add(m); docs[key]["dates"].add(p["d"])
    SOURCE_NAMES = {"pillar3": "Firm's Pillar 3 disclosures", "eba_te": "EBA Transparency Exercise", "eba": "EBA Pillar 3 Data Hub", "esef": "ESEF annual accounts (filings.xbrl.org)",
                    "fundamentals": "Yahoo Finance fundamentals", "edgar": "SEC EDGAR XBRL filings", "fdic": "FDIC Call Reports", "us_capital": "US Pillar 3 report", "us_lcr": "US LCR disclosure"}
    by_src: dict[str, dict] = {}
    for (src, doc), v in docs.items():
        g = by_src.setdefault(src, {"docs": [], "metrics": set(), "dates": set(), "method": v["method"]})
        g["docs"].append((max(v["dates"]), doc)); g["metrics"] |= v["metrics"]; g["dates"] |= v["dates"]
    src_rows = ""
    for src, g in sorted(by_src.items(), key=lambda kv: -len(kv[1]["dates"])):
        latest = max(g["docs"])[1]
        n = len(g["docs"])
        src_rows += (f'<div class="doc"><span class="doc-ico">{c.ico("doc", 18, c.NAVY)}</span><div><div class="b">{c.esc(SOURCE_NAMES.get(src, src))} <span class="muted small">· {c.esc(g["method"])}</span></div>'
                     f'<div class="muted small">{n} document{"s" if n != 1 else ""} · {len(g["metrics"])} metrics · {min(g["dates"])} to {max(g["dates"])}</div></div>'
                     f'<a class="filter" href="{c.esc(latest)}" target="_blank" rel="noopener">Latest source</a></div>')
    metric_rows = "".join(f'<tr><td>{c.esc(METRICS.get(m, m))}</td><td class="mono">{pts[-1]["v"]:,.2f}</td><td class="mono muted">{pts[-1]["d"]}</td><td class="muted">{c.esc(pts[-1]["src"])} · {c.esc(pts[-1]["method"])}</td><td class="mono muted">{pts[-1]["conf"]:.2f}{" " + c.chip("unverified", "warn") if (pts[-1]["conf"] or 1) < 0.9 and str(pts[-1]["method"]).startswith("pdf") else ""}{" " + c.chip("group figure", "navy") if pts[-1].get("basis") == "group" else ""}</td></tr>' for m, pts in series.items() if pts)
    events_rows = "".join(f'<div class="event"><span class="mono muted">{c.esc(str(e.get("date"))[:10])}</span><div><div class="b">{c.esc(e.get("title"))}</div><div class="muted small">{c.esc(e.get("source"))}</div></div>{c.chip(c.esc(e.get("severity") or "info"))}</div>' for e in b["events"]) or '<div class="empty">No events collected yet. Rating actions and disclosures will appear here once the events pipeline runs.</div>'
    content = f'''<div class="page-head"><div class="ident"><span class="avatar">{c.esc(b["short"][:2].upper())}</span><div><h1>{c.esc(b["name"])}</h1>
<div class="lede">{TYPE_LABEL.get(b["type"], b["type"])} · {COUNTRY.get(b["country"], b["country"])}{" · " + c.chip("LEI " + c.esc(b["lei"])) if b["lei"] else ""}{" · " + c.chip("Figures for lead bank subsidiary", "warn") if b.get("basis") == "lead_bank" else ""}</div></div></div>
<div class="actions"><button class="btn watch-btn" data-id="{b["id"]}">{c.ico("star", 16, c.ORANGE)}<span>Watch</span></button><button class="btn primary" onclick="window.print()">{c.ico("download", 16, c.WHITE)}Counterparty report</button></div></div>
<div class="grid-12"><div class="score-card"><div class="score-head"><span class="tile-label light">Counterparty score</span>{c.chip("Band " + (b["band"] or "?"), "orange") if b["band"] and b["band"] != "?" else c.chip("Insufficient data", "warn")}</div>
<div class="score-row">{score_html}<div class="score-meta"><div>{pct}</div><div>coverage <span class="mono">{cov*100:.0f}%</span> of the method</div></div></div>
{c.ribbon(score, peer.get("p25"), peer.get("p50"), peer.get("p75"), 330, 12)}
<div class="pillars">{prow}</div>
<div class="score-note">Rating anchor and public pillars with published weights (w).{' <span class="b" style="color:#ffd9b3">Unrated: capped at ' + f"{UNRATED_CAP:.0f}" + '.</span>' if b.get("unrated") else (' <span class="b" style="color:#ffd9b3">Capped by rating at ' + f"{score_cap(b.get('rating_grade')):.0f}" + '.</span>' if score_cap(b.get("rating_grade")) < 100 else '')} Market overlay <span class="mono" style="color:#fff;font-weight:600">{("+" if overlay > 0 else "") + f"{overlay:.1f}" if overlay is not None else "—"}</span>, bounded at ±{OVERLAY_CAP:.0f}. <a href="../method/index.html">Method</a></div></div>
<div class="tiles">{tiles}</div></div>
<div class="card tabs-card"><div class="tabs" role="tablist"><button class="tab active" data-tab="trends">Trends</button><button class="tab" data-tab="ratings">Ratings</button><button class="tab" data-tab="market">Market</button><button class="tab" data-tab="events">Events</button><button class="tab" data-tab="sources">Sources</button>{'<button class="tab" data-tab="data">Data</button>' if b.get("debug") else ''}</div>
<section class="panel active" data-panel="trends">{f'<div class="sm-intro small muted">{n_charts} series held, up to 48 periods each. Click a card to open it full size with every point and its date.</div>' if n_charts else ''}{"".join(charts) or '<div class="empty">Trends appear once two or more periods have been collected.</div>'}</section>
<section class="panel" data-panel="ratings">{ratings_html}</section>
<section class="panel" data-panel="market">{market_html}</section>
<section class="panel" data-panel="events">{events_rows}</section>
{debug_panel(b) if b.get("debug") else ''}
<section class="panel" data-panel="sources"><h3>Documents and feeds</h3>{src_rows or '<div class="empty">Nothing collected yet.</div>'}<h3>Latest value of every metric held</h3><div class="table-wrap"><table class="plain"><thead><tr><th>Metric</th><th>Value</th><th>Reference date</th><th>Source</th><th>Confidence</th></tr></thead><tbody>{metric_rows}</tbody></table></div></section></div>'''
    return c.shell(b["name"], content, "banks", "../", generated)


def page_events(board, generated):
    items = []
    recent = (datetime.utcnow() - timedelta(days=45)).date().isoformat()
    for r in board["rows"]:
        for e in (load(f"banks/{r['id']}").get("events") or []):
            d = str(e.get("date"))[:10]
            # routine affirmations stay on the profile page; the universe feed shows them only when fresh
            if e.get("type") == "rating" and "affirm" in str(e.get("title", "")).lower() and d < recent:
                continue
            items.append((d, r, e))
    items.sort(key=lambda x: x[0], reverse=True)
    tone = {"bad": "bad", "warn": "warn", "good": "good", "info": "muted"}
    def row(d, r, e):
        url = e.get("url") or ""
        title = f'<a href="{c.esc(url)}" target="_blank" rel="noopener">{c.esc(e.get("title"))}</a>' if url and str(url).startswith("http") else c.esc(e.get("title"))
        return (f'<div class="event" data-type="{c.esc(e.get("type") or "")}"><span class="mono muted">{d}</span><div><a class="b" href="../banks/{r["id"]}.html">{c.esc(r["name"])}</a>'
                f'<div>{title}</div><div class="muted small">{c.esc(e.get("source"))}</div></div>{c.chip(c.esc(e.get("type") or ""), "navy")} {c.chip(c.esc(e.get("severity") or "info"), tone.get(e.get("severity"), "muted"))}</div>')
    # a bank's documents collected on one day collapse into a single line
    merged, seen_batch = [], {}
    for d, r, e in items:
        if e.get("type") == "disclosure":
            key = (d, r["id"])
            if key in seen_batch:
                seen_batch[key]["n"] += 1
                m = re.search(r"period (\d{4})", str(e.get("title", "")))
                if m:
                    seen_batch[key]["years"].add(m.group(1))
                continue
            m = re.search(r"period (\d{4})", str(e.get("title", "")))
            seen_batch[key] = {"n": 1, "years": {m.group(1)} if m else set()}
            merged.append((d, r, dict(e, _batch=seen_batch[key])))
        else:
            merged.append((d, r, e))
    def row2(d, r, e):
        bt = e.get("_batch")
        if bt and bt["n"] > 1:
            yrs = sorted(bt["years"])
            span = f' ({yrs[0]}–{yrs[-1]})' if len(yrs) > 1 else (f' ({yrs[0]})' if yrs else "")
            e = dict(e, title=f'{bt["n"]} Pillar 3 documents collected{span}')
        return row(d, r, e)
    rows, last_day = "", None
    for d, r, e in merged[:300]:
        if d != last_day:
            rows += f'<div class="ev-day"><span>{d}</span></div>'
            last_day = d
        rows += row2(d, r, e)
    flagged = [(d, r, e) for d, r, e in items if e.get("severity") in ("bad", "warn", "good") or (e.get("type") == "rating" and "affirm" not in str(e.get("title", "")).lower())][:100]
    (OUT / "events").mkdir(exist_ok=True)
    _write(OUT / "events" / "feed.xml", events_feed(flagged, generated))
    counts = {}
    for _, _, e in items:
        counts[e.get("type")] = counts.get(e.get("type"), 0) + 1
    filters = f'<button class="filter active" data-type="all">All · {len(items)}</button>' + "".join(f'<button class="filter" data-type="{c.esc(t)}">{c.esc(t.title())} · {n}</button>' for t, n in sorted(counts.items()))
    shown_note = f'<span class="small muted">Latest {min(300, len(merged))} shown; a bank\'s documents from one day are folded into a line. Each profile carries its full history.</span>'
    content = (f'<div class="page-head"><div><h1>Events</h1><div class="lede">Rating actions from the ESMA register, Pillar 3 documents as they are collected, and headlines that pass a credit-vocabulary filter. Severity is rules-based; read the source before acting.</div></div></div>'
               f'<div class="toolbar ev-toolbar"><div class="filters" id="event-filters">{filters}<a class="filter" href="feed.xml" title="RSS feed of flagged events">RSS feed</a></div><div class="search">{c.ico("search", 16, c.MUTED)}<input id="evq" placeholder="Bank or headline" autocomplete="off"></div>{shown_note}</div><div class="card pad" id="events">{rows or "<div class=empty>Nothing collected yet.</div>"}</div>'
               f'<p class="note">Headlines are refreshed every two hours on weekdays between 07:00 and 19:00 UK; rating actions from the register and new documents arrive with the morning run. The RSS feed carries the last 100 flagged events for a reader or an alerting tool.</p>')
    return c.shell("Events", content, "events", "../", generated)


def events_feed(flagged, generated) -> str:
    from email.utils import format_datetime
    from datetime import timezone
    def rfc(d):
        try:
            return format_datetime(datetime.fromisoformat(d).replace(tzinfo=timezone.utc))
        except Exception:
            return ""
    items = "".join(
        f'<item><title>{c.esc(r["short"])}: {c.esc(e.get("title"))}</title><link>{c.esc(e.get("url") or "")}</link>'
        f'<guid isPermaLink="false">{c.esc(e.get("event_id") or "")}</guid><pubDate>{rfc(d)}</pubDate>'
        f'<category>{c.esc(e.get("type") or "")}</category><category>{c.esc(e.get("severity") or "")}</category>'
        f'<description>{c.esc(r["name"])} · {c.esc(e.get("source") or "")} · {c.esc(e.get("severity") or "")}</description></item>'
        for d, r, e in flagged)
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Counterparty · flagged events</title>'
            f'<link>https://philsmith871010-stack.github.io/bankCredit/events/index.html</link>'
            f'<description>Rating actions and credit-relevant headlines for the covered banks, rules-based severity. Information, not advice.</description>'
            f'<lastBuildDate>{rfc(generated[:19])}</lastBuildDate>{items}</channel></rss>')


def page_brief(board, status, generated):
    """Rules-based daily brief: what moved in the last seven days, drawn from the same tables as the site."""
    today = datetime.utcnow().date()
    since7 = (today - timedelta(days=7)).isoformat()
    since30 = (today - timedelta(days=30)).isoformat()
    rows = board["rows"]
    by_id = {r["id"]: r for r in rows}
    ratings, news, docs = [], [], []
    for r in rows:
        for e in (load(f"banks/{r['id']}").get("events") or []):
            d = str(e.get("date"))[:10]
            if d < since7:
                continue
            if e.get("type") == "rating" and "affirm" not in str(e.get("title", "")).lower():
                ratings.append((d, r, e))
            elif e.get("type") == "news" and e.get("severity") in ("bad", "warn", "good"):
                news.append((d, r, e))
            elif e.get("type") == "disclosure":
                docs.append((d, r, e))
    ratings.sort(key=lambda x: x[0], reverse=True); news.sort(key=lambda x: (x[2].get("severity") != "bad", x[0]), reverse=False)
    bm = board.get("benchmarks") or []
    widen = [b for b in bm if (b.get("change30") or 0) >= 5]
    tighten = [b for b in bm if (b.get("change30") or 0) <= -5]
    band_d = [r for r in rows if r.get("band") == "D"]
    weak_mkt = [r for r in rows if (r.get("market_public") or r.get("market") or {}).get("direction") == "down"]
    unverified = [d for d in (status.get("documents") or []) if d["status"] == "unverified" and d["fetched_at"][:10] >= since7]
    queue = status.get("review") or []

    tone = {"bad": "bad", "warn": "warn", "good": "good"}
    def ev_line(d, r, e):
        url = e.get("url") or ""
        t = f'<a href="{c.esc(url)}" target="_blank" rel="noopener">{c.esc(e.get("title"))}</a>' if str(url).startswith("http") else c.esc(e.get("title"))
        sev = e.get("severity")
        return (f'<div class="event"><span class="mono muted">{d}</span><div><a class="b" href="../banks/{r["id"]}.html">{c.esc(r["short"])}</a>'
                f'<div>{t}</div><div class="muted small">{c.esc(e.get("source"))}</div></div>{c.chip(c.esc(sev), tone[sev]) if sev in tone else ""}</div>')

    def bank_links(xs):
        return ", ".join(f'<a href="../banks/{r["id"]}.html">{c.esc(r["short"])}</a>' for r in xs) or "none"

    market_line = ('<div class="rtiles brief-bm">' + "".join(f'<div class="rtile"><div class="rtile-n mono">{b["value"]:.0f}<small>bp</small></div><div class="rtile-l">{c.esc(b["label"])}</div><div class="small {"bad" if b["change30"] > 4 else "good" if b["change30"] < -4 else "muted"}">{"+" if b["change30"] > 0 else ""}{b["change30"]:.0f} bp, 30 days</div></div>' for b in bm if b.get("change30") is not None) + "</div>") if bm else "<p>Credit benchmark series not yet collected.</p>"
    lead = []
    if widen:
        lead.append(f'Spreads are wider on the month in {", ".join(c.esc(b["label"]) for b in widen)}.')
    if tighten:
        lead.append(f'Tighter on the month: {", ".join(c.esc(b["label"]) for b in tighten)}.')
    if not widen and not tighten and bm:
        lead.append("Benchmark spreads are little changed on the month.")
    lead.append(f'{len(ratings)} rating action{"s" if len(ratings) != 1 else ""} and {len(news)} flagged headline{"s" if len(news) != 1 else ""} in the last seven days across {len(rows)} entities.')
    content = f'''<div class="page-head"><div><h1>Brief</h1><div class="lede">Machine-drafted from the day's tables by fixed rules, not by a language model. {c.esc(today.isoformat())}. Read the linked sources before acting.</div></div></div>
<div class="card pad"><p class="lead">{" ".join(lead)}</p>{market_line}</div>
<div class="grid-2 brief-grid"><div class="card pad"><h3>Rating actions <span class="muted small">· seven days</span></h3>{"".join(ev_line(*x) for x in ratings[:30]) or "<div class=empty>No rating changes, watch placements or outlook changes recorded.</div>"}</div>
<div class="card pad"><h3>Flagged headlines <span class="muted small">· passed the credit filter</span></h3>{"".join(ev_line(*x) for x in news[:30]) or "<div class=empty>Nothing flagged.</div>"}</div></div>
<div class="grid-2 brief-grid"><div class="card pad"><h3>Watch points</h3><div class="kv"><div><span>Band D, weakest public score</span><span>{bank_links(band_d)}</span></div><div><span>Market signal widening or equity weak</span><span>{bank_links(weak_mkt)}</span></div><div><span>Regulatory figures older than 150 days</span><span>{bank_links([r for r in rows if r["age_days"] and r["age_days"] > 150][:25])}</span></div></div></div>
<div class="card pad"><h3>New Pillar 3 documents</h3><p>{len(docs)} collected in the last seven days. {len(unverified)} loaded with warnings and shown as unverified; {len(queue)} waiting in the review queue.</p><a class="filter" href="../status/index.html">Status</a></div></div>'''
    return c.shell("Brief", content, "brief", "../", generated)


def page_method(generated):
    pillar_rows = "".join(f'<tr><td class="b">{k.replace("_", " ").title()}</td><td class="mono">{w}</td><td>{", ".join(METRICS.get(m, m) for m in ms)}</td></tr>' for k, (w, ms) in PILLARS.items())
    thr = "".join(f'<tr><td>{METRICS.get(m, m)}</td><td class="mono small">{" · ".join(f"{v}→{s}" for v, s in pts)}</td></tr>' for _, (w, ms) in PILLARS.items() for m, pts in ms.items())
    bands = " · ".join(f'<span class="b">{b}</span> {f} and above' for f, b in BANDS)
    grade_cells = "".join(f'<td class="mono small">{c.esc(l)}<br>{RATING_SCORE[i + 1]}</td>' for i, l in enumerate(GRADE_LETTERS))
    ratio_weight = sum(w for w, _ in PILLARS.values())
    content = f'''<div class="page-head"><div><h1>Method</h1><div class="lede">Version {VERSION}, published in full. Information, not advice.</div></div></div>
<div class="card pad prose">
<h2>Sources</h2><p>Regulatory figures come from the FDIC API (US banks, lead bank subsidiary), the EBA Pillar 3 Data Hub and Transparency Exercises (EU and EEA banks, consolidated), and each firm's own Pillar 3 disclosures (UK and other regions, read from PDF by a rules-based KM1 extractor with arithmetic validation; no AI service). Ratings and rating actions come from the ESMA European Rating Platform. Prices come from public market data. Bond quotes come from Börse Frankfurt's public price pages for each bank's senior fixed-rate bonds (two to eight years to run); they stay private and only the 30-day yield change against other bank bonds in the same currency is shown. CDS levels are medians of the day's reported trades in DTCC's public swap-data files (indicative, inferred from upfront payments) and iTraxx and CDX index prints from the same source; benchmark bond spreads are ICE BofA option-adjusted spread indices from FRED. Headlines are discovered through Google News and kept only when they pass a credit vocabulary and noise filter. Every figure on a profile carries its source, method and reference date.</p>
<h2>Score</h2><p>Two parts. The <span class="b">rating anchor</span> is {RATING_WEIGHT} percent of the score: the composite agency rating (the median of the long-term ratings held by the agencies that rate the bank, on a common scale from AAA to CCC) converted to a sub-score by the table below. The <span class="b">ratio pillars</span> are the other {ratio_weight} percent: each regulatory metric is converted to a 0 to 100 sub-score by straight-line interpolation between the thresholds below, averaged within its pillar and weighted. Missing metrics do not score zero: the ratio weights are re-scaled over what is available and the coverage percentage is shown. A band is only assigned when coverage is at least 50 percent.</p>
<p>A bank no agency rates takes a rating sub-score of {UNRATED_SCORE:.0f}, below neutral, and its score is capped at {UNRATED_CAP:.0f} so it cannot reach band A however strong its ratios: the absence of any independent assessment is itself information, and a young or small bank's ratios are often high because its balance sheet is small or immature rather than because it is safer. Such banks are marked "unrated" wherever the score appears. The same cap applies to a bank rated in the BBB range, and a bank rated below investment grade is capped at 64.9 (band C): strong ratios can lift a bank at most one band above what its rating says.</p>
<div class="wbar" aria-hidden="true"><span style="flex:{RATING_WEIGHT}" class="w-rating">Rating {RATING_WEIGHT}</span>{"".join(f'<span style="flex:{w}" class="w-{k}" title="{k.replace("_", " ").title()} {w}">{ {"capital": "Capital", "liquidity": "Liquidity", "stability": "Stability", "asset_quality": "Assets", "profitability": "Profit"}[k]} {w}</span>' for k, (w, _) in PILLARS.items())}</div>
<div class="bandscale" aria-hidden="true">{"".join(f'<span class="band-{b}" style="flex:{(100 if b == "A" else 80 if b == "B" else 65 if b == "C" else 50 if b == "D" else 35) - f}">{b} · {f}+</span>' for f, b in BANDS)}</div>
<table class="plain"><thead><tr><th>Component</th><th>Weight</th><th>Inputs</th></tr></thead><tbody><tr><td class="b">Rating anchor</td><td class="mono">{RATING_WEIGHT}</td><td>Composite long-term agency rating; {UNRATED_SCORE:.0f} and a cap of {UNRATED_CAP:.0f} when unrated; caps of {UNRATED_CAP:.0f} for the BBB range and 64.9 below investment grade</td></tr>{pillar_rows}</tbody></table>
<h3>Rating sub-scores</h3><div class="table-wrap"><table class="plain"><tbody><tr>{grade_cells}</tr></tbody></table></div>
<h3>Thresholds (value → sub-score)</h3><table class="plain"><tbody>{thr}</tbody></table>
<h3>Bands</h3><p>{bands}. Bands carry hysteresis in later versions so they do not flicker at boundaries.</p>
<h3>What changed from version 1</h3><p>Version 1 scored ratios alone against absolute thresholds and kept ratings in the private overlay. That put small, young or narrowly focused banks with very high capital and liquidity ratios at the top of the table, some of them unrated, and large diversified banks with A+ ratings and leaner ratios in band C. Version 2 (7 September 2026) makes the rating the anchor, moves ratings out of the overlay so they are not counted twice, and caps unrated banks. Scoring ratios relative to each peer group rather than to absolute thresholds is the next candidate change.</p>
<h2>My policy</h2><p>A page for the treasurer's own approved list. You enter the counterparties you accept and the longest tenor for each; the page keeps the list in your browser (and in a link you can share with colleagues) and checks it on every visit against the current score, band, ratings, market signal, news and data age, flagging what has changed since the day each name was approved. Like-for-like shows the other covered names whose public standing is at least as strong as the weakest counterparty you already accept at each tenor. It compares public information; it does not suggest a tenor, a limit or a list, which remain the treasurer's policy and the adviser's advice.</p>
<h2>Ratings</h2><p>The Ratings page shows each entity's latest long-term rating by agency (issuer or issuer default rating where it exists, otherwise deposit or counterparty), its outlook, the short-term rating, and the composite. Ratings come from the ESMA European Rating Platform and are shown with agency attribution, refreshed daily; rating histories are not redistributed.</p>
<h2>Market overlay</h2><p>A layer built from five-year CDS levels and 30-day changes where a CDS market exists (otherwise the 30-day change in the bank's own bond yields against peers), 30-day equity volatility and drawdown from the 52-week high. It adjusts the public score by at most ±{OVERLAY_CAP:.0f} points. Provisional weighting (September 2026): the three signals count equally, each worth at most 2.5 points either way. A CDS move is measured within one source (settlement against settlement, or trade medians on days with three or more trades) and split into the part shared with iTraxx Senior Financials and the part that is the bank's own; the label says which. The direction and size of the adjustment are shown; CDS levels themselves are not redistributed.</p>
<h2>Limitations</h2><ul><li>US banking groups appear twice, as in the UK: the operating bank a depositor faces (Call Report figures from the FDIC, with the US Tier 1 leverage ratio scored on its own scale, and the group's LCR shown as a group figure because banks do not publish their own) and the holding company (binding Basel ratios, the lower of the standardised and advanced approaches, from its Pillar 3 report or XBRL filings, the supplementary leverage ratio, the public LCR disclosure, and asset quality and profitability inherited from its lead bank, labelled).</li><li>UK and other-region figures depend on PDF extraction; failed validations are shown as unverified rather than hidden.</li><li>Peer percentiles are computed only among entities with a score, so they are unstable while coverage is low.</li><li>Asset quality and profitability are held only for US banks so far, so those pillars are re-scaled away for most of the universe; the Coverage page shows this per bank.</li><li>Back-tests against past failures are planned.</li></ul>
</div>'''
    return c.shell("Method", content, "method", "../", generated)

def page_status(status, board, generated):
    runs = "".join(f'<tr><td class="b">{c.esc(r["source"])}</td><td>{c.chip(c.esc(r["status"]), {"ok": "good", "partial": "warn", "failed": "bad"}.get(r["status"], "muted"))}</td><td class="mono">{r["rows"]}</td><td class="mono muted">{c.esc(r["finished"][:16].replace("T", " "))}</td><td class="muted small">{c.esc(r["message"])}</td></tr>' for r in status["runs"]) or '<tr><td colspan="5" class="empty">No runs recorded yet.</td></tr>'
    rows = board["rows"]
    missing = [r for r in rows if not r["asof"]]
    stale = [r for r in rows if r["age_days"] and r["age_days"] > 150]
    lst = lambda xs: ", ".join(f'<a href="../banks/{r["id"]}.html">{c.esc(r["short"])}</a>' for r in xs) or "none"
    content = f'''<div class="page-head"><div><h1>Status</h1><div class="lede">What ran, when, and what needs a look. Auto-publish with spot checks.</div></div></div>
<div class="card pad"><h3>Pipeline runs</h3><div class="table-wrap"><table class="plain"><thead><tr><th>Source</th><th>Status</th><th>Rows</th><th>Finished (UTC)</th><th>Message</th></tr></thead><tbody>{runs}</tbody></table></div></div>
<div class="card pad"><h3>Coverage</h3><p>{len(rows) - len(missing)} of {len(rows)} entities have regulatory figures; {sum(1 for r in rows if r["score"] is not None)} have enough for a score; {sum(1 for r in rows if r["ratings"])} have ratings.</p>
<p class="small"><span class="b">No regulatory figures yet:</span> {lst(missing)}</p><p class="small"><span class="b">Older than 150 days:</span> {lst(stale)}</p></div>
{documents_card(status)}
{learning_card(status)}
{audit_card()}'''
    return c.shell("Status", content, "status", "../", generated)


def documents_card(status):
    docs = status.get("documents") or []
    queue = status.get("review") or []
    if not docs and not queue:
        return ""
    counts = status.get("document_counts") or {}
    tone = {"loaded": "good", "unverified": "warn", "review": "warn", "no_km1": "bad", "error": "bad"}
    summary = " ".join(f'{c.chip(c.esc(k), tone.get(k, "muted"))} <span class="mono">{v}</span>' for k, v in counts.items())
    rows = "".join(f'<tr><td class="b"><a href="../banks/{c.esc(d["entity_id"])}.html">{c.esc(d.get("short") or d["entity_id"])}</a></td><td>{c.chip(c.esc(d["status"]), tone.get(d["status"], "muted"))}</td><td class="mono">{c.esc(d.get("reference_date") or "—")}</td><td class="mono muted">{d["confidence"]:.2f}</td><td class="small"><a href="{c.esc(d["url"])}" target="_blank" rel="noopener">{c.esc((d.get("title") or d["url"])[:70])}</a></td><td class="mono muted">{c.esc(d["fetched_at"][:10])}</td></tr>' for d in docs)
    q = "".join(f'<li><span class="b">{c.esc(i["entity_id"])}</span> · {c.esc(i.get("reference_date") or "date unknown")} · p.{i.get("page") or "?"} · <span class="muted">{c.esc(i["reason"][:120])}</span></li>' for i in queue) or "<li class='muted'>Queue is empty.</li>"
    return f'''<div class="card pad"><h3>Pillar 3 documents</h3><p class="small">{summary}</p>
<p class="small">Figures marked <em>unverified</em> passed the template checks with warnings. Items in the review queue are resolved on the maintainer's machine by the local review skill (no AI service is called from the pipeline).</p>
<h4>Review queue ({len(queue)})</h4><ul class="small">{q}</ul>
<h4>Latest collected</h4><div class="table-wrap"><table class="plain"><thead><tr><th>Entity</th><th>Outcome</th><th>Reference</th><th>Confidence</th><th>Document</th><th>Fetched</th></tr></thead><tbody>{rows}</tbody></table></div></div>'''


GRADE_COLOURS = [(4, "#0a2540"), (7, "#3f5f85"), (10, "#7d93ad"), (13, "#c77d1a"), (99, "#b04632")]     # upper grade -> colour


def grade_colour(grade):
    if grade is None:
        return "#dfe5eb"
    for upper, col in GRADE_COLOURS:
        if grade <= upper:
            return col
    return "#b04632"


def outlook_glyph(o: str) -> str:
    o = (o or "").lower()
    if "pos" in o:
        return '<span title="positive outlook" style="color:#1e7a3a">▲</span>'
    if "neg" in o:
        return '<span title="negative outlook" style="color:#b04632">▼</span>'
    if "watch" in o or "review" in o or "developing" in o:
        return '<span title="on watch" style="color:#c77d1a">◆</span>'
    if "stab" in o:
        return '<span title="stable outlook" class="muted">▶</span>'
    return ""


def rating_grade_site(value):
    from ..export import rating_grade
    return rating_grade(value)


def grade_trend(r) -> str:
    """Composite grade through the daily snapshots: a sparkline once there are two, the held-since date before that."""
    try:
        h = load(f"banks/{r['id']}").get("history") or {}
    except Exception:
        h = {}
    pts = [g for _d, _v, g in (h.get("snapshots") or []) if g is not None]
    if len(pts) >= 2 and len({d for d, _v, g in h["snapshots"] if g is not None}) >= 2:
        return c.spark([-g for g in pts], w=72, h=20) + f'<span class="small muted"> {len(pts)}d</span>'
    since = min((a.get("date") or "9999" for a in (r.get("agencies") or {}).values() if a.get("date")), default=None)
    return f'<span class="small muted">held since {c.esc(since)}</span>' if since and since != "9999" else '<span class="muted">—</span>'


def page_ratings(generated):
    R = load("ratings")
    rows = R["rows"]
    rated = [r for r in rows if r["grade"] is not None]
    today = datetime.utcnow().date()
    since90 = (today - timedelta(days=90)).isoformat()
    since30 = (today - timedelta(days=30)).isoformat()
    acts_all = R["actions"]
    recent30 = [a for a in acts_all if a["date"] >= since30]
    ups = sum(1 for a in recent30 if a["severity"] == "good")
    downs = sum(1 for a in recent30 if a["severity"] in ("warn", "bad"))
    moved = {a["id"] for a in acts_all if a["date"] >= since90}
    # distribution by composite grade: the filter control for the grid
    GR = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC"]
    counts = {i: 0 for i in range(1, 18)}
    for r in rated:
        counts[max(1, min(17, int(r["grade"] + 0.5)))] += 1
    mx = max(counts.values()) or 1
    hist = "".join(f'<button class="gbar gfilter" data-grade="{i}" title="{GR[i-1]}: {counts[i]}" {"disabled" if not counts[i] else ""}><span class="gcount mono">{counts[i] or ""}</span><i style="height:{max(3, counts[i] / mx * 64):.0f}px;background:{grade_colour(i)}"></i><span class="glabel">{GR[i-1]}</span></button>' for i in range(1, 14))
    hist += f'<button class="gbar gfilter" data-grade="nr" title="Unrated: {len(rows) - len(rated)}"><span class="gcount mono">{len(rows) - len(rated)}</span><i style="height:{max(3, (len(rows) - len(rated)) / mx * 64):.0f}px;background:#dfe5eb"></i><span class="glabel">NR</span></button>'
    band_tiles = [("AA- and above", sum(1 for r in rated if r["grade"] <= 4), "#0a2540"), ("A range", sum(1 for r in rated if 4 < r["grade"] <= 7), "#3f5f85"),
                  ("BBB range", sum(1 for r in rated if 7 < r["grade"] <= 10), "#7d93ad"), ("Below BBB-", sum(1 for r in rated if r["grade"] > 10), "#b04632"),
                  ("Unrated", len(rows) - len(rated), "#6c757d")]
    tiles = "".join(f'<button class="rtile bfilter" data-band="{k}"><div class="rtile-n mono" style="color:{col}">{n}</div><div class="rtile-l">{c.esc(k)}</div></button>' for k, n, col in band_tiles)
    tiles += f'<a class="rtile" href="#actions"><div class="rtile-n mono"><span style="color:#1e7a3a">{ups}▲</span> <span style="color:#b04632">{downs}▼</span></div><div class="rtile-l">Actions, 30 days</div></a>'
    # the grid: one row per entity, one tinted cell per agency
    AG = [("fitch", "Fitch"), ("sp", "S&amp;P"), ("moodys", "Moody's"), ("dbrs", "DBRS"), ("kbra", "KBRA"), ("scope", "Scope")]
    used = [(k, n) for k, n in AG if any(r["agencies"].get(k, {}).get("lt") for r in rows)]
    def cell(a):
        if not a or not a.get("lt"):
            return '<td class="rc rc-na">—</td>'
        g = rating_grade_site(a["lt"])
        col = grade_colour(g)
        light = g is None or g > 10 or g <= 4 or (7 < g <= 10 and False)
        typ = "" if a.get("lt_type") in ("idr", "issuer") else f' <span class="rc-typ" title="rating type">{c.esc(str(a.get("lt_type") or "")[:3])}</span>'
        return (f'<td class="rc" style="--g:{col}"><span class="rc-lt mono">{c.esc(a["lt"])}</span>{outlook_glyph(a.get("outlook"))}{typ}'
                f'<span class="rc-sub small">{c.esc(a.get("st") or "")}<span class="muted"> {c.esc((a.get("date") or "")[:7])}</span></span></td>')
    def band_key(g):
        return "Unrated" if g is None else "AA- and above" if g <= 4 else "A range" if g <= 7 else "BBB range" if g <= 10 else "Below BBB-"
    trs = "".join(
        f'<tr data-id="{c.esc(r["id"])}" data-region="{c.esc(r["region"])}" data-name="{c.esc(r["short"].lower())} {c.esc(r["name"].lower())}" data-score="{100 - (r["grade"] or 99)}" '
        f'data-grade="{max(1, min(17, int(r["grade"] + 0.5))) if r["grade"] is not None else "nr"}" data-band="{band_key(r["grade"])}" data-moved="{1 if r["id"] in moved else 0}">'
        f'<td><a class="b" href="../banks/{c.esc(r["id"])}.html">{c.esc(r["short"])}</a><div class="small muted">{c.esc(COUNTRY.get(r["country"], r["country"]))} · {c.esc(TYPE_LABEL.get(r["type"], r["type"]))}</div></td>'
        f'<td class="rc rc-comp" style="--g:{grade_colour(r["grade"])}"><span class="band mono" style="background:{grade_colour(r["grade"])};color:{"#fff" if r["grade"] is not None and r["grade"] <= 10 else "#243240"}">{c.esc(r["composite"] or "NR")}</span><span class="rc-sub small muted">{len([1 for k, _ in used if r["agencies"].get(k, {}).get("lt")])} agenc{"y" if len([1 for k, _ in used if r["agencies"].get(k, {}).get("lt")]) == 1 else "ies"}</span></td>'
        + "".join(cell(r["agencies"].get(k)) for k, _ in used)
        + f'<td class="small">{("<span class=chip-dot></span> " if r["id"] in moved else "")}<span class="mono muted">{c.esc(r["last_action"] or "—")}</span></td><td>{grade_trend(r)}</td></tr>'
        for r in sorted(rows, key=lambda r: (r["grade"] is None, r["grade"] or 99, r["short"])))
    regions = [("all", "All"), ("uk", "UK"), ("eu", "EU"), ("us_ch", "US and Switzerland"), ("aus_can", "Australia and Canada"), ("asia", "Asia"), ("gulf", "Gulf"), ("watch", "Watching")]
    filters = "".join(f'<button class="filter{" active" if k == "all" else ""}" data-region="{k}">{c.esc(l)}</button>' for k, l in regions)
    tone = {"bad": "bad", "warn": "warn", "good": "good", "info": "muted"}
    acts = "".join(f'<div class="ract"><span class="mono muted">{a["date"]}</span><a class="b" href="../banks/{c.esc(a["id"])}.html">{c.esc(a["short"])}</a><span>{c.esc(a["title"])}</span>{c.chip(c.esc({"good": "positive", "warn": "watch", "bad": "adverse"}.get(a["severity"], a["severity"])), tone.get(a["severity"], "muted"))}</div>' for a in acts_all[:30]) or '<div class="empty">No rating actions other than affirmations in the last 90 days.</div>'
    AGN = [("fitch", "Fitch"), ("sp", "S&amp;P"), ("moodys", "Moody's"), ("dbrs", "DBRS")]
    dist = ""
    for ag, label in AGN:
        gs = [rating_grade_site(r["agencies"].get(ag, {}).get("lt")) for r in rows]
        gs = [g for g in gs if g is not None]
        if not gs:
            continue
        cnts = [sum(1 for g in gs if g <= 4), sum(1 for g in gs if 4 < g <= 7), sum(1 for g in gs if 7 < g <= 10), sum(1 for g in gs if g > 10)]
        segs = "".join(f'<div class="dseg" style="flex:{n};background:{col}" title="{lab}: {n}"></div>' for n, col, lab in zip(cnts, ["#0a2540", "#3f5f85", "#7d93ad", "#b04632"], ["AA- and above", "A range", "BBB range", "below BBB-"]) if n)
        dist += f'<div class="drow"><div class="dlabel">{label} <span class="muted small">{sum(cnts)} rated</span></div><div class="dbar">{segs}</div></div>'
    content = f'''<div class="page-head"><div><h1>Ratings</h1><div class="lede">Who rates whom, and how. One row per entity, one tinted cell per agency: the long-term rating with its outlook, the short-term rating and month beneath. Click a band, a grade bar or a region to filter; the ESMA European Rating Platform is the source, refreshed daily.</div></div></div>
<div class="rtiles rtiles-f">{tiles}</div>
<div class="card rgrid-card"><div class="toolbar rg-tools"><div class="filters">{filters}<button class="filter" data-region="moved">Moved in 90 days</button></div><input id="q" class="search" placeholder="Search"><span class="small muted" id="rg-count"></span></div>
<div class="rg-hist"><span class="small muted">Composite grade</span>{hist}<button class="filter small gclear" hidden>Clear grade</button></div>
<div class="table-wrap"><table id="board" class="plain rgrid"><thead><tr><th data-sort="name">Entity</th><th data-sort="score" title="Median of the agencies' long-term ratings on a common scale">Composite</th>{"".join(f"<th>{n}</th>" for _, n in used)}<th>Last action</th><th title="composite grade on each build since snapshots began">Since</th></tr></thead><tbody>{trs}</tbody></table></div>
<div class="table-foot"><span>▲ positive outlook · ▼ negative · ◆ on watch · ▶ stable · cell tint follows the grade · a dot marks an action in 90 days · symbols are the agencies' and are shown with attribution; histories are not redistributed</span></div></div>
<div class="grid-2 rgrid2"><div class="card pad" id="actions"><h3>Latest rating actions <span class="muted small">· 90 days, affirmations excluded</span></h3><div class="racts">{acts}</div></div>
<div class="card pad"><h3>How each agency sees the universe</h3><div class="dist">{dist}</div><div class="dlegend"><span><i style="background:#0a2540"></i>AA- and above</span><span><i style="background:#3f5f85"></i>A range</span><span><i style="background:#7d93ad"></i>BBB range</span><span><i style="background:#b04632"></i>below BBB-</span></div>
<p class="note">Long-term issuer ratings only, one per agency per entity. Differences between the bars are mostly which banks each agency rates, not disagreement about the same bank.</p></div></div>'''
    return c.shell("Ratings", content, "ratings", "../", generated)

def page_policy(generated):
    content = '''<div class="page-head"><div><h1>My policy</h1><div class="lede">Your approved counterparties and the longest tenor you accept for each, checked against today's public standing, market signal and news. The list lives in this browser and in the share link; nothing is sent anywhere.</div></div></div>
<div class="pol-shared" id="pol-shared" hidden><span></span><button class="filter" id="pol-use-shared">Use it</button><button class="filter" id="pol-keep-mine">Keep mine</button></div>
<div class="card pad"><h3>Add a counterparty</h3>
<div class="pol-form"><label>Name<input id="pol-name" list="pol-names" placeholder="Start typing a bank or building society" autocomplete="off"><datalist id="pol-names"></datalist></label>
<label>Longest tenor you accept<select id="pol-tenor"></select></label><button class="filter active" id="pol-add">Add</button></div>
<p class="note">Use the legal entity you actually place with: Barclays Bank UK PLC rather than Barclays PLC, HSBC UK Bank plc rather than HSBC Holdings. Each name is checked from the day you add it.</p></div>
<div class="card pad" style="margin-top:16px"><h3>Your counterparties</h3><div id="policy-body"><div class="empty">Loading…</div></div>
<div class="pol-share"><button class="filter" id="pol-copy">Copy link</button><input id="pol-link" readonly placeholder="A link that carries this policy appears here"><button class="filter" id="pol-clear">Clear all</button></div>
<p class="note">Counterparty is information, not advice. The flags say what has changed in public information since you approved a name; whether that changes your policy is for you and your adviser.</p></div>'''
    return c.shell("My policy", content, "policy", "../", generated).replace('<script src="../assets/app.js"></script>', '<script src="../assets/app.js"></script><script src="../assets/policy.js"></script>').replace("<body>", '<body data-root="../">')


def audit_card():
    try:
        A = load("audit")["rows"]
    except Exception:
        return ""
    if not A:
        return ""
    regions = {}
    for a in A:
        regions.setdefault(a["region"], []).append(a)
    head = "".join(f'<tr><td class="b">{c.esc(k)}</td><td class="mono">{len(v)}</td><td class="mono">{sum(1 for a in v if a["periods"])}</td><td class="mono">{sorted(a["periods"] for a in v)[len(v)//2]}</td><td class="mono">{max(a["years"] for a in v):.1f}</td><td class="mono">{sum(1 for a in v if a["agencies"])}</td><td class="mono">{sum(1 for a in v if a["price_days"])}</td><td class="mono">{sum(1 for a in v if a["cds_days"])}</td><td class="mono">{sum(1 for a in v if a["bonds"])}</td></tr>' for k, v in sorted(regions.items()))
    rows = "".join(f'<tr><td class="b"><a href="../banks/{c.esc(a["id"])}.html">{c.esc(a["short"])}</a></td><td class="muted small">{c.esc(a["region"])}</td><td class="mono">{a["periods"] or "—"}</td><td class="mono small">{c.esc(a["first"] or "—")}</td><td class="mono small">{c.esc(a["last"] or "—")}</td><td class="mono">{a["years"] or "—"}</td><td class="small muted">{c.esc(", ".join(a["sources"]))}</td><td class="mono">{a["agencies"] or "—"}</td><td class="mono">{a["price_days"] or ("—" if not a["ticker"] else "0")}</td><td class="mono">{a["cds_days"] or "—"}</td><td class="mono">{a["bonds"] or "—"}</td></tr>' for a in sorted(A, key=lambda a: (-a["periods"], a["short"])))
    return f'''<div class="card pad"><h3>Data audit</h3><p class="small">What is held for every entity: regulatory history measured on the CET1 ratio (periods, first and last reference date, span in years, sources), rating agencies, daily prices, CDS settlement days and reference bonds. A dash means none; prices show 0 for a listed name whose feed has failed.</p>
<div class="table-wrap"><table class="plain"><thead><tr><th>Region</th><th>Entities</th><th>With figures</th><th>Median periods</th><th>Longest span</th><th>Rated</th><th>Priced</th><th>CDS</th><th>Bonds</th></tr></thead><tbody>{head}</tbody></table></div>
<h4 style="margin-top:14px">By entity</h4><div class="table-wrap"><table class="plain"><thead><tr><th>Entity</th><th>Region</th><th>Periods</th><th>First</th><th>Last</th><th>Years</th><th>Sources</th><th>Agencies</th><th>Price days</th><th>CDS days</th><th>Bonds</th></tr></thead><tbody>{rows}</tbody></table></div></div>'''


def learning_card(status):
    L = status.get("learning") or {}
    if not L.get("answers") and not L.get("entities_with_hints"):
        return ""
    agree = f'{L["agreement"] * 100:.0f}%' if L.get("agreement") is not None else "—"
    def _examples(d):
        return "; ".join(f"{x['entity']}: rules {x['extractor']} vs reviewer {x['reviewer']}" for x in d["examples"])
    metric_rows = "".join(f'<tr><td class="b">{c.esc(m)}</td><td class="mono">{d["mismatches"]}</td><td class="small muted">{c.esc(_examples(d))}</td></tr>' for m, d in (L.get("by_metric") or {}).items())
    reason_rows = "".join(f'<li><span class="mono">{n}</span> · {c.esc(r)}</li>' for r, n in list((L.get("by_reason") or {}).items())[:8])
    return f'''<div class="card pad"><h3>What the review taught the extractor</h3>
<p class="small">Every answer from the review queue is compared with what the rules read from the same page, and becomes a hint for that bank's next document: the page, the currency, whether the table carries row numbers, filenames that never hold a KM1 table, and the last verified figures for a continuity check. No AI service is involved; the loop is the reviewer's answers and the rules.</p>
<div class="kv"><div><span>Answers recorded</span><span class="mono">{L.get("answers", 0)} ({L.get("skipped", 0)} skipped)</span></div><div><span>Rules agreed with the reviewer</span><span class="mono">{agree} of {L.get("values_compared", 0)} values</span></div><div><span>Right page, right date</span><span class="mono">{L.get("page_right", 0)} / {L.get("date_right", 0)} of {L.get("answered", 0)}</span></div><div><span>Banks with hints</span><span class="mono">{L.get("entities_with_hints", 0)} ({L.get("entities_with_baseline", 0)} with a verified baseline, {L.get("skip_patterns", 0)} skip patterns)</span></div></div>
{('<h4>Where the rules disagree</h4><div class="table-wrap"><table class="plain"><thead><tr><th>Metric</th><th>Cases</th><th>Examples</th></tr></thead><tbody>' + metric_rows + '</tbody></table></div>') if metric_rows else ''}
{('<h4>Why items were queued</h4><ul class="small">' + reason_rows + '</ul>') if reason_rows else ''}</div>'''


AUDIT_COLS = [("cet1_ratio", "CET1"), ("tier1_ratio", "Tier 1"), ("total_capital_ratio", "Total cap."), ("leverage_ratio", "Leverage"),
              ("lcr", "LCR"), ("nsfr", "NSFR"), ("overall_capital_requirement", "Requirement"), ("npl_ratio", "NPL"),
              ("roe", "ROE"), ("roa", "ROA"), ("efficiency_ratio", "Cost/income"), ("total_assets", "Assets")]


def _depth_cell(m: dict) -> str:
    n = m["n"]
    if not n:
        return '<td class="cov cov0" data-v="0">—</td>'
    span = m["first"][:4] if m["first"] == m["last"] else f'{m["first"][:4]}–{m["last"][2:4]}'
    k = 1 if n < 4 else 2 if n < 12 else 3
    return f'<td class="cov cov{k}" data-v="{n}"><b>{n}</b><span>{span}</span></td>'


def page_coverage(generated):
    A = load("audit")["rows"]
    n = len(A)

    def cnt(fn):
        return sum(1 for a in A if fn(a))
    tiles = "".join(f'<div class="rtile"><div class="rt-n">{v}</div><div class="rt-l">{c.esc(l)}</div></div>' for v, l in [
        (n, "entities"), (cnt(lambda a: a["score"] is not None), "scored"), (cnt(lambda a: a["agencies"]), "rated"),
        (cnt(lambda a: a["years"] >= 5), "5+ years of ratios"), (cnt(lambda a: a["metrics"]["lcr"]["n"]), "with LCR"),
        (cnt(lambda a: a["metrics"]["npl_ratio"]["n"]), "with asset quality"), (cnt(lambda a: a["price_days"]), "with a share price"),
        (cnt(lambda a: a["cds_days"]), "with CDS"), (cnt(lambda a: a["bonds"]), "with bonds")])
    trs = []
    for a in sorted(A, key=lambda a: (-(a["score"] or -1), a["short"])):
        band = c.chip(c.esc(a["band"] or "—"), "muted") if a["band"] else ""
        letters = "".join(AGENCY_LETTER.get(x, x[:1].upper()) for x in a["agency_list"])
        rating = f'<b>{c.esc(a["rating"])}</b> <span class="muted small">· {c.esc(letters)}</span>' if a["agencies"] else '<span class="muted">unrated</span>'
        price = f'{a["price_days"]}<span class="muted small"> {c.esc(a["symbol"])}</span>' if a["price_days"] else ('<span class="muted">0</span>' if a["ticker"] else '<span class="muted">—</span>')
        cells = "".join(_depth_cell(a["metrics"][m]) for m, _ in AUDIT_COLS)
        score = a["score"] if a["score"] is not None else -1
        sources = ", ".join(x.replace("eba_te", "EBA TE") for x in a["sources"])
        trs.append(f'<tr data-id="{c.esc(a["id"])}" data-name="{c.esc(a["short"].lower())}" data-region="{c.esc(a["region"])}" data-score="{score}">'
                   f'<td class="b"><a href="../banks/{c.esc(a["id"])}.html">{c.esc(a["short"])}</a><div class="muted small">{c.esc(a["peer_group"])}</div></td>'
                   f'<td class="mono" data-v="{score}">{a["score"] if a["score"] is not None else "—"} {band}</td>'
                   f'<td data-v="{a["agencies"]}">{rating}</td>'
                   f'<td class="mono" data-v="{a["price_days"]}">{price}</td>'
                   f'<td class="mono" data-v="{a["cds_days"]}">{a["cds_days"] or "—"}</td>'
                   f'<td class="mono" data-v="{a["bonds"]}">{a["bonds"] or "—"}</td>'
                   f'<td class="mono" data-v="{a["news90"]}">{a["news90"] or "—"}</td>'
                   f'<td class="mono" data-v="{a["years"]}">{a["years"] or "—"}</td>'
                   f'<td class="small muted">{c.esc(sources)}</td>{cells}</tr>')
    regions = [("all", "All"), ("uk", "UK"), ("eu", "EU"), ("us_ch", "US and Switzerland"), ("aus_can", "Australia and Canada"), ("asia", "Asia"), ("gulf", "Gulf"), ("watch", "Watching")]
    filters = "".join(f'<button class="filter{" active" if k == "all" else ""}" data-region="{k}">{c.esc(l)}</button>' for k, l in regions)
    heads = "".join(f'<th class="num" data-sort="col" title="periods held and the years they span">{c.esc(l)}</th>' for _, l in AUDIT_COLS)
    body = "".join(trs)
    content = (
        '<div class="page-head"><div><h1>Coverage</h1><div class="lede">What is held for every entity: the score it earns, ratings by agency, '
        'share price, CDS and bond data, news, and for each ratio the number of reporting periods and the years they span. '
        'A build-time view, so gaps are visible before they are trusted.</div></div></div>'
        f'<div class="rtiles">{tiles}</div>'
        f'<div class="card" style="margin-top:16px"><div class="toolbar"><div class="filters">{filters}</div><input id="q" class="search" placeholder="Search"></div>'
        '<div class="table-wrap"><table id="board" class="plain coverage"><thead><tr><th data-sort="name">Entity</th><th data-sort="score">Score</th>'
        '<th data-sort="col">Rating</th><th class="num" data-sort="col" title="trading days of closing prices held">Price days</th>'
        '<th class="num" data-sort="col" title="settlement days with a CDS level">CDS days</th><th class="num" data-sort="col">Bonds</th>'
        '<th class="num" data-sort="col" title="headlines kept in the last 90 days">News 90d</th>'
        f'<th class="num" data-sort="col" title="span of the CET1 history in years">Years</th><th>Sources</th>{heads}</tr></thead><tbody>{body}</tbody></table></div>'
        '<div class="table-foot"><span>Ratio cells: periods held, then the first and last year. Shading: light under 4 periods, mid under 12, dark 12 and over. '
        "Rating letters are the agencies holding a long-term issuer rating (F Fitch, S S&amp;P, M Moody's, D DBRS, K KBRA, Sc Scope, J JCR). Click a column heading to sort.</span></div></div>")
    return c.shell("Coverage", content, "coverage", "../", generated)


_WS = re.compile(r">\s+<")


def _write(path, html: str) -> None:
    """Write a page with the whitespace between tags collapsed (there is no <pre> content on the site)."""
    path.write_text(_WS.sub("><", html))


def page_compare(generated):
    sets = [("all", "Everyone"), ("uk_large", "UK majors"), ("uk_mid", "UK mid-sized"), ("uk_small", "UK small banks"), ("uk_bs", "Building societies"),
            ("eu_large", "EU and Nordic"), ("us", "US"), ("ch", "Switzerland"), ("aus", "Australia"), ("can", "Canada"), ("asia", "Asia"), ("gulf", "Gulf"),
            ("watch", "Watching"), ("policy", "My policy")]
    chips = "".join(f'<button class="filter cp-set" data-set="{k}">{c.esc(l)}<span class="cnt"></span></button>' for k, l in sets)
    def panel(pid, title, sub):
        return (f'<section class="panel-c" id="p-{pid}"><div class="pc-head"><h3>{c.esc(title)} <span class="muted small">{c.esc(sub)}</span></h3>'
                f'<button class="pc-x" data-panel="{pid}" title="Expand or restore" aria-label="Expand {c.esc(title)}">⤢</button></div><div class="pc-body cp-chart" id="c-{pid}"><div class="empty">Loading…</div></div></section>')
    content = f'''<div class="page-head"><div><h1>Analysis</h1><div class="lede">One peer set, one measure, every view at once. Pin up to six names and they carry the same colour in every panel; hover any name anywhere and it lights up everywhere.</div></div></div>
<div class="card cp-card"><div class="cp-tools">
<div class="filters" id="cp-sets">{chips}</div>
<div class="cp-row"><label class="small muted">Measure <select id="cp-metric"></select></label>
<label class="small muted">against <select id="cp-metric2"></select></label>
<div class="search cp-add">{c.ico("search", 16, c.MUTED)}<input id="cp-q" placeholder="Add a name to the set" autocomplete="off"><div class="cp-sugg" id="cp-sugg" hidden></div></div>
<span class="small muted" id="cp-count"></span></div>
<div class="cp-pins" id="cp-pins"></div></div></div>
<div class="dash" id="dash">
{panel("rank", "Ranking now", "latest figure, set median")}
{panel("trend", "Trend", "quarter ends, set median dashed")}
{panel("bump", "Rank over time", "position within the set")}
{panel("scatter", "Two measures", "bubble size follows total assets")}
</div>
<div class="card cp-card"><div class="pc-head"><h3>The set in numbers <span class="muted small">· latest reported figures; click a heading to sort, a swatch to pin</span></h3></div><div class="table-wrap" id="c-table"></div></div>
<div class="table-foot"><span>Figures are the latest reported by each name; sources and dates are on each profile. Ranks count only names with a figure at that date. The score's history is recomputed with today's method and rating on the ratios as they stood.</span></div>'''
    return c.shell("Analysis", content, "compare", "../", generated).replace("</body>", '<script src="../assets/compare.js"></script></body>')

def build():
    board = load("board"); status = load("status"); generated = board["generated"]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "banks").mkdir(parents=True); (OUT / "events").mkdir(); (OUT / "method").mkdir(); (OUT / "status").mkdir()
    shutil.copytree(ASSETS, OUT / "assets")
    _write(OUT / "index.html", page_board(board, generated))
    _write(OUT / "banks" / "index.html", page_banks_index(board, generated))
    for r in board["rows"]:
        _write(OUT / "banks" / f"{r['id']}.html", page_bank(load(f"banks/{r['id']}"), generated))
    _write(OUT / "events" / "index.html", page_events(board, generated))
    _write(OUT / "method" / "index.html", page_method(generated))
    (OUT / "ratings").mkdir(exist_ok=True)
    _write(OUT / "ratings" / "index.html", page_ratings(generated))
    (OUT / "compare").mkdir(exist_ok=True); (OUT / "data").mkdir(exist_ok=True)
    _write(OUT / "compare" / "index.html", page_compare(generated))
    shutil.copy(store.DATA / "json" / "compare.json", OUT / "data" / "compare.json")
    (OUT / "coverage").mkdir(exist_ok=True)
    _write(OUT / "coverage" / "index.html", page_coverage(generated))
    (OUT / "policy").mkdir(exist_ok=True)
    _write(OUT / "policy" / "index.html", page_policy(generated))
    (OUT / "data").mkdir(exist_ok=True)
    shutil.copy(store.DATA / "json" / "policy.json", OUT / "data" / "policy.json")
    (OUT / "brief").mkdir(exist_ok=True)
    _write(OUT / "brief" / "index.html", page_brief(board, status, generated))
    _write(OUT / "status" / "index.html", page_status(status, board, generated))
    _write(OUT / ".nojekyll", "")
    print(f"built site/ with {len(board['rows'])} bank pages")
