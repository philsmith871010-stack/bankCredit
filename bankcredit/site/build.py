"""Static site generator. Reads data/json, writes site/."""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from ..models import METRICS
from ..score import PILLARS, BANDS, OVERLAY_CAP
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
<td class="col-name"><button class="watch" data-id="{r["id"]}" aria-label="Watch">{c.ico("star", 15, "#cbd3dc")}</button><a href="banks/{r["id"]}.html"><span class="nm">{c.esc(r["name"])}</span><span class="sub">{sub}</span></a></td>
<td class="col-score"><span class="mono score">{sc(r)}</span>{c.ribbon(r["score"], peer.get("p25"), peer.get("p50"), peer.get("p75"))}</td>
<td class="col-band">{c.band_chip(r["band"])}</td>
<td class="num">{c.fmt(r["cet1"], 1, "%")}</td><td class="num">{c.fmt(r["leverage"], 1, "%")}</td><td class="num">{c.fmt(r["lcr"], 0, "%")}</td>
<td>{c.agency_chips(r["ratings"])}</td><td class="col-mkt">{c.market_glyph(r["market"])}</td>
<td class="col-asof">{age_badge(r["asof"], r["age_days"])}</td></tr>''')
    n_scored = sum(1 for r in rows if r["score"] is not None)
    content = f'''<div class="page-head"><div><h1>Board</h1><div class="lede">{len(rows)} banks and building societies · {n_scored} with enough data to score · figures as of the date on each row</div></div>
<div class="actions"><label class="search">{c.ico("search", 16, c.MUTED)}<input id="q" type="search" placeholder="Search bank or country" aria-label="Search"></label></div></div>
{benchmark_strip(board)}
<div class="filters" id="filters">{filters}</div>
<div class="card table-card"><div class="table-wrap"><table class="board" id="board"><thead><tr>
<th data-sort="name">Bank</th><th data-sort="score">Score · peers</th><th>Band</th><th class="num" data-sort="cet1">CET1</th><th class="num" data-sort="leverage">Lev.</th><th class="num" data-sort="lcr">LCR</th><th>Ratings</th><th>Mkt</th><th data-sort="asof">As of</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>
<div class="table-foot"><span>Ratings from the ESMA register with agency attribution · Mkt is the 30-day direction of the market signal, never a level · a grey band means not enough data yet</span><span class="legend">{c.ribbon(72, 52, 64, 74, 60, 8)} peer 25th to 75th percentile, median in orange</span></div></div>'''
    return c.shell("Board", content, "board", "", generated)


def page_banks_index(board, generated):
    rows = sorted(board["rows"], key=lambda r: (r["region"], r["name"]))
    groups = {}
    for r in rows:
        groups.setdefault(r["region"], []).append(r)
    blocks = "".join(f'<section class="group"><h2>{REGION_LABEL[k]}</h2><div class="grid-cards">' + "".join(
        f'<a class="bank-card" href="{r["id"]}.html"><span class="nm">{c.esc(r["name"])}</span><span class="sub">{TYPE_LABEL.get(r["type"], r["type"])} · {COUNTRY.get(r["country"], r["country"])}</span><span class="row">{c.band_chip(r["band"])}<span class="mono">{sc(r)}</span>{c.agency_chips(r["ratings"][:3])}</span></a>' for r in v) + "</div></section>" for k, v in groups.items())
    content = f'<div class="page-head"><div><h1>Bank profiles</h1><div class="lede">Every entity in the release-one universe, grouped by region</div></div></div>{blocks}'
    return c.shell("Bank profiles", content, "banks", "../", generated)


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
    unverified = c.chip("unverified", "warn") if (last.get("conf") or 1) < 0.9 else ""
    return f'''<div class="tile"><div class="tile-head"><span class="tile-label">{label}</span><span class="tile-flags">{unverified}<span class="src-dot" title="{c.esc(src)}">{c.ico("info", 14, "#b8c2cc")}</span></span></div>
