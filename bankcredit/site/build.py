"""Static site generator. Reads data/json, writes site/."""
from __future__ import annotations

import json
import os
import re
import shutil

from .. import store
from datetime import date, datetime, timedelta
from pathlib import Path

from ..composite import THREE, describe, of_three, tone_words
from .. import attributed
from ..models import METRICS
from ..score import PILLARS, BANDS, OVERLAY_CAP, RATING_WEIGHT, RATING_SCORE, UNRATED_SCORE, UNRATED_CAP, VERSION, score_cap
from ..composite import SCALE as GRADE_LETTERS
from . import components as c

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "site"
ASSETS = Path(__file__).resolve().parent / "assets"
REGION_LABEL = {"uk": "UK", "eu": "EU and EEA", "aus_can": "Australia and Canada", "asia": "Asia", "gulf": "Gulf", "us_ch": "US and Swiss"}
TYPE_LABEL = {"bank": "Bank", "building_society": "Building society", "subsidiary": "Overseas-owned bank", "holding": "Group"}
COUNTRY = {"GB": "UK", "FI": "Finland", "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "NL": "Netherlands", "DE": "Germany", "FR": "France", "BE": "Belgium", "ES": "Spain", "IT": "Italy", "AT": "Austria", "IE": "Ireland", "AU": "Australia", "CA": "Canada", "SG": "Singapore", "HK": "Hong Kong", "JP": "Japan", "QA": "Qatar", "AE": "UAE", "SA": "Saudi Arabia", "US": "US", "CH": "Switzerland"}
# Which definition belongs to which measure. A reader meeting "NSFR" for the first time should be
# able to ask on the spot, wherever the number appears, so the mapping lives once and every surface
# that draws a label uses it.
GLOSS = {"cet1_ratio": "cet1_ratio", "tier1_ratio": "tier1_ratio", "total_capital_ratio": "total_capital_ratio",
         "leverage_ratio": "leverage_ratio", "tier1_leverage": "leverage_ratio", "rwa": "rwa",
         "lcr": "lcr", "nsfr": "nsfr", "deposits": "deposits", "total_assets": "total_assets",
         "roe": "roe", "roa": "roa", "nim": "nim", "efficiency_ratio": "cost_to_income",
         "npl_ratio": "npl_ratio", "cost_of_risk": "cost_of_risk",
         "overall_capital_requirement": "overall_capital_requirement", "cet1_requirement": "overall_capital_requirement"}


TILE_METRICS = [("cet1_ratio", "CET1 ratio", "%", 1), ("leverage_ratio", "Leverage ratio", "%", 1), ("total_capital_ratio", "Total capital", "%", 1),
                ("lcr", "LCR", "%", 0), ("nsfr", "NSFR", "%", 0)]


TYPE_GLOSS = {"holding": c.info("holding"), "subsidiary": c.info("subsidiary"),
              "building_society": c.info("building_society")}


def sovereign_pill(b, cls: str = "") -> str:
    """The country a bank sits in, with the state's own rating beside it.

    A bank is read against the sovereign that stands behind its banking system, so the country is
    worth more than two letters. Context only: it is not in the score, and the pill says so on
    hover rather than in more text on the page.
    """
    sv = b.get("sovereign") or {}
    country = COUNTRY.get(b.get("country"), b.get("country") or "")
    if not sv.get("composite"):
        return f'<span class="sov{" " + cls if cls else ""}">{c.esc(country)}</span>'
    title = f'{sv["name"]} sovereign rating: {describe(dict(sv, letter=sv["composite"], worst_letter=sv.get("worst") or sv["composite"]))}. Context, not part of the score.'
    return (f'<span class="sov{" " + cls if cls else ""}" title="{c.esc(title)}">{c.esc(country)}'
            f'<b>sovereign {c.esc(sv["composite"])}</b></span>')


def sc(r):
    return "" if r["score"] is None else f"{r['score']:.0f}"


def load(name):
    # through the store, so a build pointed at another copy of the data (the dev server's, under
    # .dev/) reads that copy's export rather than the pipeline's
    return json.loads((store.DATA / "json" / f"{name}.json").read_text())


def qlabel(d: str) -> str:
    dt = date.fromisoformat(d[:10])
    return dt.strftime("%b %y")


def age_badge(asof, age):
    if not asof:
        return '<span class="age age-none">no data</span>'
    late = age is not None and age > 150
    return f'<span class="age{" age-late" if late else ""}" title="Reference date of the latest regulatory figures">{c.esc(asof)}</span>'


def _grade_bucket(r) -> str:
    g = r.get("rating_grade")
    if g is None:
        return "nr"
    return "top" if g <= 4 else "a" if g <= 7 else "bbb" if g <= 10 else "sub"



# The regulator's floor for each ratio, where it is the same for everyone. A bank's own capital
# requirement is in its series and is used ahead of these when it has been collected.
FLOORS = {"lcr": (100.0, "minimum"), "nsfr": (100.0, "minimum")}


def requirement(metric: str, series: dict, country: str | None) -> tuple[float | None, str]:
    """What the figure is measured against first: the bank's own requirement where it is published,
    the regulator's floor where it is the same for everyone, nothing for a currency amount."""
    if metric == "cet1_ratio":
        # only a CET1 requirement will do: the overall requirement is a total-capital figure, and a
        # CET1 ratio measured against it reads as a breach on nearly every bank
        pts = series.get("cet1_requirement")
        if pts and pts[-1].get("v") is not None:
            return float(pts[-1]["v"]), "CET1 requirement"
        return 4.5, "Pillar 1 minimum"
    if metric == "total_capital_ratio":
        pts = series.get("overall_capital_requirement")
        if pts and pts[-1].get("v") is not None:
            return float(pts[-1]["v"]), "overall requirement"
        return 8.0, "Pillar 1 minimum"
    if metric == "leverage_ratio":
        return (3.25, "UK minimum") if country == "GB" else (3.0, "Basel minimum")
    if metric in FLOORS:
        return FLOORS[metric]
    return None, ""


def ratio_verdict(v, pr: dict | None, req: float | None, req_label: str = "requirement") -> tuple[str, str]:
    """The figure judged in words: against the requirement first, then where it sits among peers.
    Returns (class, text); the class is good, warn, bad or na and the text always says which."""
    if v is None:
        return "na", "Not published"
    if req is not None and v < req:
        return "bad", f"Below the {req:g}% {req_label}"
    if not pr or pr.get("p50") is None:
        return ("good", f"Above the {req:g}% {req_label}") if req is not None else ("na", "No peer figures")
    if v >= pr["p75"]:
        return "good", "Top quarter of peers"
    if v >= pr["p50"]:
        return "good", "Above peer median"
    if v >= pr["p25"]:
        return "warn", "Below peer median"
    return "warn", "Bottom quarter of peers"


def tile(metric, label, unit, dp, series, peer_ratios=None, country=None):
    """One headline figure: the value, its move since the last period, a verdict in words against
    the requirement and then the peer group, the recent path with the requirement drawn on it, and
    the peer figures it was judged against. A currency amount gets the value and the move only."""
    pts = series.get(metric, [])
    mark = c.info(GLOSS[metric]) if metric in GLOSS else ""
    if not pts:
        return f'<div class="tile tile-empty"><span class="tile-label">{label}{mark}</span><span class="na big">—</span><span class="tile-foot">not yet collected</span></div>'
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
    unverified = (c.chip("unverified", "warn") + c.info("unverified")) if (last.get("conf") or 1) < 0.9 and str(last.get("method", "")).startswith("pdf") else ""
    if last.get("basis") == "group":
        unverified += c.chip("group figure", "navy")
    move = f'{c.chg(delta, 1, "%" if unit == "m" else "")} vs {c.esc(qlabel(prev["d"]))}' if delta is not None else "<span class=na>first period</span>"
    verdict = peers = ""
    req = None
    if unit == "%":
        req, req_label = requirement(metric, series, country)
        pr = (peer_ratios or {}).get(metric)
        cls, text = ratio_verdict(v, pr, req, req_label)
        room = ""
        if req is not None and v is not None:
            gap = v - req
            room = (f'<span class="tile-room {"good" if gap >= 0 else "bad"}">{"+" if gap >= 0 else "−"}{abs(gap):.{dpv}f} '
                    f'{"over" if gap >= 0 else "under"} the {req:g}% {c.esc(req_label)}</span>')
        verdict = f'<div class="tile-vd {cls}"><i></i>{c.esc(text)}</div>{room}'
        if pr and pr.get("p50") is not None:
            peers = (f'<div class="tile-peers">Peers: median {pr["p50"]:.{dpv}f}{u} · middle half {pr["p25"]:.{dpv}f}–{pr["p75"]:.{dpv}f}{u}'
                     f'{" · " + str(pr["n"]) + " names" if pr.get("n") else ""}</div>')
    return f'''<div class="tile"><div class="tile-head"><span class="tile-label">{label}{mark}</span><span class="tile-flags">{unverified}<span class="src-dot" title="Source: {c.esc(src)}">{c.ico("doc", 13, "#b8c2cc")}</span></span></div>
<div class="tile-body"><div><span class="mono big">{shown:,.{dpv}f}</span><span class="mono unit">{u}</span></div>{c.spark(vals, req=req)}</div>
{verdict}<div class="tile-foot"><span>{move}</span><span class="mono">{c.esc(last["d"])}</span></div>{peers}</div>'''


def debug_panel(b) -> str:
    """Every input that drives this profile, raw, for checking a bank by hand.

    Local builds only. It publishes CDS levels and bond quotes that may not be redistributed, and
    on a bank with history it is 300 KB of the page's 438 KB - the reason profiles felt slow.
    """
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


def rating_history_block(b) -> str:
    """The ladder, what it adds up to, and the moves behind it.

    The register keeps every action under every live rating record, so this is the whole path the
    ratings took, not a line drawn between where they started and where they are.
    """
    h = b["rating_history"]
    moves = h.get("moves") or []
    ups = [m for m in moves if m["action"] == "upgrade"]
    downs = [m for m in moves if m["action"] == "downgrade"]
    comp = h.get("composite") or []
    net = (comp[0][1] - comp[-1][1]) if len(comp) > 1 else 0     # a lower grade is a stronger rating
    since = (h.get("start") or "")[:4]
    def tally(n, word, colour):
        return (f'<div class="rh-n"><b style="color:{colour}">{n}</b><span>{word}{"s" if n != 1 else ""}</span></div>'
                if n else '')
    arrow = {"upgrade": ("&uarr;", c.GREEN), "downgrade": ("&darr;", c.RED),
             "withdrawal": ("&times;", c.MUTED), "new": ("&bull;", c.NAVY)}
    def move_row(m):
        glyph, colour = arrow[m["action"]]
        n = m.get("notches")
        notch = f', {n} notch{"es" if n != 1 else ""}' if n else ""
        what = {"upgrade": f"<b>upgrade</b> by one of the three{notch}",
                "downgrade": f"<b>downgrade</b> by one of the three{notch}",
                "withdrawal": "<b>withdrawn</b> by one of the three", "new": "<b>new rating</b> from one of the three"}[m["action"]]
        after = f' &middot; average {c.esc(c._letter(m["avg"]))}' if m.get("avg") is not None else ""
        return (f'<li><span class="rh-d mono">{c.esc(m["date"])}</span>'
                f'<span class="rh-a" style="color:{colour}">{glyph}</span>'
                f'<span class="rh-w">{what}{after}</span></li>')
    rows = "".join(move_row(m) for m in moves[:8])
    net_txt = ("no net change" if not net else
               f'{abs(net):.1f} notch{"es" if abs(net) != 1 else ""} {"stronger" if net > 0 else "weaker"}')
    return f'''<div class="rh">
<div class="rh-head"><div><h3>Rating history</h3><div class="small muted">Since {c.esc(since)}, from the actions the European Rating Platform holds: the average and the weakest of the three main agencies on every day either moved, and how many of the three held the name on a positive or negative outlook or watch.</div></div>
<div class="rh-tally">{tally(len(ups), "upgrade", c.GREEN)}{tally(len(downs), "downgrade", c.RED)}<div class="rh-n"><b>{c.esc(net_txt.split(" ")[0])}</b><span>{c.esc(" ".join(net_txt.split(" ")[1:]) or "net")}</span></div></div></div>
<div class="rh-body"><div class="rh-chart">{c.rating_timeline(h)}{c.rating_legend(h)}</div>
{f'<div class="rh-moves"><h4 class="rh-mh">Every move since {c.esc(since)}</h4><ul class="rh-list">{rows}</ul></div>' if rows else ''}</div>
</div>'''


def ratings_tile(b) -> str:
    """The rating as the first tile of the profile: the average of the three main agencies, the
    weakest of them, how many of the three hold the name on which outlook, and when one of them
    last acted. No agency is named against a rating anywhere on the site."""
    rs = b.get("rating")
    if not rs:
        return (f'<div class="tile tile-ratings tile-empty"><span class="tile-label">Agency rating{c.info("rating")}</span>'
                f'<span class="na big">NR</span><span class="tile-foot">none of {THREE} publishes an issuer rating on the ESMA register</span></div>')
    wg = rs.get("worst")
    cells = (f'<div class="rcell"><div class="ragency">Average</div><div class="rlt"><span class="mono big">{c.esc(rs["letter"])}</span></div>'
             f'<div class="rst small muted">of {c.esc(of_three(rs["n"]))}</div></div>'
             f'<div class="rcell"><div class="ragency">Weakest</div><div class="rlt"><span class="mono big" style="color:{grade_colour(wg)}">{c.esc(rs["worst_letter"])}</span></div>'
             f'<div class="rst small muted">{"the same" if rs["worst_letter"] == rs["letter"] else "one agency"}</div></div>'
             f'<div class="rcell"><div class="ragency">Outlooks</div><div class="rlt"><span class="big">{tone_glyphs(rs.get("tones") or [])}</span></div>'
             f'<div class="rst small muted">{c.esc(tone_words(rs.get("tones") or []) or "none published")}</div></div>'
             f'<div class="rcell"><div class="ragency">Last action</div><div class="rlt"><span class="mono" style="font-size:16px">{c.esc(rs.get("date") or "—")}</span></div>'
             f'<div class="rst small muted">by any of the three</div></div>')
    # The average's own path since the register's log begins, so the card says where the rating has
    # been as well as where it stands; the Ratings tab below holds every move.
    path = ""
    steps = (b.get("rating_history") or {}).get("composite") or []
    if len(steps) >= 2:
        pts = _at_year_ends(steps, int(steps[0][0][:4]), datetime.utcnow().year)
        if len(pts) >= 2:
            net = steps[0][1] - steps[-1][1]
            n = f"{abs(net):.1f}".rstrip("0").rstrip(".")
            lab = "no net change" if not net else f'{n} notch{"es" if abs(net) != 1 else ""} {"up" if net > 0 else "down"}'
            path = (f'<div class="rpath"><span class="ragency">Since {c.esc(steps[0][0][:4])}</span>'
                    + c.spark([-g for g in pts], w=220, h=26) + f'<span class="small muted">{c.esc(lab)}</span></div>')
    # The average sits large in the first cell, so the heading does not repeat it; the market signal
    # has its own tab and its own line on the score card.
    return (f'<div class="tile tile-ratings"><div class="tile-head"><span class="tile-label">Agency rating{c.info("rating")}</span></div>'
            f'<div class="rcells">{cells}</div>{path}<div class="tile-foot"><span>Long-term ratings of {THREE} on one scale, from the ESMA register, checked daily.</span></div></div>')


def attributed_block(b) -> str:
    """The agencies' own ratings, filled in by the browser from the members file. The page carries
    the frame and the basis; the ratings live in one file that a login can later sit in front of."""
    return (f'<div class="attr" data-attr="{c.esc(b["id"])}"><h3>The agencies\' own ratings</h3>'
            f'<div class="attr-body"><div class="attr-wait small muted">Loading the current rating and outlook each of the three publishes on this name.</div></div>'
            f'<details class="attr-basis"><summary class="small">The basis on which they are shown</summary><p class="small muted">{c.esc(attributed.BASIS)}</p></details></div>')


def tone_glyphs(tones) -> str:
    """One glyph per agency, worst first, so the tile reads ▼▶▶ for one negative and two stable."""
    out = []
    for t in tones:
        out.append(outlook_glyph(t) or '<span title="no outlook published" class="muted">·</span>')
    return f'<span title="{c.esc(tone_words(tones) or "no outlook published")}">{"".join(out)}</span>'


# What each pillar is made of, in the words a reader would use. A sub-score of 0 beside a weight of
# 10 is unreadable without knowing which measure produced it.
PILLAR_INPUTS = {
    "rating": "the average of the three main agencies' long-term ratings on this entity",
    "capital": "CET1, leverage and total capital ratios against Basel thresholds",
    "liquidity": "liquidity coverage ratio and net stable funding ratio",
    "stability": "CET1 ratio over the entity's overall capital requirement",
    "asset_quality": "the non-performing or noncurrent loan ratio",
    "profitability": "return on equity, return on assets and cost to income",
}


def pillar_note(k: str, cell) -> str:
    """The native tooltip on a pillar: what it measures, what it scored, what it counts for."""
    label = c.PILLAR_LABEL[k]
    what = PILLAR_INPUTS.get(k, "")
    if cell[0] is None:
        return f"{label}: {what}. Not published for this entity, so its weight is re-scaled over the rest."
    if cell[0] == 0 and k == "stability":
        return (f"{label}: {what}. Sub-score 0: CET1 is below the requirement the method measures it "
                f"against, so there is no headroom to score.")
    return (f"{label}: {what}. Sub-score {cell[0]:.0f} out of 100. The weight beside it, w, is the "
            f"reader's: set it on the Weightings tab.")




def summary_block(b: dict, generated: str) -> str:
    """One summary on the profile. The written one (a background sentence and a short synthesis)
    when it still holds, with when it was written and what has moved since; otherwise the paragraph
    the data gives on every build, so the reader is never told a stale thing as current. Both used
    to stand one above the other, saying the same ratios twice."""
    from .. import summaries as S
    today = date.fromisoformat(generated[:10])
    br = S.brief(b, today)
    # the space goes inside the span: the writer collapses whitespace between tags
    l1 = '<div class="brief-l1">' + "".join(f'<span class="br-{k}">{c.esc(br[k])} </span>' for k in S.SENTENCES if br.get(k)) + '</div>'
    s = S.load(b["id"])
    if not s:
        return f'<div class="card brief">{l1}</div>'
    if S.check(s, S.brief_text(br)):
        # it quotes a figure the paragraph no longer carries, or headlines the site no longer shows;
        # it is owed a rewrite and is not shown as current
        return (f'<div class="card brief">{l1}<div class="brief-meta muted">The written summary of {S.fdate(s["written"])} '
                'is being rewritten; this paragraph is drawn from the data on every build.</div></div>')
    moved = S.changes_since(s.get("inputs") or {}, br["fingerprint"])
    meta = f'Written {S.fdate(s["written"])}' + (f' from figures to {S.fdate((s.get("inputs") or {}).get("asof"))}' if (s.get("inputs") or {}).get("asof") else "") + "."
    stale = f' <span class="brief-stale">Since then: {c.esc("; ".join(moved))}.</span>' if moved else ""
    return (f'<div class="card brief"><p class="brief-bg">{c.esc(s["background"])}</p>'
            f'<p class="brief-syn">{c.esc(s["synthesis"])}</p><div class="brief-meta muted">{meta}{stale}</div></div>')


def page_bank(b, generated):
    series = b["series"]
    tiles = "".join(tile(m, l, u, dp, series, b.get("peer_ratios"), b.get("country")) for m, l, u, dp in TILE_METRICS)
    peer = b.get("peer") or {}
    score = b["score"]
    score_html = f'<span class="mono huge">{score:.0f}</span>' if score is not None else '<span class="mono huge muted">—</span>'
    # the pillars the browser re-weighs with the reader's own weights; none where the score is
    # withheld, so a reader's weights cannot draw a number the method refuses
    pw_attr = (f' data-pw="{c.esc(json.dumps([b["score_detail"]["pillars"].get(k, (None,))[0] for k in c.PILLAR_KEYS]))}"'
               if score is not None else "")
    pct = f'<span class="mono">{b["percentile"]}th</span> percentile of {peer.get("n", 0)} peers' if b.get("percentile") is not None else "not enough data to place among peers"
    cov = b.get("coverage") or 0
    overlay = b.get("overlay")
    pillars = b["score_detail"]["pillars"]
    order = ["rating", "capital", "liquidity", "stability", "asset_quality", "profitability"]
    prow = "".join(f'<div class="pillar{" pillar-na" if pillars[k][0] is None else ""}" data-k="{k}" title="{c.esc(pillar_note(k, pillars[k]))}"><span class="pl">{c.PILLAR_LABEL[k]}</span>'
                   f'<span class="mono{" pz" if pillars[k][0] == 0 else ""}">{"—" if pillars[k][0] is None else f"{pillars[k][0]:.0f}"}</span><i><b style="width:{0 if pillars[k][0] is None else pillars[k][0]:.0f}%"></b></i>'
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
        standing.append(f'<button class="sm" type="button" data-title="Counterparty score, recomputed" data-def="score" '
                        f'data-sub="Today\'s method and composite rating applied to the ratios as they stood at each quarter end '
                        f'\u00b7 {len(sc_pts)} quarters" aria-label="Expand score history">'
                        f'<div class="sm-head"><span class="sm-label">Score, recomputed</span>'
                        f'<span class="sm-val mono">{last:.0f}</span></div>'
                        f'<div class="sm-sub">{dchip}<span class="muted">vs {c.esc(sc_pts[-2][0])}</span></div>'
                        f'{c.chart(sc_pts, unit="", dp=1, w=300, h=96, compact=True)}'
                        f'<template>{c.chart(sc_pts, unit="", dp=1, w=720, h=300, ymin=0, ymax=100, step=20)}</template></button>')
    # The published score, day by day, used to sit beside this. Each day's figure carries that day's
    # method and data fixes, so it stepped about in ways that say nothing about the bank; the
    # recomputed line above is the like-for-like path, and the one worth reading.
    standing_block = ""
    if standing:
        standing_block = (f'<div class="sm-block" style="--n:{len(standing)}"><div class="sm-sec">Score</div>'
                      f'<div class="sm-cards">{"".join(standing)}</div></div>')
        n_charts += len(standing)
    for group, metrics in TREND_GROUPS:
        cards = []
        for metric, label, unit, dp in metrics:
            pts = series.get(metric, [])
            if len(pts) < 2:
                continue
            # a series that stopped years ago is history, not a trend: drawn beside current ones it
            # read as if "+8.6% vs Dec 20" were news
            if (date.fromisoformat(generated[:10]) - date.fromisoformat(str(pts[-1]["d"])[:10])).days > 900:
                continue
            # the same floor the headline tile judges against: a bank's own requirement where it is
            # published, and never the overall requirement against a CET1 ratio
            req, req_label = (requirement(metric, series, b.get("country")) if metric in ("cet1_ratio", "total_capital_ratio") else (None, "Requirement"))
            if req_label == "Pillar 1 minimum":
                req = None                            # nine points below the data, it says nothing on a chart
            shown = pts if len(pts) <= 48 else pts[-48:]                       # up to twelve years of quarters
            u = unit
            if u == "m":
                u = "bn" if any(p["v"] and abs(p["v"]) > 5000 for p in shown) else "m"
            data = [(qlabel(p["d"]), (p["v"] / 1000 if u == "bn" else p["v"])) for p in shown]
            cdp = 0 if u != "%" or metric in ("lcr", "nsfr") else dp
            last, prev = data[-1][1], data[-2][1]
            delta = round(last - prev, cdp)            # a move too small to show is no move: never "−0%"
            good = (delta >= 0) != (metric in LOWER_BETTER)
            dchip = f'<span class="delta {"up" if good else "down"}">{"+" if delta > 0 else ("−" if delta < 0 else "")}{abs(delta):.{cdp}f}{u if u == "%" else ""}</span>' if abs(delta) > 0 else '<span class="delta flat">no change</span>'
            # the peer group's current quartile band behind the bank's own path, on the ratios
            # where a peer position means anything; a currency amount is not comparable that way
            pq = (b.get("peer_ratios") or {}).get(metric) if u == "%" else None
            band = (pq["p25"], pq["p75"]) if pq else None
            median = pq["p50"] if pq else None
            vs = ""
            if pq:
                diff = last - median
                if abs(diff) < 0.05:
                    diff = 0.0
                cls = "up" if (diff >= 0) != (metric in LOWER_BETTER) else "down"
                vs = (f'<span class="sm-peer {cls if diff else "flat"}">{"+" if diff > 0 else ("−" if diff < 0 else "")}'
                      f'{abs(diff):.{cdp}f} vs peers</span>')
            big = c.chart(data, unit="" if u in ("m", "bn") else u, req=req, req_label=req_label, dp=cdp,
                          band=band, median=median, w=720, h=300)
            small = c.chart(data, unit="" if u in ("m", "bn") else u, req=req, dp=cdp,
                            band=band, median=median, w=300, h=96, compact=True)
            src = pts[-1].get("src", "")
            # a marker cannot sit inside the button, so the definition travels with the card and is
            # printed when the chart is opened full size
            gk = GLOSS.get(metric, "")
            cards.append(f'<button class="sm" type="button" data-title="{c.esc(label)}" data-def="{gk}" data-sub="{c.esc(METRICS.get(metric, ""))} · {len(data)} periods · {c.esc(src)}" aria-label="Expand {c.esc(label)}">'
                         f'<div class="sm-head"><span class="sm-label">{c.esc(label)}</span><span class="sm-val mono">{last:,.{cdp}f}<small>{u if u != "m" else "m"}</small></span></div>'
                         f'<div class="sm-sub">{dchip}<span class="muted">vs {c.esc(data[-2][0])}</span>{vs}</div>{small}<template>{big}</template></button>')
            n_charts += 1
        if cards:
            # the block asks for room for its own charts, so a section of one can share a row
            charts.append(f'<div class="sm-block" style="--n:{len(cards)}"><div class="sm-sec">{group}</div>'
                          f'<div class="sm-cards">{"".join(cards)}</div></div>')
            # the score's own history opens the row after the first group, so a short row starts on
            # the headline series and simply ends early
            if standing_block and len(charts) == 1:
                charts.append(standing_block)
                standing_block = ""
    # the score's own history closes the trends, where it shares a row with the other short section
    if standing_block:
        charts.append(standing_block)
    rs = b.get("rating")
    if rs:
        three = "Fitch, S&amp;P and Moody's"
        tw = tone_words(rs.get("tones") or []) or "none published"
        stands = ('<h3>What stands today</h3><table class="plain"><tbody>'
                  f'<tr><td class="b">Average</td><td class="mono b">{c.esc(rs["letter"])}</td><td class="muted">of {c.esc(of_three(rs["n"]))} main agencies, long-term ratings on one scale</td></tr>'
                  f'<tr><td class="b">Weakest</td><td class="mono b">{c.esc(rs["worst_letter"])}</td><td class="muted">the lowest of them</td></tr>'
                  f'<tr><td class="b">Outlooks</td><td>{tone_glyphs(rs.get("tones") or [])}</td><td class="muted">{c.esc(tw)}</td></tr>'
                  f'<tr><td class="b">Last action</td><td class="mono">{c.esc(rs.get("date") or "—")}</td><td class="muted">the most recent action by any of the three</td></tr>'
                  '</tbody></table>'
                  f'<div class="note">Source: ESMA European Rating Platform, checked daily. The three are {three}; which of them said what is not shown, '
                  'and the letters are this site&#39;s notation for a position on the scale, not any agency&#39;s symbol.</div>')
        ratings_html = (rating_history_block(b) if b.get("rating_history") else "") + stands + attributed_block(b)
    else:
        ratings_html = f'<div class="empty">None of {THREE} publishes an issuer-level rating on this entity in the ESMA register.</div>'
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
    # an unlisted subsidiary shows its group's listed equity, named, rather than an empty panel
    owner = b.get("price_owner_name")
    price_head = f'Share price, 12 months{"" if not owner else " &middot; " + c.esc(owner)}'
    price_note = (f'<div class="note">{c.esc(owner)} is the listed company; this entity has no equity of its own, '
                  f'and the group price does not enter its score.</div>') if owner else ""
    # the volatility and the drawdown describe whichever series is drawn above them
    pstat = (b.get("price_owner_stats") or {}) if owner else mp
    owner_tag = f' <span class="muted">&middot; {c.esc(owner)}</span>' if owner else ""
    market_html = f'''<div class="grid-2"><div class="chart-block"><div class="chart-head"><span>{price_head}</span><span class="muted">{c.esc(b.get("price_currency") or "")}</span></div>{price_chart}{price_note}</div>
<div class="kv"><div><span>30-day realised volatility{owner_tag}</span>{c.fmt(pstat.get("vol30"), 1, "%")}</div><div><span>Drawdown from 52-week high{owner_tag}</span>{c.fmt(pstat.get("drawdown52"), 1, "%")}</div><div><span>Market signal</span><span>{c.market_glyph(mp)} {c.esc(mp.get("label"))}</span></div><div><span>Last price{owner_tag}</span><span class="mono">{c.esc(pstat.get("last_price_date") or "—")}</span></div>{bond_line}
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
    # a source key can carry a qualifier - "eba_te (lead bank)" - and the name is the part before it
    def source_name(key: str) -> str:
        base, _, rest = key.partition(" (")
        return SOURCE_NAMES.get(base, base) + (" (" + rest if rest else "")
    # how a figure was read, in words rather than the pipeline's own shorthand
    METHOD_NAMES = {"pdf_rules": "read from the PDF", "pdf_rules_prior": "read from the PDF, prior-period column",
                    "csv": "published data file", "xbrl": "tagged XBRL filing", "api": "public API",
                    "json": "public API", "html": "read from the web page"}
    by_src: dict[str, dict] = {}
    for (src, doc), v in docs.items():
        g = by_src.setdefault(src, {"docs": [], "metrics": set(), "dates": set(), "method": v["method"]})
        g["docs"].append((max(v["dates"]), doc)); g["metrics"] |= v["metrics"]; g["dates"] |= v["dates"]
    src_rows = ""
    for src, g in sorted(by_src.items(), key=lambda kv: -len(kv[1]["dates"])):
        latest = max(g["docs"])[1]
        n = len(g["docs"])
        src_rows += (f'<div class="doc"><span class="doc-ico">{c.ico("doc", 18, c.NAVY)}</span><div><div class="b">{c.esc(source_name(src))} <span class="muted small">· {c.esc(METHOD_NAMES.get(g["method"], g["method"]))}</span></div>'
                     f'<div class="muted small">{n} document{"s" if n != 1 else ""} · {len(g["metrics"])} metrics · {min(g["dates"])} to {max(g["dates"])}</div></div>'
                     f'<a class="filter" href="{c.esc(latest)}" target="_blank" rel="noopener">Latest source</a></div>')
    metric_rows = "".join(f'<tr><td>{c.esc(METRICS.get(m, m))}</td><td class="mono">{pts[-1]["v"]:,.2f}</td><td class="mono muted">{pts[-1]["d"]}</td><td class="muted">{c.esc(source_name(pts[-1]["src"]))} <span class="small">· {c.esc(METHOD_NAMES.get(pts[-1]["method"], pts[-1]["method"]))}</span></td><td class="mono muted">{pts[-1]["conf"]:.2f}{" " + c.chip("unverified", "warn") if (pts[-1]["conf"] or 1) < 0.9 and str(pts[-1]["method"]).startswith("pdf") else ""}{" " + c.chip("group figure", "navy") if pts[-1].get("basis") == "group" else ""}</td></tr>' for m, pts in series.items() if pts)
    content = f'''<div class="page-head"><div class="ident"><span class="avatar">{c.esc(b["short"][:2].upper())}</span><div><h1>{c.esc(b["name"])}</h1>
<div class="lede">{TYPE_LABEL.get(b["type"], b["type"])}{TYPE_GLOSS.get(b["type"], "")} · {sovereign_pill(b)}{'<span class="lei mono small muted" title="Legal Entity Identifier">LEI ' + c.esc(b["lei"]) + '</span>' if b["lei"] else ""}{" · " + c.chip("Figures for lead bank subsidiary", "warn") if b.get("basis") == "lead_bank" else ""}</div></div></div>
<div class="actions"><a class="btn btn-back" href="../tool/index.html#universe">&lsaquo; All names</a><button class="btn watch-btn" data-id="{b["id"]}">{c.ico("star", 16, c.ORANGE)}<span>Watch</span></button></div></div>
<div class="grid-12"><div class="score-card"{pw_attr} data-overlay="{overlay if overlay is not None else 0}" data-grade="{b.get("rating_grade") if b.get("rating_grade") is not None else ""}" data-coverage="{cov}"><div class="score-head"><span class="tile-label light">Counterparty score{c.info("score")}</span><span class="score-band">{c.chip("Band " + (b["band"] or "?"), "orange") + c.info("band") if b["band"] and b["band"] != "?" else c.chip("Not scored: " + (b.get("unscored") or "insufficient data"), "warn") + c.info("not_scored")}</span></div>
<div class="score-main"><div class="score-fig">{score_html}<div class="score-meta"><div>{pct}{c.info("percentile") if b.get("percentile") is not None else c.info("peer_group")}</div><div>coverage{c.info("coverage")} <span class="mono">{cov*100:.0f}%</span> of the method</div></div>
{c.ribbon(score, peer.get("p25"), peer.get("p50"), peer.get("p75"), 330, 12, fluid=True)}</div>
<div class="pillars">{prow}</div></div>
{f'<div class="np-note"><b>{c.esc(b["not_published"]["reason"][0].upper() + b["not_published"]["reason"][1:])}.</b> {c.esc(b["not_published"].get("standing") or "")}. A score needs current capital ratios for this entity, so none is shown; the rating and the standing above are what to judge this name on. <a href="{c.esc(b["not_published"].get("source") or "")}" target="_blank" rel="noopener">Source</a></div>' if b.get("not_published") else ''}
<div class="score-note">The agency rating and the bank's own ratios, each weighted (w).{c.info("pillar")}{' <span class="b" style="color:#ffd9b3">No score: a score needs an agency rating and current capital ratios.</span>' if b.get("unscored") else (' <span class="b" style="color:#ffd9b3">Capped by rating at ' + f"{score_cap(b.get('rating_grade')):.0f}" + '.</span>' if b.get("rating_grade") is not None and score_cap(b.get("rating_grade")) < 100 else '')} {('Market signal <span class="mono" style="color:#fff;font-weight:600">' + ("+" if overlay > 0 else "") + f"{overlay:.1f}" + '</span>. ') if overlay else ''}<a href="../admin/index.html#method">Method</a></div></div>
{ratings_tile(b)}</div>
{summary_block(b, generated)}
<div class="tiles">{tiles}</div>
<div class="card tabs-card"><div class="tabs" role="tablist"><button class="tab active" data-tab="trends">Trends</button><button class="tab" data-tab="ratings">Ratings</button><button class="tab" data-tab="market">Market</button><button class="tab" data-tab="sources">Sources</button>{'<button class="tab" data-tab="data">Data</button>' if b.get("debug") else ''}</div>
<section class="panel active" data-panel="trends">{f'<div class="sm-intro small muted">Open a card for every point and its date.{" The grey band is where the peer group stands today, quartile to quartile." if b.get("peer_ratios") else ""}</div>' if n_charts else ''}{f'<div class="sm-flow">{"".join(charts)}</div>' if charts else '<div class="empty">Trends appear once two or more periods have been collected.</div>'}</section>
<section class="panel" data-panel="ratings">{ratings_html}</section>
<section class="panel" data-panel="market">{market_html}</section>
{debug_panel(b) if b.get("debug") else ''}
<section class="panel" data-panel="sources"><h3>Documents and feeds</h3>{src_rows or '<div class="empty">Nothing collected yet.</div>'}<h3>Latest value of every metric held</h3><div class="table-wrap"><table class="plain sortable"><thead><tr><th data-sortable>Metric</th><th data-sortable class="num">Value</th><th data-sortable>Reference date</th><th data-sortable>Source</th><th data-sortable class="num">Confidence</th></tr></thead><tbody>{metric_rows}</tbody></table></div></section></div>'''
    return c.shell(b["name"], content, "", "../", generated)


def page_brief_redirect(generated):
    return '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=../tool/index.html#policy"><title>Brief moved</title><p>The brief has gone; <a href="../tool/index.html#policy">your counterparties</a> carry what has moved on each name.</p>'


# A tab named here is held back: its fragment is not written and its button is not drawn. The
# Events tab was removed outright on 3 November 2026 (docs/news-removed.md): a name's rating
# actions are on its Ratings tab and its documents on Sources, so the feed added nothing a reader
# could not find on the name itself.
HOME_TABS_HIDDEN = ()


def page_method(generated, inner: bool = False):
    mname = lambda m: METRICS.get(m) or {"cet1_headroom": "CET1 above the bank's own requirement (points)"}.get(m, m.replace("_", " "))
    pillar_rows = "".join(f'<tr><td class="b">{c.PILLAR_LABEL.get(k, k)}</td><td class="tnum">{w}</td><td>{", ".join(mname(m) for m in ms)}</td></tr>' for k, (w, ms) in PILLARS.items())
    thr = "".join(f'<tr><td>{mname(m)}</td><td class="tnum small">{" · ".join(f"{v}→{s}" for v, s in pts)}</td></tr>' for _, (w, ms) in PILLARS.items() for m, pts in ms.items())
    bands = " · ".join(f'<span class="b">{b}</span> {f} and above' for f, b in BANDS)
    grade_cells = "".join(f'<td class="tnum small">{c.esc(l)}<br>{RATING_SCORE[i + 1]}</td>' for i, l in enumerate(GRADE_LETTERS))
    ratio_weight = sum(w for w, _ in PILLARS.values())
    body = f'''<div class="card pad prose" id="method-prose">
<h2>Score</h2><div class="wbar" aria-hidden="true"><span style="flex:{RATING_WEIGHT}" class="w-rating">{c.PILLAR_LABEL["rating"]} {RATING_WEIGHT}</span>{"".join(f'<span style="flex:{w}" class="w-{k}{" w-narrow" if w < 10 else ""}" title="{c.PILLAR_LABEL[k]} {w}">{(c.PILLAR_LABEL[k] + " ") if w >= 10 else ""}{w}</span>' for k, (w, _) in PILLARS.items())}</div>
<p class="small muted wlegend">{" · ".join([c.PILLAR_LABEL["rating"] + " " + str(RATING_WEIGHT)] + [c.PILLAR_LABEL[k] + " " + str(w) for k, (w, _) in PILLARS.items()])}</p>
<p>The score runs from 0 to 100. The agency rating counts for {RATING_WEIGHT}%: the average of the three main agencies' long-term ratings, converted by the table below. The bank's own ratios count for the other {ratio_weight}%: each is scored from 0 to 100 against the thresholds below and averaged within its part. A ratio the bank does not publish is left out and the rest re-weighted, and the coverage figure says how much of the method a score rests on.</p>
<p>A score is withheld, with the reason, when a bank has no agency rating, no capital ratio, or capital figures older than eighteen months. A rating in the BBB range caps the score at 74.9 (band B), and one below investment grade at 64.9 (band C).</p>
<div class="bandscale" aria-hidden="true">{"".join(f'<span class="band-{b}" style="flex:{(100 if b == "A" else 80 if b == "B" else 65 if b == "C" else 50 if b == "D" else 35) - f}"></span>' for f, b in BANDS)}</div><p class="small muted wlegend">{" · ".join(f"Band {b} {f}+" if f else f"Band {b} below 35" for f, b in BANDS)}</p>
<table class="plain"><thead><tr><th>Component</th><th>Weight</th><th>Inputs</th></tr></thead><tbody><tr><td class="b">{c.PILLAR_LABEL["rating"]}</td><td class="mono">{RATING_WEIGHT}</td><td>Composite long-term agency rating; required for a score; caps of 74.9 for the BBB range and 64.9 below investment grade</td></tr>{pillar_rows}</tbody></table>
<h3>Rating sub-scores</h3><div class="table-wrap"><table class="plain subscores"><tbody><tr>{grade_cells}</tr></tbody></table></div>
<h3>Thresholds (value → sub-score)</h3><table class="plain"><tbody>{thr}</tbody></table>
<h3>Bands</h3><p>{bands}.</p>
<h2>Ratings</h2><p>The site shows one rating per name: the average of the long-term ratings Fitch, S&amp;P and Moody's hold on it, on one scale, with the weakest of the three beside it and one outlook mark per agency. Ratings come from the ESMA European Rating Platform, refreshed daily, and each profile carries the history the register publishes back to July 2015. Agencies outside the three are not averaged in.</p>
<details class="method-more"><summary>The agencies' own ratings, and the basis for quoting them</summary><p>Each profile also shows the current long-term rating and outlook and the current short-term rating that each of the three main agencies publishes on the name, with the agency named, the date and a link to the source. This view is a quotation, not a feed: current ratings only, no history by agency, no download. The basis on which it is shown is set out beside it and repeated here.</p><p class="note">{c.esc(attributed.BASIS)}</p></details>
<h2>Market signal</h2><p>A layer built from five-year CDS levels and 30-day changes where a CDS market exists (otherwise the 30-day change in the bank's own bond yields against peers), 30-day equity volatility and drawdown from the 52-week high. It adjusts the public score by at most ±{OVERLAY_CAP:.0f} points.</p><details class="method-more"><summary>How the signal is weighted and measured</summary><p>Provisional weighting (September 2026): the three signals count equally, each worth at most 2.5 points either way. A CDS move is measured within one source (settlement against settlement, or trade medians on days with three or more trades) and split into the part shared with iTraxx Senior Financials and the part that is the bank's own; the label says which. The direction and size of the adjustment are shown; CDS levels themselves are not redistributed.</p></details>
<h2>Limitations</h2><p>What the data cannot yet do: chiefly, UK figures come from reading PDFs, and some pillars are held only for some regions.</p><details class="method-more"><summary>Every limitation</summary><ul><li>US banking groups appear twice, as in the UK: the operating bank a depositor faces (Call Report figures from the FDIC, with the US Tier 1 leverage ratio scored on its own scale, and the group's LCR shown as a group figure because banks do not publish their own) and the holding company (binding Basel ratios, the lower of the standardised and advanced approaches, from its Pillar 3 report or XBRL filings, the supplementary leverage ratio, the public LCR disclosure, and asset quality and profitability inherited from its lead bank, labelled).</li><li>UK and other-region figures depend on PDF extraction; failed validations are shown as unverified rather than hidden.</li><li>Peer percentiles are computed only among entities with a score, so they are unstable while coverage is low.</li><li>Asset quality and profitability are held only for US banks so far, so those pillars are re-scaled away for most of the universe; the Coverage page shows this per bank.</li><li>Back-tests against past failures are planned.</li></ul></details>

<h2>Sources</h2><p>Regulators' and banks' own published figures, the ESMA rating register and public market prices.</p><details class="method-more"><summary>Every source</summary><p>Regulatory figures come from the FDIC API (US banks, lead bank subsidiary), the EBA Pillar 3 Data Hub and Transparency Exercises (EU and EEA banks, consolidated), and each firm's own Pillar 3 disclosures (UK and other regions, read from PDF by a rules-based KM1 extractor with arithmetic validation; no AI service). Ratings and rating actions come from the ESMA European Rating Platform. Prices come from public market data. Bond quotes come from Börse Frankfurt's public price pages for each bank's senior fixed-rate bonds (two to eight years to run); they stay private and only the 30-day yield change against other bank bonds in the same currency is shown. CDS levels are medians of the day's reported trades in DTCC's public swap-data files (indicative, inferred from upfront payments), and the iTraxx and CDX index levels shown as credit benchmarks are index prints from the same source. Every figure on a profile carries its source, method and reference date.</p></details></div>'''
    content = (f'<div class="page-head"><div><h1>Method</h1><div class="lede">Version {VERSION}, '
               f'published in full. Information, not advice.</div></div></div>' + with_contents(body))
    return content if inner else c.shell("Method", content, "method", "../", generated)


def with_contents(body: str) -> str:
    """A reference document read in pieces: the sections stand beside it and say where you are.

    The page is long because the method is long, and cutting it into tabs would hide the part a
    reader is checking against the part it depends on. A rail is the compromise: nothing is hidden,
    and no section is more than one click away.
    """
    heads, out, n = [], [], 0
    for m in re.finditer(r"<h2>(.*?)</h2>", body):
        n += 1
        heads.append((f"s{n}", re.sub(r"<[^>]+>", "", m.group(1))))
    n = 0
    def tag(m):
        nonlocal n
        n += 1
        return f'<h2 id="s{n}">{m.group(1)}</h2>'
    body = re.sub(r"<h2>(.*?)</h2>", tag, body)
    links = "".join(f'<a href="#{i}">{c.esc(t)}</a>' for i, t in heads)
    out = (f'<div class="docpage"><nav class="doc-nav" aria-label="Sections">'
           f'<div class="doc-nav-head">On this page</div>{links}</nav>{body}</div>')
    return out


HEALTH_STATE = {"ok": ("good", "collecting"), "overdue": ("warn", "overdue"),
                "never": ("bad", "never collected"), "no source": ("bad", "no source"),
                "by design": ("muted", "not published")}


def health_card() -> str:
    """Which sources are still working. A bank redesigns its investor pages, the locator stops
    matching, and nothing fails: the collector just returns nothing. This is where that shows."""
    from .. import health
    rep = health.load()
    if not rep:
        return ""
    counts, rows = rep.get("counts", {}), rep.get("entities", [])
    chips = "".join(c.chip(f"{counts.get(k, 0)} {label}", tone)
                    for k, (tone, label) in HEALTH_STATE.items() if counts.get(k))
    faults = "".join(f'<li class="bad">{c.esc(f["entity"])}: {c.esc(f["fault"])}</li>' for f in rep.get("faults", []))
    def group(state):
        xs = [r for r in rows if r["state"] == state]
        if not xs:
            return ""
        items = ", ".join(f'<a href="../banks/{r["entity"]}.html">{c.esc(r["short"])}</a>'
                          + (f' <span class="mono muted">{r["age_days"]}d</span>' if r.get("age_days") else "")
                          for r in xs)
        return f'<p class="small"><span class="b">{HEALTH_STATE[state][1].capitalize()}:</span> {items}</p>'
    return f'''<div class="card pad"><h3>Source health</h3>
<p class="small muted">Every entity\'s Pillar 3 source, checked against what it has actually delivered. "Overdue" means the source worked once and its newest capital figure is now more than 300 days old; "never collected" means a locator exists and has never yielded a document.</p>
<div class="chips">{chips}</div>
{f'<ul class="small">{faults}</ul>' if faults else ''}
{group("never")}{group("overdue")}{group("no source")}</div>'''


# The day's collection is due from 05:00 UTC. Whether it arrived, and how late, has until now been
# knowable only from a routine's chat reply that nobody reads - which is how eight consecutive
# mornings went by with the punctuality layer doing nothing and reporting success.
#
# Read from the run log rather than from data/state/last-collect. The workflow writes that stamp
# after the site is built, deliberately, so that a run which fails before publishing leaves the day
# still owed - which meant this line reported the previous run every time and contradicted the
# table beneath it. The run log is written by the adapters themselves, before the build, so it
# describes the run that produced this page.
DUE_HOUR = 5
LATE_HOURS = 2
MARKER = "esma"      # runs only in a full collection, so it marks the day's collection and nothing else


def punctuality(status, generated: str) -> str:
    """When the day's collection ran, against when it was due."""
    runs = [r for r in (status.get("runs") or []) if r.get("source") == MARKER and r.get("started")]
    if not runs:
        return ('<div class="punct bad"><b>No collection recorded.</b> The run log holds no '
                'collection, so nothing on this page can be assumed current.</div>')
    last = max(runs, key=lambda r: str(r["finished"]))
    began = datetime.fromisoformat(str(last["started"])[:19])
    ended = datetime.fromisoformat(str(last["finished"])[:19])
    now = datetime.fromisoformat(str(generated)[:19].replace("Z", ""))
    if began.date() < now.date():
        days = (now.date() - began.date()).days
        return (f'<div class="punct bad"><b>No collection today.</b> The last one ran on '
                f'{began:%Y-%m-%d} at {began:%H:%M} UTC, {days} day{"s" if days != 1 else ""} ago. '
                f'Every figure below is from that run.</div>')
    due = began.replace(hour=DUE_HOUR, minute=0, second=0, microsecond=0)
    late = (began - due).total_seconds() / 3600
    ran = f'started {began:%H:%M} and finished {ended:%H:%M} UTC'
    if late <= LATE_HOURS:
        return (f'<div class="punct good">Today\'s collection {ran}, '
                f'{_hm(late)} after the usual 05:00.</div>')
    return (f'<div class="punct warn">Today\'s collection {ran}, <b>{_hm(late)}</b> later than '
            f'the usual 05:00.</div>')


def _hm(hours: float) -> str:
    m = max(0, int(round(hours * 60)))
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m} minutes"


# What each source is, in the reader's words rather than the adapter's name.
SOURCE_LABEL = {"bonds": "Bond quotes", "dtcc": "CDS trades (DTCC)", "eba": "EBA Pillar 3 hub", "edgar": "SEC filings",
                "esef": "Annual accounts (ESEF)", "esma": "Agency ratings (ESMA)", "events": "Rating actions",
                "fdic": "FDIC returns", "fundamentals": "Accounts (Yahoo)", "ice": "CDS prices (ICE)",
                "nsm_release": "Results (FCA NSM)", "pillar3": "Pillar 3 reports", "sovereign": "Sovereign ratings",
                "te": "EBA Transparency Exercise", "yahoo": "Share prices"}


def run_note(msg, names: dict | None = None) -> str:
    """A run's message as a line a reader can take in: how many names failed and which, rather than
    the Python exception, which stays in the cell's title for whoever needs it."""
    msg = "" if msg is None or str(msg) == "nan" else str(msg)
    if not msg:
        return ""
    names_of = names
    names = re.findall(r"(?:^|; )([a-z0-9][a-z0-9-]+): ", msg)
    # a collector that logged its findings as a record rather than a sentence names them inside it
    names = names or list(dict.fromkeys(re.findall(r"'entity': '([a-z0-9][a-z0-9-]+)'", msg)))
    if names:
        label = lambda i: (names_of or {}).get(i, i)
        head = ", ".join(c.esc(label(n)) for n in names[:3])
        rest = names[3:]
        # the rest are a click away rather than "and 2 more" with no way to see them
        more = (f' and <details class="rn-more"><summary>{len(rest)} more</summary>{", ".join(c.esc(label(n)) for n in rest)}</details>'
                if rest else "")
        return f'<span title="{c.esc(msg)}">{len(names)} could not be read: {head}{more}</span>'
    if msg.lstrip().startswith(("{", "[")):
        return '<span>see the run log for details</span>'
    text = msg if len(msg) <= 110 else msg[:107].rstrip() + "…"
    return f'<span title="{c.esc(msg)}">{c.esc(text)}</span>'


def page_status(status, board, generated, inner: bool = False):
    # the regulatory sources run on the 1st, 15th and 25th (pipeline.yml): a date ten days old
    # on one of those rows is the cadence, not a failure, and the table says so
    THRICE = {"fdic", "eba", "edgar", "te", "esef", "fundamentals", "nsm_release"}
    def cadence(src):
        return "1st, 15th, 25th" if src in THRICE else "daily"
    def fresh(r):
        state = {"ok": ("Up to date", "good"), "partial": ("Partly collected", "warn"), "failed": ("Failed", "bad"),
                 "skipped": ("Skipped", "muted")}.get(r["status"], (r["status"], "muted"))
        note = run_note(r["message"], short_of) if r["status"] in ("partial", "failed") else ""
        note_html = f'<div class="small muted">{note}</div>' if note else ""
        return (f'<tr><td><span class="b">{c.esc(SOURCE_LABEL.get(r["source"], r["source"]))}</span>'
                f'{note_html}</td><td>{c.chip(state[0], state[1])}</td>'
                f'<td class="mono muted nowrap">{c.esc(r["finished"][:10])}</td><td class="small muted nowrap">{cadence(r["source"])}</td></tr>')
    short_of = {r["id"]: r["short"] for r in board["rows"]}
    runs = "".join(fresh(r) for r in sorted(status["runs"], key=lambda r: SOURCE_LABEL.get(r["source"], r["source"]))) \
        or '<tr><td colspan="5" class="empty">No runs recorded yet.</td></tr>'
    rows = board["rows"]
    missing = [r for r in rows if not r["asof"]]
    stale = sorted((r for r in rows if r["age_days"] and r["age_days"] > 150), key=lambda r: -r["age_days"])
    lst = lambda xs: ", ".join(f'<a href="../banks/{r["id"]}.html">{c.esc(r["short"])}</a>' for r in xs) or "none"
    # What a treasurer needs from this page: whether today's data is in, how fresh each source is,
    # and which names' figures are old or missing. The pipeline's own diagnostics (source health,
    # the review queue, how the rules did, the data audit) are on the maintainer's page.
    content = f'''<div class="page-head"><div><h1>Data status</h1><div class="lede">How fresh the data is, source by source and name by name.</div></div></div>
<div class="card pad status-card"><h3>Sources</h3>{punctuality(status, generated)}<div class="table-wrap"><table class="plain src-t"><thead><tr><th>Source</th><th>State</th><th>Last run</th><th>Runs</th></tr></thead><tbody>{runs}</tbody></table></div></div>
<div class="card pad status-card"><h3>Names</h3><p class="small">{len(rows) - len(missing)} of {len(rows)} have regulatory figures, {sum(1 for r in rows if r["score"] is not None)} are scored and {sum(1 for r in rows if r.get("rating"))} carry an agency rating.</p>
<p class="small"><span class="b">Figures older than 150 days, oldest first: </span>{lst(stale)}</p><p class="small"><span class="b">No regulatory figures yet: </span>{lst(missing)}</p></div>'''
    return content if inner else c.shell("Status", content, "status", "../", generated)


def page_maintainer(status, board, generated) -> str:
    """The pipeline's own diagnostics, for whoever keeps it running: which sources are collecting,
    the review queue and the documents behind it, how the rules agreed with the reviewer, and what
    is held for every name. Not in the navigation; the Data status page is the public view."""
    content = ('<div class="page-head"><div><h1>Maintainer</h1><div class="lede">The pipeline\'s diagnostics. '
               'Not part of the product; the public view is <a href="index.html#status">Data status</a>.</div></div></div>'
               + health_card() + documents_card(status) + learning_card(status) + audit_card())
    return c.shell("Maintainer", content, "", "../", generated)


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


# One ramp for a rating everywhere on the site, in components. Five buckets of navy and blue put
# almost every covered bank in the same one or two shades: 120 of the 130 rated names sit between
# AAA and A-, so the grid was a wall of blue on a page whose whole job is telling them apart.
grade_colour = c.grade_colour
LETTER_GRADES = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC"]


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


def _at_year_ends(steps, first_year: int, last_year: int) -> list[float]:
    """A step series read at each year end, so a sparkline's x axis is time rather than event count."""
    out, i, cur = [], 0, None
    for y in range(first_year, last_year + 1):
        end = f"{y}-12-31"
        while i < len(steps) and steps[i][0] <= end:
            cur = steps[i][1]; i += 1
        out.append(cur)
    while out and out[0] is None:
        out.pop(0)
    return [v for v in out if v is not None]


def grade_trend(r) -> str:
    """The composite grade's own path, from the register's action log rather than our snapshots.

    This column used to plot the composite on each daily build. Snapshots began four days before
    anyone looked at it, so every row on the page carried the same flat line and the same "4d".
    The register holds eleven years of actions, so the line is now the real one.
    """
    try:
        b = load(f"banks/{r['id']}")
    except Exception:
        b = {}
    h = b.get("rating_history") or {}
    steps = h.get("composite") or []
    if len(steps) >= 2:
        first, last = int(steps[0][0][:4]), datetime.utcnow().year
        pts = _at_year_ends(steps, first, last)
        if len(pts) >= 2:
            net = steps[0][1] - steps[-1][1]              # a lower grade is a stronger rating
            # an average of three moves in thirds of a notch as often as whole ones
            n = f"{abs(net):.1f}".rstrip("0").rstrip(".")
            lab = "flat" if not net else f'{n} notch{"es" if abs(net) != 1 else ""} {"up" if net > 0 else "down"}'
            # the path is history; the outlooks beside it are what is expected next, so the path is told
            # in a neutral voice and never reads as a warning against a positive outlook
            col = c.MUTED
            # the start year is the same for nearly every row, so it belongs on the cell rather
            # than under it, where it would cost a line of height on 150 rows
            return (f'<span class="gpath" title="the composite grade at each year end from '
                    f'{c.esc(steps[0][0][:4])} to today">' + c.spark([-g for g in pts], w=72, h=20)
                    + f'<span class="small" style="color:{col}">{c.esc(lab)}</span></span>')
    # no path to draw: the Last action column already carries the date, so this one stays quiet
    return '<span class="muted">—</span>'


def action_words(title: str) -> tuple[str, str]:
    """A rating action as a short phrase and its tone, from the register's sentence: "Outlook
    positive", "Downgraded", "Positive outlook removed". The tone follows the words, so taking a
    positive outlook away is not counted as good news."""
    t = (title or "").lower()
    term = "Short-term rating" if "short-term" in t else "Rating"
    side = "positive" if "positive" in t else "negative" if "negative" in t else ""
    if "upgrad" in t:
        return "Upgraded", "good"
    if "downgrad" in t:
        return "Downgraded", "warn"
    if "withdr" in t:
        return f"{term} withdrawn", "info"
    if "remov" in t:
        return (f"{side.capitalize()} {'watch' if 'watch' in t else 'outlook'} removed" if side else "Outlook removed"), "info"
    if "watch" in t:
        return (f"On watch {side}" if side else "On watch"), {"positive": "good", "negative": "warn"}.get(side, "info")
    if "outlook" in t and side:
        return f"Outlook {side}", {"positive": "good", "negative": "warn"}[side]
    if "default" in t:
        return "Default", "bad"
    return (title or "")[:80], "info"


def page_ratings(generated, inner: bool = False):
    R = load("ratings")
    rows = R["rows"]
    rated = [r for r in rows if r["grade"] is not None]
    today = datetime.utcnow().date()
    since90 = (today - timedelta(days=90)).isoformat()
    since30 = (today - timedelta(days=30)).isoformat()
    acts_all = R["actions"]
    recent30 = [a for a in acts_all if a["date"] >= since30]
    ups = sum(1 for a in recent30 if action_words(a["title"])[1] == "good")
    downs = sum(1 for a in recent30 if action_words(a["title"])[1] in ("warn", "bad"))
    moved = {a["id"] for a in acts_all if a["date"] >= since90}
    # distribution by composite grade: the filter control for the grid
    GR = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC"]
    counts = {i: 0 for i in range(1, 18)}
    for r in rated:
        counts[max(1, min(17, int(r["grade"] + 0.5)))] += 1
    mx = max(counts.values()) or 1
    hist = "".join(f'<button class="gbar gfilter" data-grade="{i}" title="{GR[i-1]}: {counts[i]}" {"disabled" if not counts[i] else ""}><span class="gcount mono">{counts[i] or ""}</span><i style="height:{max(3, counts[i] / mx * 64):.0f}px;background:{grade_colour(i)}"></i><span class="glabel">{GR[i-1]}</span></button>' for i in range(1, 14))
    hist += f'<button class="gbar gfilter" data-grade="nr" title="Unrated: {len(rows) - len(rated)}"><span class="gcount mono">{len(rows) - len(rated)}</span><i style="height:{max(3, (len(rows) - len(rated)) / mx * 64):.0f}px;background:#dfe5eb"></i><span class="glabel">NR</span></button>'
    # a group takes the colour of a rating in the middle of it, so the tiles, the bars and the
    # grid are all reading off the same ramp
    # An average grade sits between notches (4.33 is AA- by a third); every count here takes the
    # notch it rounds to, the one its letter shows and its bar counts it under, so a name shown as
    # AA- is never counted in the A range.
    def notch(g):
        return max(1, min(17, int(g + 0.5)))
    def group(g):
        n = notch(g)
        return "AA- and above" if n <= 4 else "A range" if n <= 7 else "BBB range" if n <= 10 else "Below BBB-"
    band_tiles = [(k, sum(1 for r in rated if group(r["grade"]) == k), grade_colour(m))
                  for k, m in (("AA- and above", 3), ("A range", 6), ("BBB range", 9), ("Below BBB-", 13))] + [
                  ("Unrated", len(rows) - len(rated), "#6c757d")]
    tiles = "".join(f'<button class="rtile bfilter" data-band="{k}"><div class="rtile-n" style="color:{col}">{n}</div><div class="rtile-l">{c.esc(k)}</div></button>' for k, n, col in band_tiles)
    tiles += f'<a class="rtile" href="#actions"><div class="rtile-n"><span style="color:#1e7a3a">{ups}▲</span> <span style="color:#b04632">{downs}▼</span></div><div class="rtile-l">Moves, 30 days</div></a>'
    # the grid: one row per entity, the average, the weakest and the outlooks across the three
    def band_key(g):
        return "Unrated" if g is None else group(g)
    DOT = ('<span class="chip-dot" title="one of the three agencies moved this rating within 90 days: an upgrade, '
           'downgrade, outlook or watch change, not an affirmation"></span> ')
    def letter_cell(letter, grade, sub=""):
        if not letter:
            return '<td class="rc rc-na">—</td>'
        col = grade_colour(grade)
        under = f'<span class="rc-sub small muted">{sub}</span>' if sub else ""
        return (f'<td class="rc" style="--g:{col}"><span class="band mono" style="background:{col};color:{c.on_colour(col)}">{c.esc(letter)}</span>'
                f'{under}</td>')
    trs = "".join(
        f'<tr data-id="{c.esc(r["id"])}" data-region="{c.esc(r["region"])}" data-name="{c.esc(r["short"].lower())} {c.esc(r["name"].lower())}" data-score="{100 - (r["grade"] or 99)}" '
        f'data-grade="{max(1, min(17, int(r["grade"] + 0.5))) if r["grade"] is not None else "nr"}" data-band="{band_key(r["grade"])}" data-moved="{1 if r["id"] in moved else 0}">'
        f'<td><a class="b" href="../banks/{c.esc(r["id"])}.html">{c.esc(r["short"])}</a><div class="small muted">{c.esc(COUNTRY.get(r["country"], r["country"]))}<span class="ty"> · {c.esc(TYPE_LABEL.get(r["type"], r["type"]))}</span></div></td>'
        + letter_cell(r["composite"] or ("NR" if r["grade"] is None else ""), r["grade"], f'{c.esc(of_three(r["n"]))}' if r["n"] else "")
        + letter_cell(r["worst"], r.get("worst_grade"))
        + f'<td class="rc-tones">{tone_glyphs(r.get("tones") or []) if r["n"] else "—"}</td>'
        + f'<td class="small">{DOT if r["id"] in moved else ""}<span class="muted tnum">{c.esc(r["last_action"] or "—")}</span></td><td>{grade_trend(r)}</td></tr>'
        for r in sorted(rows, key=lambda r: (r["grade"] is None, r["grade"] or 99, r["short"])))
    # the reader's own list first after All: it is the set a treasurer opens this page to check
    regions = [("all", "All"), ("mine", "My counterparties"), ("uk", "UK"), ("eu", "EU"), ("us_ch", "US and Switzerland"), ("aus_can", "Australia and Canada"), ("asia", "Asia"), ("gulf", "Gulf"), ("watch", "Watching")]
    filters = "".join(f'<button class="filter{" active" if k == "all" else ""}" data-region="{k}">{c.esc(l)}</button>' for k, l in regions)
    tone = {"bad": "bad", "warn": "warn", "good": "good", "info": "muted"}
    def ract(a):
        words, tone_ = action_words(a["title"])
        label = {"good": "positive", "warn": "negative", "bad": "adverse"}.get(tone_, "neutral")
        return (f'<div class="ract"><span class="mono muted">{a["date"]}</span><a class="b" href="../banks/{c.esc(a["id"])}.html">{c.esc(a["short"])}</a>'
                f'<span title="{c.esc(a["title"])}">{c.esc(words)}</span>{c.chip(label, tone.get(tone_, "muted"))}</div>')
    acts = "".join(ract(a) for a in acts_all[:30]) or '<div class="empty">No rating actions other than affirmations in the last 90 days.</div>'
    content = f'''<div class="page-head"><div><h1>Ratings</h1><div class="lede">The three main agencies' long-term ratings for every name, on one scale, from the ESMA register. Click a tile, bar or region to filter.</div></div></div>
<div class="rtiles rtiles-f">{tiles}</div>
<div class="card rgrid-card"><div class="toolbar rg-tools"><div class="filters">{filters}<button class="filter" data-region="moved">Moved in 90 days</button></div><input id="q" class="search" placeholder="Search"><span class="small muted" id="rg-count"></span></div>
<div class="rg-hist"><span class="small muted">Average grade{c.info("rating")}</span>{hist}<button class="filter small gclear" hidden>Clear grade</button></div>
<div class="table-wrap"><table id="board" class="plain rgrid"><thead><tr><th data-sort="name">Entity</th><th data-sort="score">Average{c.info("composite")}</th><th>Weakest</th><th>Outlooks</th><th>Last action</th><th title="the average grade at each year end, from the register\'s own action log">Path since 2015</th></tr></thead><tbody>{trs}</tbody></table></div><div class="pager" id="rg-more" data-step="40"></div>
<div class="table-foot"><span>Average and weakest of the three main agencies' long-term ratings, on one scale. Outlooks, one mark per agency: ▲ positive · ▼ negative · ◆ watch · ▶ stable. An orange dot marks a move in the last 90 days.</span></div></div>
<div class="rgrid2"><div class="card pad" id="actions"><h3>Latest rating actions <span class="muted small">· 90 days, affirmations excluded</span></h3><div class="racts" id="racts">{acts}</div><div class="pager" id="ract-more" data-step="12"></div></div>
</div>'''
    return content if inner else c.shell("Ratings", content, "ratings", "../", generated)

WT_LINE = (f'<div class="wt-line" id="wt-line"><span class="wt-l">Weightings{c.info("score")}</span>'
           '<span class="wt-vals" id="wt-vals"><span class="sk"></span></span></div>')

# A name's detail still opens over the page: it is a glance at one name from wherever it is listed.
# Weightings and Choose names were dialogs too; they are pages of their own now (strategy pages below).
TOOL_DIALOGS = '<dialog id="pol-modal" class="pol-modal"></dialog>'


def strategy_pages() -> str:
    """Weightings and Choose names: the first two of the three steps, as pages on the tool beside
    Start here rather than dialogs over it. A reader working through the steps stays on the page,
    and the navigation marks where they are like any other page."""
    return ('<section class="panel" data-panel="weights">'
            + panel_head("Build your strategy", "Weightings",
                         "How much each part of the score counts. Move a slider and every score on the site follows, on this device only; the six are scaled to add up to 100%.")
            + '<div class="card pad wt-page" id="pol-weights"></div></section>'
            '<section class="panel" data-panel="universe">'
            + panel_head("Build your strategy", "Choose names",
                         "Every covered bank and building society. Sort on any column, open a name for its detail, and add the ones you accept; the star follows a name without adding it.")
            + '<div class="uni-page">' + UNIVERSE_PANEL + '</div></section>')


def strategy_panel() -> str:
    """Build your strategy: the three steps, numbered the way PWLBreports numbers its passes, each
    with its one action on the right and a line saying where the reader has got to. Step one leads
    to the Weightings page, step two to Choose names, step three to the list. The status lines are
    painted by the list's own script."""
    def step(n, title, text, body, act):
        return (f'<div class="step" id="st-{n}"><span class="k">0{n}</span><div><h3>{title}</h3><p>{text}</p>{body}</div>'
                f'<div class="step-act">{act}</div></div>')
    return ('<section class="panel active" data-panel="strategy">'
            + panel_head("Build your strategy", "Three steps to a counterparty policy",
                         "Set how the score is made, choose the names you accept, and say how long you would lend to each.")
            + '<div class="steps">'
            + step(1, "Set your weightings", "Decide how much each part of the score counts. The published weights apply until you change them.",
                   "", '<button class="filter" id="wt-change" type="button">Change weightings</button><span class="step-now" id="st-weights"></span>')
            + step(2, "Choose your names", "Every covered bank and building society on one table. Add the ones you accept.",
                   "", '<button class="filter filter-blue uni-open" type="button">Choose from every covered name</button><span class="step-now" id="st-names"></span>')
            + step(3, "Set tenors, then watch", "Give each name a tenor. The list is re-checked every night, and Alternatives finds names as strong as your weakest.",
                   "", '<a class="filter" href="#policy">Go to your counterparties &rarr;</a><span class="step-now" id="st-tenors"></span>')
            + '</div></section>')


def panel_head(kicker: str, title: str, lede: str) -> str:
    """A page's title and one line on what it is for. The kicker (the pathway it sits on) is no
    longer drawn: the navigation above already says it."""
    return (f'<div class="ph"><div><h2>{c.esc(title)}</h2>'
            f'<span class="lede">{lede}</span></div></div>')


def _panel_content(html: str, kicker: str = "", title: str = "") -> str:
    """A page's own content, with its page-head turned into a panel head: the pathway it sits on,
    the name the sidebar gives it, and the page's own lede beneath."""
    m = re.search(r'<div class="page-head">.*?<div class="lede">(.*?)</div>.*?</div></div>', html, re.S)
    if not m:
        return html
    head = panel_head(kicker, title, m.group(1)) if title else f'<p class="small muted panel-lede">{m.group(1)}</p>'
    return head + html[m.end():]


UNIVERSE_PANEL = f"""<div class="uni-tools">
<div class="uni-row1">
  <label class="uni-search">{c.ico("search", 16, c.MUTED)}<input id="uni-q" type="search" placeholder="Search name, country or LEI" autocomplete="off" aria-label="Search the names"></label>
  <div class="uni-addat"><label for="uni-tenor">Add names at</label><select id="uni-tenor" title="The tenor the Add buttons in this table use"></select><span class="uni-other" id="uni-other" hidden><input id="uni-other-n" type="number" min="1" max="3650" step="1" value="9" aria-label="How many"><select id="uni-other-u" aria-label="Unit"><option value="1">days</option><option value="7">weeks</option><option value="30.4167" selected>months</option><option value="365">years</option></select></span></div>
</div>
<button class="filter uni-ftoggle" id="uni-ftoggle" type="button" aria-expanded="false" aria-controls="uni-row2">Filters</button>
<div class="uni-row2" id="uni-row2">
  <div class="filters uni-chips" id="uni-chips"><button class="filter" data-uf="top" type="button" title="the five strongest published standings today">Top standing today</button><button class="filter" data-uf="mine" type="button">In my list</button><button class="filter" data-uf="watch" type="button">Watching</button></div>
  <span class="uni-div" aria-hidden="true"></span>
  <select id="uni-region" aria-label="Region"><option value="">Every region</option></select>
  <select id="uni-type" aria-label="Type"><option value="">Every type</option></select>
  <select id="uni-band" aria-label="Band"><option value="">Any band</option><option>A</option><option>B</option><option>C</option><option>D</option><option>E</option></select>
  <label class="uni-chk"><input type="checkbox" id="uni-scored"> Scored only</label>
  <span class="uni-cols"><button class="filter" id="uni-cols-btn" type="button" aria-expanded="false" aria-controls="uni-cols-menu">Columns</button><div class="uni-cols-menu" id="uni-cols-menu" hidden></div></span>
  <span class="uni-count small muted" id="uni-count"></span>
</div>
</div>
<div class="table-wrap scrollbox"><table class="plain uni" id="uni-table"><thead><tr>
  <th class="uni-st" title="watching"></th><th class="uni-add"><span class="sr-only">Add</span></th><th data-sort="short">Name</th><th data-sort="country">Country</th><th data-sort="score" class="num">Score{c.info("score")}</th>
  <th data-sort="rating_grade">Agency rating{c.info("composite")}</th><th data-sort="cet1" class="num">CET1{c.info("cet1_ratio")}</th><th data-sort="leverage" class="num">Lev{c.info("leverage_ratio")}</th>
  <th data-sort="lcr" class="num">LCR{c.info("lcr")}</th><th data-sort="nsfr" class="num">NSFR{c.info("nsfr")}</th>
  <th data-sort="asof" class="uni-fig">Figures{c.info("as_at")}</th></tr></thead><tbody id="uni-body"><tr class="sk-tr"><td colspan="11"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr><tr class="sk-tr"><td colspan="9"><span class="sk"></span></td></tr></tbody></table></div><div class="tfoot small muted" id="uni-count2"></div>
"""


def home_panels(board, status, generated) -> dict[str, str]:
    """The two heavy panels of the home page, as fragments fetched when their tab is first used.

    Four pages became three tabs, and the two nobody has clicked were still 426 KB of the home
    page's 441 KB: every rating of every name, and every event, parsed into the document before
    anything was drawn. They are written here instead and fetched on demand.
    """
    out = {"analysis": _panel_content(compare_content(), "Compare", "Analysis")}
    # a tab that is held back publishes nothing: the fragment is not written either, so the grid
    # and the feed are not sitting at a guessable URL for anyone who looks
    if "ratings" not in HOME_TABS_HIDDEN:
        out["ratings"] = _panel_content(page_ratings(generated, inner=True), "Compare", "Ratings")
    return out


def page_tool(board, status, generated):
    """The tool, one page: every pathway is a panel, and the sidebar is the way between them.

    The board, the bank navigator, the ratings grid and the events feed were four pages showing
    slices of one universe. They are panels here, so nothing is lost and nothing is a journey.
    The tab strip that used to switch them is still in the document, because the panel loader
    and every link into the page speak to it, but it is not drawn: the pathways down the side
    say the same thing in the platform's own words.
    """
    v = c.stamp(generated)
    content = (
        '<div class="pol-shared" id="pol-shared" hidden><span></span><button class="filter" id="pol-use-shared">Use it</button><button class="filter" id="pol-keep-mine">Keep mine</button></div>'
        '<div class="card tabs-card" id="browse">'
        '<div class="tabs" role="tablist">'
        '<button class="tab active" data-tab="strategy">Build your strategy</button>'
        '<button class="tab" data-tab="weights">Weightings</button>'
        '<button class="tab" data-tab="universe">Choose names</button>'
        '<button class="tab" data-tab="policy">Your counterparties<span class="tab-n" id="tn-policy"></span></button>'
        '<button class="tab" data-tab="likeforlike">Alternatives<span class="tab-n" id="tn-ll"></span></button>'
        '<button class="tab" data-tab="analysis">Analysis</button>'
        '<button class="tab" data-tab="ratings">Ratings</button></div>'
        + strategy_panel()
        + strategy_pages()
        + '<section class="panel" data-panel="policy">'
        + panel_head("Monitor", "Your counterparties",
                     "Every name on your list, re-checked each night, with what has moved since you approved it.")
        + '<div id="policy-body"><div class="sk-cards" aria-hidden="true">' + '<span class="sk"></span>' * 4 + '</div></div>'
        '<div class="pol-share" id="pol-share" hidden><button class="filter" id="pol-clear">Clear all</button></div></section>'
        '<section class="panel" data-panel="likeforlike">'
        + panel_head("Compare", "Alternatives",
                     "At each tenor, the covered names at least as strong as the weakest you already accept: same or better band, ratings and score, and no widening market signal.")
        + '<div id="pol-ll"></div></section>'
        f'<section class="panel" data-panel="analysis" data-src="data/panels/analysis.html?v={v}" data-js="assets/compare.js?v={v}"></section>'
        f'<section class="panel" data-panel="ratings" data-src="data/panels/ratings.html?v={v}"></section>'
        '</div>'
        # The panel to open on is decided here, before the first paint, rather than after the scripts
        # have loaded: the address's own panel, or the list for a reader who holds one. Done later, the
        # page painted Start here and then jumped to the list.
        '<script>(function(){try{var h=location.hash.slice(1).split("&")[0],c=document.getElementById("browse");'
        'if(!h){var p=JSON.parse(localStorage.getItem("counterparty.policy")||"[]");if(p&&p.length)h="policy"}'
        'var q0=h&&c.querySelector(\'.panel[data-panel="\'+h+\'"]\');if(!q0||q0.dataset.src)return;'
        'c.querySelectorAll(".tab").forEach(function(t){t.classList.toggle("active",t.dataset.tab===h)});'
        'c.querySelectorAll(".panel").forEach(function(q){q.classList.toggle("active",q.dataset.panel===h)})}catch(e){}})()</script>'
        + TOOL_DIALOGS)
    # the list is drawn from this file, and asking for it only after two scripts have been
    # fetched and run is a round trip the reader spends looking at an empty box
    return (c.shell("Your counterparties", content, "strategy", "../", generated,
                    preload=("data/policy.json",), body_class="tool")
            .replace(f'<script src="../assets/app.js?v={v}"></script>',
                     f'<script src="../assets/app.js?v={v}"></script>'
                     f'<script src="../assets/policy.js?v={v}"></script>')
            .replace('<body class="tool">', '<body class="tool" data-root="../">'))


page_home = page_tool


BAND_COLOUR = {"A": "#4cb583", "B": "#5695d1", "C": "#e8c547", "D": "#e8974a", "E": "#e0776a"}

LANDING_SCRIPT = """
(function(){
  try{var p=JSON.parse(localStorage.getItem('counterparty.policy')||'[]');
    if(p&&p.length){var r=document.getElementById('returning');document.getElementById('returning-n').textContent='Your list holds '+p.length+' name'+(p.length===1?'':'s')+'.';r.hidden=false}}catch(e){}
  var rv=document.querySelectorAll('.rv');
  if(!('IntersectionObserver' in window)||matchMedia('(prefers-reduced-motion: reduce)').matches){rv.forEach(function(el){el.classList.add('in')});return}
  var io=new IntersectionObserver(function(es){es.forEach(function(x){if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}})},{rootMargin:'0px 0px -8% 0px'});
  rv.forEach(function(el){io.observe(el)});
})();
"""


def page_landing(board, status, generated):
    """The page that explains the tool, in the frame PWLBreports uses for the same job: one
    question, the three pathways, how it works, what it rests on, and the way in. Static, dark,
    no webfont, no script but a reveal and a line for the reader who has been here before."""
    rows = board["rows"]
    n = len(rows)
    rated = sum(1 for r in rows if r.get("rating"))
    scored = sum(1 for r in rows if r.get("score") is not None)
    bands = {k: sum(1 for r in rows if r.get("band") == k) for k in "ABCDE"}
    total = sum(bands.values()) or 1
    bar = "".join(f'<i style="width:{bands[k] / total * 100:.1f}%;background:{BAND_COLOUR[k]}" title="Band {k}: {bands[k]}"></i>' for k in "ABCDE" if bands[k])
    leg = "".join(f'<span><i style="background:{BAND_COLOUR[k]}"></i>{k} &middot; {bands[k]}</span>' for k in "ABCDE")
    built = generated[:10]
    P = c.PRODUCT[0] + c.PRODUCT[1]
    T = c.TOOL
    arrow = '<span class="arw">&rarr;</span>'
    lock = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>')
    return (f'<!doctype html>\n<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{P} · PWLBtoday</title>\n'
            '<meta name="description" content="Who can you deal with, and for how long? Every covered bank and building society scored from its regulatory filings and its agency ratings, with the market&rsquo;s own signal, against the weightings you choose. Build a counterparty policy, watch every name on it, and find the next one. From PWLBtoday.">\n'
            '<meta name="color-scheme" content="dark">\n'
            '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E%3Ccircle cx=\'16\' cy=\'16\' r=\'9\' fill=\'%23fd7e14\'/%3E%3C/svg%3E">\n'
            # the reveal hides sections only once a script is known to run, so a page with scripts off,
            # or printed, is never left faded
            f'<link rel="stylesheet" href="assets/landing.css?v={c.stamp(generated)}">\n'
            '<script>document.documentElement.classList.add("js")</script>\n</head><body>\n'
            f'<div class="masthead"><div class="wrap"><a class="brand" href="index.html"><b>{c.PRODUCT[0]}</b>{c.PRODUCT[1]}</a><span class="sp"></span>'
            f'<a class="mini" href="#paths">Three pathways</a><a class="mini" href="#how">How it works</a><a class="mini" href="#rests">What it rests on</a><a class="mini" href="{T}">Open the tool &rarr;</a></div></div>\n'
            '<header class="hero"><div class="wrap"><div class="herogrid"><div>\n'
            '<h1 class="rv">Who can you deal with,<br><span class="em">and for how long</span>?</h1>\n'
            '<p class="sub rv">Every covered bank and building society, scored from its regulatory filings and agency ratings. Build a counterparty policy, watch every name on it, and find the next one.</p>\n'
            f'<div class="cta rv"><a class="btn" href="{T}">Open {P} {arrow}</a><a class="btn ghost" href="#paths">See the three pathways</a></div>\n'
            f'<p class="freeline rv">{lock}Your list stays in your browser. Nothing is sent anywhere.</p>\n'
            f'<div class="returning" id="returning" hidden><span>Welcome back. <b id="returning-n"></b></span><a href="{T}#policy">Go straight to your counterparties &rarr;</a></div>\n'
            '</div>\n'
            f'<div class="herocard rv"><div class="hc-k"><span class="live"></span>What it holds today &middot; built {c.esc(built)}</div>\n'
            '<p class="hc-t">Every name a UK treasury desk would deal with, read from the public record every morning.</p>\n'
            f'<div class="hc-stats"><div class="hc-stat"><b>{n}</b><span>names covered</span></div><div class="hc-stat"><b>{rated}</b><span>with an agency rating</span></div>'
            f'<div class="hc-stat"><b>{scored}</b><span>scored</span></div><div class="hc-stat"><b>{bands["A"]}</b><span>in band A</span></div></div>\n'
            f'<div class="hc-bands"><div class="bar">{bar}</div><div class="hc-leg">{leg}</div></div></div>\n'
            '</div></div></header>\n\n'
            '<section id="paths" class="path"><div class="wrap">\n<p class="eyebrow rv">Three pathways</p>\n'
            '<h2 class="rv">Build it. <span class="em">Watch it.</span> Find the next name.</h2>\n'
            '<p class="lede rv">A counterparty list is built once, checked every day and extended now and then. The tool follows that order.</p>\n'
            '<div class="cards">\n'
            f'<a class="card rv" href="{T}#strategy"><span class="n">01 &middot; Build your strategy</span><h3>Three steps to a policy</h3><p>Set how the score is made, choose the names you accept, and say how long you would lend to each.</p>'
            '<ul><li>Weightings you can change, for you alone</li><li>Every covered name on one table</li><li>Any tenor, from a day to ten years</li></ul><span class="go">Start here &rarr;</span></a>\n'
            f'<a class="card rv" href="{T}#policy"><span class="n">02 &middot; Monitor your counterparties</span><h3>Re-checked every night</h3><p>Every name on your list, against its filings, its ratings and the market, with what has moved since you approved it.</p>'
            '<ul><li>What changed, flagged on the card</li><li>Names you are only watching, beneath</li><li>Rating actions and new filings, on each name</li></ul><span class="go">Open your counterparties &rarr;</span></a>\n'
            f'<a class="card rv" href="{T}#likeforlike"><span class="n">03 &middot; Compare</span><h3>The next name, and the whole universe</h3><p>Alternatives at least as strong as your weakest at each tenor, any names side by side, and the universe by rating.</p>'
            '<ul><li>Alternatives, tenor by tenor</li><li>Analysis: any names, any ratio, over time</li><li>Ratings: the average and the weakest of the three</li></ul><span class="go">Compare &rarr;</span></a>\n'
            '</div></div></section>\n\n<div class="wrap"><div class="rule"></div></div>\n\n'
            '<section id="how" class="honest"><div class="wrap">\n<p class="eyebrow rv">How it works</p>\n'
            '<h2 class="rv">Read every morning, and nothing typed by hand.</h2>\n'
            '<p class="lede rv">One published method, applied the same way to every name. Every figure carries its source and its date.</p>\n'
            '<div class="steps">\n'
            "<div class=\"step rv\"><span class=\"k\">01</span><div><h3>The public record is read</h3></div><p>Pillar 3 reports and regulatory returns for capital and liquidity, the ESMA register for the agencies' ratings, and traded prices for the market signal.</p></div>\n"
            "<div class=\"step rv\"><span class=\"k\">02</span><div><h3>Every name is scored</h3></div><p>The agency rating anchors the score and the bank's own ratios make up the rest, weighed by the published method or by your own weightings. A name without a rating or current figures is not scored, and says so.</p></div>\n"
            '<div class="step rv"><span class="k">03</span><div><h3>Your list is checked against it</h3></div><p>Each night every name you hold is read again. A rating that moved, a ratio that fell or a market signal that turned is marked on its card.</p></div>\n'
            '<div class="step rv"><span class="k">04</span><div><h3>The next name is found</h3></div><p>Alternatives finds names at least as strong as your weakest at each tenor. Analysis puts any names side by side, and Ratings lays out the whole universe.</p></div>\n'
            '</div></div></section>\n\n'
            '<section id="rests"><div class="wrap">\n<p class="eyebrow rv">What it rests on</p>\n'
            '<h2 class="rv">Public data, one method, every date on the page.</h2>\n<div class="cards cards-4">\n'
            "<div class=\"card rv\"><span class=\"n\">Regulatory filings</span><h3>The banks' own figures</h3><p>CET1, leverage, liquidity and funding ratios from Pillar 3 reports, the EBA and the FDIC, each checked against the figures around it.</p></div>\n"
            "<div class=\"card rv\"><span class=\"n\">Agency ratings</span><h3>The average and the weakest of three</h3><p>The long-term ratings of Fitch, S&amp;P and Moody's on one scale, from the ESMA register every day.</p></div>\n"
            '<div class="card rv"><span class="n">Market</span><h3>What the market says</h3><p>CDS, bond yields and the share price, as a signal worth a few points either way at most.</p></div>\n'
            "<div class=\"card rv\"><span class=\"n\">Not advice</span><h3>Information, and a published method</h3><p>Scores follow the published method and can be wrong. Nothing here is a recommendation or stands in for your own policy.</p></div>\n"
            '</div></div></section>\n\n'
            '<section class="close"><div class="wrap">\n<h2 class="rv">Open the tool and build your list.</h2>\n'
            f'<div class="cta rv"><a class="btn" href="{T}">Open {P} {arrow}</a></div>\n'
            '<p class="claims rv">Your list and your weightings stay in this browser and nowhere else. Information, not advice: check every figure against its source before it reaches a committee.</p>\n'
            '</div></section>\n\n'
            f'<footer><div class="wrap"><span><b>{c.PRODUCT[0]}</b>{c.PRODUCT[1]} &middot; from PWLBtoday</span><span class="sp"></span><a href="admin/index.html#method">Method</a><a href="admin/index.html#status">Data status</a><a href="{T}">Open the tool</a></div></footer>\n'
            f'<script>{LANDING_SCRIPT}</script>\n</body></html>')


def page_admin(status, board, generated):
    """Method, coverage and data status behind one door.

    None of it is the daily job: it is how the score is built, what is held for every name and
    what ran last night. Kept together so it can be shown to someone deciding whether to trust
    the thing, and taken away without disturbing the pages that do the work.
    """
    # The navigation names the three pages, so the tab strip steps aside here as it does on the
    # tool, and each page carries its own heading.
    content = ('<div class="card tabs-card"><div class="tabs" role="tablist">'
               '<button class="tab active" data-tab="method">Method</button>'
               '<button class="tab" data-tab="coverage">Coverage</button>'
               '<button class="tab" data-tab="status">Data status</button></div>'
               f'<section class="panel active" data-panel="method">{_panel_content(page_method(generated, inner=True), "Reference", "Method")}</section>'
               f'<section class="panel" data-panel="coverage">{_panel_content(page_coverage(generated, inner=True), "Reference", "Coverage")}</section>'
               f'<section class="panel" data-panel="status">{_panel_content(page_status(status, board, generated, inner=True), "Reference", "Data status")}</section>'
               '</div>')
    return c.shell("Method", content, "admin", "../", generated, body_class="tool")


def page_gone(title: str, generated: str, target: str = "../index.html", nav: str = "home") -> str:
    """A page that has been folded into another; its address still resolves and carries the reader
    on, so a bookmark or a link in someone's paper trail does not break."""
    content = (f'<div class="page-head"><div><h1>{c.esc(title)}</h1>'
               f'<div class="lede">This view now sits on the page it belongs to. Taking you there.</div>'
               f'</div></div><meta http-equiv="refresh" content="0; url={target}">'
               f'<p><a class="filter" href="{target}">Continue</a></p>')
    return c.shell(title, content, nav, "../", generated)


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


def page_coverage(generated, inner: bool = False):
    A = load("audit")["rows"]
    n = len(A)

    def cnt(fn):
        return sum(1 for a in A if fn(a))
    tiles = "".join(f'<div class="rtile"><div class="rtile-n">{v}</div><div class="rtile-l">{c.esc(l)}</div></div>' for v, l in [
        (n, "entities"), (cnt(lambda a: a["score"] is not None), "scored"), (cnt(lambda a: a["agencies"]), "rated"),
        (cnt(lambda a: a["years"] >= 5), "5+ years of ratios"), (cnt(lambda a: a["metrics"]["lcr"]["n"]), "with LCR"),
        (cnt(lambda a: a["metrics"]["npl_ratio"]["n"]), "with asset quality"), (cnt(lambda a: a["price_days"]), "with a share price"),
        (cnt(lambda a: a["cds_days"]), "with CDS"), (cnt(lambda a: a["bonds"]), "with bonds")])
    trs = []
    for a in sorted(A, key=lambda a: (-(a["score"] or -1), a["short"])):
        band = c.chip(c.esc(a["band"] or "—"), "muted") if a["band"] else ""
        rating = f'<b style="color:{grade_colour(LETTER_GRADES.index(a["rating"]) + 1 if a["rating"] in LETTER_GRADES else None)}">{c.esc(a["rating"])}</b><div class="muted small">{a["agencies"]} of 3</div>' if a["agencies"] else '<span class="muted">unrated</span>'
        cells = "".join(_depth_cell(a["metrics"][m]) for m, _ in AUDIT_COLS)
        score = a["score"] if a["score"] is not None else -1
        shown_score = f"{a['score']:.0f}" if a["score"] is not None else "—"
        # the source a reader knows, not the adapter that read it
        sources = ", ".join(dict.fromkeys({"eba": "EBA", "eba_te": "EBA", "esef": "annual accounts", "nsm_release": "results",
                                           "pillar3": "Pillar 3", "fdic": "FDIC", "edgar": "SEC", "fundamentals": "accounts",
                                           "te": "EBA"}.get(x, x) for x in a["sources"]))
        trs.append(f'<tr data-id="{c.esc(a["id"])}" data-name="{c.esc(a["short"].lower())}" data-region="{c.esc(a["region"])}" data-score="{score}">'
                   f'<td class="b"><a href="../banks/{c.esc(a["id"])}.html">{c.esc(a["short"])}</a><div class="muted small nowrap">{c.esc(REGION_LABEL.get(a["region"], a["region"]))}<span class="ty"> · {c.esc(TYPE_LABEL.get(a["type"], a["type"]))}</span></div></td>'
                   f'<td class="nowrap cov-sc" data-v="{score}">{shown_score} {band}</td>'
                   f'<td data-v="{a["agencies"]}">{rating}</td>'
                   f'<td class="cov-yr" data-v="{a["years"]}" title="{c.esc(sources)}">{a["years"] or "—"}</td>{cells}</tr>')
    regions = [("all", "All"), ("uk", "UK"), ("eu", "EU"), ("us_ch", "US and Switzerland"), ("aus_can", "Australia and Canada"), ("asia", "Asia"), ("gulf", "Gulf"), ("watch", "Watching")]
    filters = "".join(f'<button class="filter{" active" if k == "all" else ""}" data-region="{k}">{c.esc(l)}</button>' for k, l in regions)
    heads = "".join(f'<th class="num" data-sort="col" title="periods held and the years they span">{c.esc(l)}</th>' for _, l in AUDIT_COLS)
    body = "".join(trs)
    content = (
        '<div class="page-head"><div><h1>Coverage</h1><div class="lede">What is held for every name. In each ratio column, '
        'the number is how many reporting dates are held, and beneath it the first and last year.</div></div></div>'
        f'<div class="rtiles rtiles-cov">{tiles}</div>'
        f'<div class="card" style="margin-top:16px;padding:14px 16px"><div class="toolbar rg-tools"><div class="filters">{filters}</div><input id="q" class="search" placeholder="Search"></div>'
        '<div class="table-wrap"><table id="board" class="plain coverage"><thead><tr><th data-sort="name">Entity</th><th data-sort="score">Score</th>'
        '<th data-sort="col">Rating</th>'
        f'<th class="num" data-sort="col" title="span of the CET1 history in years; hover a cell for its sources">Years</th>{heads}</tr></thead><tbody>{body}</tbody></table></div><div class="pager" id="cov-more" data-step="40"></div>'
        '<div class="table-foot"><span>Shading: light under 4 reporting dates, mid under 12, dark 12 and over. The rating is the average of the three main agencies and how many of them rate the name.</span></div></div>')
    return content if inner else c.shell("Coverage", content, "coverage", "../", generated)


_WS = re.compile(r">\s+<")


def _write(path, html: str) -> None:
    """Write a page with the whitespace between tags collapsed (there is no <pre> content on the site)."""
    path.write_text(_WS.sub("><", html))


def compare_content() -> str:
    sets = [("all", "Everyone"), ("uk_large", "UK majors"), ("uk_mid", "UK mid-sized"), ("uk_small", "UK small banks"), ("uk_bs", "Building societies"),
            ("eu_large", "EU and Nordic"), ("us", "US"), ("ch", "Switzerland"), ("aus", "Australia"), ("can", "Canada"), ("asia", "Asia"), ("gulf", "Gulf"),
            ("watch", "Watching"), ("policy", "My counterparties")]
    chips = "".join(f'<button class="filter cp-set" data-set="{k}">{c.esc(l)}<span class="cnt"></span></button>' for k, l in sets)
    def panel(pid, title, sub, wide: bool = False):
        return (f'<section class="panel-c{" wide" if wide else ""}" id="p-{pid}"><div class="pc-head"><h3>{c.esc(title)} <span class="muted small">{c.esc(sub)}</span></h3>'
                f'<button class="pc-x" data-panel="{pid}" title="Expand or restore" aria-label="Expand {c.esc(title)}">⤢</button></div>'
                f'<div class="pc-body cp-chart" id="c-{pid}"><div class="sk-rows" aria-hidden="true">'
                + '<span class="sk"></span>' * 5 + '</div></div></section>')
    head = panel_head("Compare", "Analysis", "Pick a peer set and a measure: where the names stand today, where the measure has been, and how their order has changed. Pin up to six names to follow them through every view.")
    return head + f'''<div class="card cp-card"><div class="cp-tools">
<div class="filters" id="cp-sets">{chips}</div>
<select id="cp-set-sel" class="cp-set-sel" aria-label="Peer set">{"".join(f'<option value="{k}">{c.esc(l)}</option>' for k, l in sets)}</select>
<div class="cp-row"><label class="small muted">Measure <select id="cp-metric"></select></label><button type="button" class="i" id="cp-def" data-t="score" aria-expanded="false" aria-label="What is this measure?">i</button>
<div class="search cp-add">{c.ico("search", 16, c.MUTED)}<input id="cp-q" placeholder="Add a name to the set" autocomplete="off"><div class="cp-sugg" id="cp-sugg" hidden></div></div>
<span class="small muted" id="cp-count"></span></div>
<div class="cp-pins" id="cp-pins"></div></div></div>
<div class="dash" id="dash">
{panel("rank", "Ranking now", "latest figure, set median")}
{panel("trend", "Trend", "quarter ends, set median dashed")}
{panel("bump", "Rank over time", "position within the set", wide=True)}
</div>
<div class="card cp-card"><div class="pc-head"><h3>The set in numbers <span class="muted small">· latest reported figures; click a heading to sort, a swatch to pin</span></h3></div><div class="table-wrap scrollbox" id="c-table"></div></div>
<div class="table-foot"><span>Figures are the latest reported by each name; sources and dates are on each profile. Ranks count only names with a figure at that date. The score's history is recomputed with today's method and rating on the ratios as they stood.</span></div>'''

# What the policy page's dialog reads when a card is opened. The profile JSON carries the
# document, page, method and confidence behind every point, which is the right record for a
# bank's own page and a hundred kilobytes the dialog has no use for.
DETAIL_SERIES = ("cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio",
                 "lcr", "nsfr", "npl_ratio", "roe", "efficiency_ratio")
DETAIL_KEEP = ("id", "short", "name", "country", "score", "band", "coverage", "asof",
               "rating_composite", "peer_group", "percentile", "unscored")


def _quartiles(vals: list[float]) -> dict | None:
    v = sorted(x for x in vals if x is not None)
    if len(v) < 4:
        return None
    q = lambda f: v[min(len(v) - 1, int(f * (len(v) - 1) + 0.5))]
    return {"p25": round(q(0.25), 2), "p50": round(q(0.5), 2), "p75": round(q(0.75), 2), "n": len(v)}


def write_detail(limit: int = 40) -> int:
    """One slim file per bank, values and dates only, for the policy dialog.

    Also writes the peer quartiles for each ratio by peer group, so a trend can be read against
    the bank's peers rather than only against its own past. These are today's peer positions -
    the latest value each peer holds - not a peer history, and the dialog says so.
    """
    src, dst = store.DATA / "json" / "banks", OUT / "data" / "detail"
    dst.mkdir(parents=True, exist_ok=True)
    groups: dict[str, dict[str, list]] = {}
    n = 0
    for f in sorted(src.glob("*.json")):
        try:
            b = json.loads(f.read_text())
        except Exception:
            continue
        g = b.get("peer_group") or ""
        if g:
            for m in DETAIL_SERIES:
                pts = b.get("series", {}).get(m) or []
                if pts:
                    groups.setdefault(g, {}).setdefault(m, []).append(pts[-1]["v"])
        series = {}
        for m in DETAIL_SERIES:
            pts = b.get("series", {}).get(m) or []
            if len(pts) >= 2:
                series[m] = [{"d": p["d"], "v": p["v"]} for p in pts[-limit:]]
        out = {k: b.get(k) for k in DETAIL_KEEP if b.get(k) is not None}
        out["series"] = series
        out["rating"] = b.get("rating")
        out["rating_worst"] = b.get("rating_worst")
        out["score_detail"] = (b.get("score_detail") or {}).get("pillars") and {"pillars": b["score_detail"]["pillars"]} or None
        out["events"] = (b.get("events") or [])[:8]
        rh = b.get("rating_history")
        if rh:
            # the dialog draws the composite path and says what moved it; the full ladder, every
            # agency and every action, is a click away on the profile
            out["rating_history"] = {"start": rh["start"], "composite": rh["composite"],
                                     "ups": rh["ups"], "downs": rh["downs"], "moves": rh["moves"][:5]}
        (dst / f.name).write_text(json.dumps(out, separators=(",", ":")))
        n += 1
    peers = {g: {m: q for m, vals in ms.items() if (q := _quartiles(vals))} for g, ms in groups.items()}
    (OUT / "data" / "peers.json").write_text(json.dumps(peers, separators=(",", ":")))
    return n


def build():
    board = load("board"); status = load("status"); generated = board["generated"]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "banks").mkdir(parents=True); (OUT / "events").mkdir(); (OUT / "method").mkdir(); (OUT / "status").mkdir()
    shutil.copytree(ASSETS, OUT / "assets")
    faces = (ASSETS / "fonts.css").read_text()
    css = OUT / "assets" / "site.css"
    css.write_text(faces + css.read_text())        # one stylesheet: the faces first, then everything that uses them
    _write(OUT / "index.html", page_landing(board, status, generated))
    (OUT / "tool").mkdir(exist_ok=True)
    _write(OUT / "tool" / "index.html", page_tool(board, status, generated))
    (OUT / "data" / "panels").mkdir(parents=True, exist_ok=True)
    for name, html in home_panels(board, status, generated).items():
        _write(OUT / "data" / "panels" / f"{name}.html", html)
    _write(OUT / "banks" / "index.html", page_gone("Banks", generated, "../tool/index.html#universe", "universe"))
    for r in board["rows"]:
        _write(OUT / "banks" / f"{r['id']}.html", page_bank(load(f"banks/{r['id']}"), generated))
    _write(OUT / "events" / "index.html", page_gone("Events", generated, "../tool/index.html#policy", "policy"))
    (OUT / "admin").mkdir(exist_ok=True)
    _write(OUT / "admin" / "index.html", page_admin(status, board, generated))
    _write(OUT / "admin" / "maintainer.html", page_maintainer(status, board, generated))
    _write(OUT / "method" / "index.html", page_gone("Method", generated, "../admin/index.html#method", "admin"))
    (OUT / "ratings").mkdir(exist_ok=True)
    _write(OUT / "ratings" / "index.html", page_gone("Ratings", generated, "../tool/index.html#ratings", "ratings"))
    (OUT / "compare").mkdir(exist_ok=True); (OUT / "data").mkdir(exist_ok=True)
    _write(OUT / "compare" / "index.html", page_gone("Analysis", generated, "../tool/index.html#analysis", "analysis"))
    shutil.copy(store.DATA / "json" / "compare.json", OUT / "data" / "compare.json")
    (OUT / "coverage").mkdir(exist_ok=True)
    _write(OUT / "coverage" / "index.html", page_gone("Coverage", generated, "../admin/index.html#coverage", "admin"))
    (OUT / "policy").mkdir(exist_ok=True)
    _write(OUT / "policy" / "index.html", page_gone("My policy", generated, "../tool/index.html#policy", "policy"))
    (OUT / "data").mkdir(exist_ok=True)
    shutil.copy(store.DATA / "json" / "policy.json", OUT / "data" / "policy.json")
    write_detail()
    if os.environ.get(attributed.ENV):
        # the attributed ratings, for the members path only; never in the public data
        from ..entities import load as load_entities
        n = attributed.write(OUT / "members" / "ratings.json", [e for e in load_entities() if e.active], store.read("ratings"))
        print(f"members/ratings.json: the agencies' own ratings on {n} names")
    (OUT / "brief").mkdir(exist_ok=True)
    _write(OUT / "brief" / "index.html", page_brief_redirect(generated))
    _write(OUT / "status" / "index.html", page_gone("Status", generated, "../admin/index.html#status", "admin"))
    _write(OUT / ".nojekyll", "")
    print(f"built site/ with {len(board['rows'])} bank pages")