<div class="tile-body"><div><span class="mono big">{shown:,.{dpv}f}</span><span class="mono unit">{u}</span></div>{c.spark(vals)}</div>
<div class="tile-foot"><span>{c.chg(delta, 1, "%" if unit == "m" else "") if delta is not None else "<span class=na>first period</span>"}{" vs prior" if delta is not None else ""}</span><span class="mono">{c.esc(last["d"])}</span></div></div>'''


def page_bank(b, generated):
    series = b["series"]
    tiles = "".join(tile(m, l, u, dp, series) for m, l, u, dp in TILE_METRICS)
    peer = b.get("peer") or {}
    score = b["score"]
    score_html = f'<span class="mono huge">{score:.0f}</span>' if score is not None else '<span class="mono huge muted">—</span>'
    pct = f'<span class="mono">{b["percentile"]}th</span> percentile of {peer.get("n", 0)} peers' if b.get("percentile") is not None else "not enough data to place among peers"
    cov = b.get("coverage") or 0
    overlay = b.get("overlay")
    pillars = b["score_detail"]["pillars"]
    prow = "".join(f'<div class="pillar"><span>{k.replace("_", " ").title()}</span><span class="mono">{"—" if v[0] is None else f"{v[0]:.0f}"}</span><span class="pw">w {PILLARS[k][0]}</span></div>' for k, v in pillars.items())
    # charts
    charts = []
    for metric, label, unit, dp in TILE_METRICS[:2] + [TILE_METRICS[3]]:
        pts = series.get(metric, [])
        if len(pts) >= 2:
            req = None; req_label = "Requirement"
            if metric == "cet1_ratio":
                r = series.get("cet1_requirement") or series.get("overall_capital_requirement")
                if r:
                    req = r[-1]["v"]; req_label = "CET1 requirement" if series.get("cet1_requirement") else "Overall requirement"
            data = [(qlabel(p["d"]), p["v"]) for p in pts[-16:]]
            charts.append(f'<div class="chart-block"><div class="chart-head"><span>{label}</span><span class="muted">{METRICS.get(metric, "")}</span></div>{c.chart(data, unit="" if unit == "m" else unit, req=req, req_label=req_label, dp=0 if unit != "%" or metric in ("lcr", "nsfr") else 1)}</div>')
    ratings_rows = "".join(f'<tr><td>{c.esc(r["agency"])}</td><td class="muted">{c.esc(r["type"].replace("_", " "))} · {c.esc(r["horizon"])}</td><td class="mono b">{c.esc(r["value"])}</td><td class="muted">{c.esc(r["outlook"])}</td><td class="mono muted">{c.esc(r["date"])}</td></tr>' for r in b["ratings_all"])
    ratings_html = f'<table class="plain"><thead><tr><th>Agency</th><th>Type</th><th>Rating</th><th>Outlook</th><th>Date</th></tr></thead><tbody>{ratings_rows}</tbody></table><div class="note">Source: ESMA European Rating Platform, checked daily. Symbols shown with agency attribution; histories are not redistributed.</div>' if ratings_rows else '<div class="empty">No issuer-level ratings found in the ESMA register for this entity.</div>'
    mp = b["market_public"]
    prices = b["prices"]
    price_chart = c.chart([(p["d"][2:7], p["c"]) for p in prices[::max(1, len(prices)//60)]], unit="", dp=2) if len(prices) > 5 else '<div class="empty">Not listed, or no price data collected.</div>'
    market_html = f'''<div class="grid-2"><div class="chart-block"><div class="chart-head"><span>Share price, 12 months</span><span class="muted">{c.esc(b.get("price_currency") or "")}</span></div>{price_chart}</div>
<div class="kv"><div><span>30-day realised volatility</span>{c.fmt(mp.get("vol30"), 1, "%")}</div><div><span>Drawdown from 52-week high</span>{c.fmt(mp.get("drawdown52"), 1, "%")}</div><div><span>Market signal</span><span>{c.market_glyph(mp)} {c.esc(mp.get("label"))}</span></div><div><span>Last price</span><span class="mono">{c.esc(mp.get("last_price_date") or "—")}</span></div>
<div class="note">CDS levels and agency ratings feed the private market overlay and are never shown as levels; only the direction is public.</div></div></div>'''
    # sources
    docs = {}
    for m, pts in series.items():
        for p in pts:
            key = (p["src"], p["doc"])
            docs.setdefault(key, {"metrics": set(), "dates": set(), "method": p["method"]})
            docs[key]["metrics"].add(m); docs[key]["dates"].add(p["d"])
    src_rows = "".join(f'<div class="doc"><span class="doc-ico">{c.ico("doc", 18, c.NAVY)}</span><div><div class="b">{c.esc(k[0])} · {c.esc(v["method"])}</div><div class="muted small">{len(v["metrics"])} metrics · {min(v["dates"])} to {max(v["dates"])}</div></div><a class="muted small" href="{c.esc(k[1])}" target="_blank" rel="noopener">source</a></div>' for k, v in docs.items())
    metric_rows = "".join(f'<tr><td>{c.esc(METRICS.get(m, m))}</td><td class="mono">{pts[-1]["v"]:,.2f}</td><td class="mono muted">{pts[-1]["d"]}</td><td class="muted">{c.esc(pts[-1]["src"])} · {c.esc(pts[-1]["method"])}</td><td class="mono muted">{pts[-1]["conf"]:.2f}{" " + c.chip("unverified", "warn") if (pts[-1]["conf"] or 1) < 0.9 else ""}</td></tr>' for m, pts in series.items() if pts)
    events_rows = "".join(f'<div class="event"><span class="mono muted">{c.esc(str(e.get("date"))[:10])}</span><div><div class="b">{c.esc(e.get("title"))}</div><div class="muted small">{c.esc(e.get("source"))}</div></div>{c.chip(c.esc(e.get("severity") or "info"))}</div>' for e in b["events"]) or '<div class="empty">No events collected yet. Rating actions and disclosures will appear here once the events pipeline runs.</div>'
    content = f'''<div class="page-head"><div class="ident"><span class="avatar">{c.esc(b["short"][:2].upper())}</span><div><h1>{c.esc(b["name"])}</h1>
<div class="lede">{TYPE_LABEL.get(b["type"], b["type"])} · {COUNTRY.get(b["country"], b["country"])}{" · " + c.chip("LEI " + c.esc(b["lei"])) if b["lei"] else ""}{" · " + c.chip("Figures for lead bank subsidiary", "warn") if b.get("basis") == "lead_bank" else ""}</div></div></div>
<div class="actions"><button class="btn watch-btn" data-id="{b["id"]}">{c.ico("star", 16, c.ORANGE)}<span>Watch</span></button><button class="btn primary" onclick="window.print()">{c.ico("download", 16, c.WHITE)}Counterparty report</button></div></div>
<div class="grid-12"><div class="score-card"><div class="score-head"><span class="tile-label light">Counterparty score</span>{c.chip("Band " + (b["band"] or "?"), "orange") if b["band"] and b["band"] != "?" else c.chip("Insufficient data", "warn")}</div>
<div class="score-row">{score_html}<div class="score-meta"><div>{pct}</div><div>coverage <span class="mono">{cov*100:.0f}%</span> of the method</div></div></div>
{c.ribbon(score, peer.get("p25"), peer.get("p50"), peer.get("p75"), 330, 12)}
<div class="pillars">{prow}</div>
<div class="score-note">Public pillars with published weights (w). Market overlay <span class="mono" style="color:#fff;font-weight:600">{("+" if overlay > 0 else "") + f"{overlay:.1f}" if overlay is not None else "—"}</span>, bounded at ±{OVERLAY_CAP:.0f}. <a href="../method/index.html">Method</a></div></div>
<div class="tiles">{tiles}</div></div>
<div class="card tabs-card"><div class="tabs" role="tablist"><button class="tab active" data-tab="trends">Trends</button><button class="tab" data-tab="ratings">Ratings</button><button class="tab" data-tab="market">Market</button><button class="tab" data-tab="events">Events</button><button class="tab" data-tab="sources">Sources</button></div>
<section class="panel active" data-panel="trends"><div class="grid-2">{"".join(charts) or '<div class="empty">Trends appear once two or more periods have been collected.</div>'}</div></section>
<section class="panel" data-panel="ratings">{ratings_html}</section>
<section class="panel" data-panel="market">{market_html}</section>
<section class="panel" data-panel="events">{events_rows}</section>
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
    rows = "".join(row(d, r, e) for d, r, e in items[:400])
    counts = {}
    for _, _, e in items:
        counts[e.get("type")] = counts.get(e.get("type"), 0) + 1
    filters = f'<button class="filter active" data-type="all">All · {len(items)}</button>' + "".join(f'<button class="filter" data-type="{c.esc(t)}">{c.esc(t.title())} · {n}</button>' for t, n in sorted(counts.items()))
    content = (f'<div class="page-head"><div><h1>Events</h1><div class="lede">Rating actions from the ESMA register, Pillar 3 documents as they are collected, and headlines that pass a credit-vocabulary filter. Severity is rules-based; read the source before acting.</div></div></div>'
               f'<div class="filters" id="event-filters">{filters}</div><div class="card pad" id="events">{rows or "<div class=empty>Nothing collected yet.</div>"}</div>')
    return c.shell("Events", content, "events", "../", generated)


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

    def ev_line(d, r, e):
        url = e.get("url") or ""
        t = f'<a href="{c.esc(url)}" target="_blank" rel="noopener">{c.esc(e.get("title"))}</a>' if str(url).startswith("http") else c.esc(e.get("title"))
        return f'<li><span class="mono muted">{d}</span> <a class="b" href="../banks/{r["id"]}.html">{c.esc(r["short"])}</a> · {t} <span class="muted small">{c.esc(e.get("source"))}</span></li>'

    def bank_links(xs):
        return ", ".join(f'<a href="../banks/{r["id"]}.html">{c.esc(r["short"])}</a>' for r in xs) or "none"

    market_line = ("Credit benchmarks: " + "; ".join(f'{c.esc(b["label"])} {b["value"]:.0f}bp ({"+" if b["change30"] > 0 else ""}{b["change30"]:.0f}bp over 30 days)' for b in bm if b.get("change30") is not None)) if bm else "Credit benchmark series not yet collected."
    lead = []
    if widen:
        lead.append(f'Spreads are wider on the month in {", ".join(c.esc(b["label"]) for b in widen)}.')
    if tighten:
        lead.append(f'Tighter on the month: {", ".join(c.esc(b["label"]) for b in tighten)}.')
    if not widen and not tighten and bm:
        lead.append("Benchmark spreads are little changed on the month.")
    lead.append(f'{len(ratings)} rating action{"s" if len(ratings) != 1 else ""} and {len(news)} flagged headline{"s" if len(news) != 1 else ""} in the last seven days across {len(rows)} entities.')
    content = f'''<div class="page-head"><div><h1>Brief</h1><div class="lede">Machine-drafted from the day's tables by fixed rules, not by a language model. {c.esc(today.isoformat())}. Read the linked sources before acting.</div></div></div>
<div class="card pad prose">
<p class="b">{" ".join(lead)}</p>
<p>{market_line}</p>
<h3>Rating actions, seven days</h3><ul class="small">{"".join(ev_line(*x) for x in ratings[:40]) or "<li class=muted>No rating changes, watch placements or outlook changes recorded.</li>"}</ul>
<h3>Headlines that passed the credit filter and carry a flag</h3><ul class="small">{"".join(ev_line(*x) for x in news[:40]) or "<li class=muted>Nothing flagged.</li>"}</ul>
<h3>New Pillar 3 documents</h3><p class="small">{len(docs)} collected in the last seven days. {len(unverified)} loaded with warnings and shown as unverified; {len(queue)} waiting in the review queue. <a href="../status/index.html">Status</a></p>
<h3>Watch points</h3><ul class="small"><li>Band D (weakest public score): {bank_links(band_d)}</li><li>Market signal widening or equity weak: {bank_links(weak_mkt)}</li><li>Regulatory figures older than 150 days: {bank_links([r for r in rows if r["age_days"] and r["age_days"] > 150][:25])}</li></ul>
</div>'''
    return c.shell("Brief", content, "brief", "../", generated)


def page_method(generated):
    pillar_rows = "".join(f'<tr><td class="b">{k.replace("_", " ").title()}</td><td class="mono">{w}</td><td>{", ".join(METRICS.get(m, m) for m in ms)}</td></tr>' for k, (w, ms) in PILLARS.items())
    thr = "".join(f'<tr><td>{METRICS.get(m, m)}</td><td class="mono small">{" · ".join(f"{v}→{s}" for v, s in pts)}</td></tr>' for _, (w, ms) in PILLARS.items() for m, pts in ms.items())
    bands = " · ".join(f'<span class="b">{b}</span> {f} and above' for f, b in BANDS)
    content = f'''<div class="page-head"><div><h1>Method</h1><div class="lede">Version 1, published in full. Information, not advice.</div></div></div>
<div class="card pad prose">
<h2>Sources</h2><p>Regulatory figures come from the FDIC API (US banks, lead bank subsidiary), the EBA Pillar 3 Data Hub (EU and EEA banks, consolidated), and each firm's own Pillar 3 disclosures (UK and other regions, read from PDF by a rules-based KM1 extractor with arithmetic validation; no AI service). Ratings and rating actions come from the ESMA European Rating Platform. Prices come from public market data. CDS levels are medians of the day's reported trades in DTCC's public swap-data files (indicative, inferred from upfront payments) and iTraxx and CDX index prints from the same source; benchmark bond spreads are ICE BofA option-adjusted spread indices from FRED. Headlines are discovered through Google News and kept only when they pass a credit vocabulary and noise filter. Every figure on a profile carries its source, method and reference date.</p>
<h2>Score</h2><p>Each metric is converted to a 0 to 100 sub-score by straight-line interpolation between the thresholds below, then averaged within its pillar and weighted. Missing metrics do not score zero: the weights are re-scaled over what is available and the coverage percentage is shown. A band is only assigned when coverage is at least 50 percent.</p>
<table class="plain"><thead><tr><th>Pillar</th><th>Weight</th><th>Metrics</th></tr></thead><tbody>{pillar_rows}</tbody></table>
<h3>Thresholds (value → sub-score)</h3><table class="plain"><tbody>{thr}</tbody></table>
<h3>Bands</h3><p>{bands}. Bands carry hysteresis in later versions so they do not flicker at boundaries.</p>
<h2>Market overlay</h2><p>A private layer built from agency ratings, five-year CDS levels and changes where a CDS market exists, and equity volatility and drawdown. It adjusts the public score by at most ±{OVERLAY_CAP:.0f} points. The direction and size of the adjustment are shown; the underlying levels are not redistributed.</p>
<h2>Limitations</h2><ul><li>US figures are for the lead bank subsidiary, not the holding company, and follow the US regulatory template.</li><li>UK and other-region figures depend on PDF extraction; failed validations are shown as unverified rather than hidden.</li><li>Peer percentiles are computed only among entities with a score, so they are unstable while coverage is low.</li><li>Back-tests against past failures are planned for version 2.</li></ul>
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
{documents_card(status)}'''
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


def build():
    board = load("board"); status = load("status"); generated = board["generated"]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "banks").mkdir(parents=True); (OUT / "events").mkdir(); (OUT / "method").mkdir(); (OUT / "status").mkdir()
    shutil.copytree(ASSETS, OUT / "assets")
    (OUT / "index.html").write_text(page_board(board, generated))
    (OUT / "banks" / "index.html").write_text(page_banks_index(board, generated))
    for r in board["rows"]:
        (OUT / "banks" / f"{r['id']}.html").write_text(page_bank(load(f"banks/{r['id']}"), generated))
    (OUT / "events" / "index.html").write_text(page_events(board, generated))
    (OUT / "method" / "index.html").write_text(page_method(generated))
    (OUT / "brief").mkdir(exist_ok=True)
    (OUT / "brief" / "index.html").write_text(page_brief(board, status, generated))
    (OUT / "status" / "index.html").write_text(page_status(status, board, generated))
    (OUT / ".nojekyll").write_text("")
    print(f"built site/ with {len(board['rows'])} bank pages")
