"""Visual components shared by every page. Same language as design/gen.py (PWLBtoday tokens)."""
from __future__ import annotations

import html
import json

from . import glossary

# Prefetch is cheap - the document is fetched and held, nothing is parsed or run. Prerender is a
# whole page load: parse, scripts, fonts, layout. At "moderate" it fires when the pointer settles
# on a link, so running the mouse down the board's 153 bank links starts and evicts prerender after
# prerender, each a 438 KB document, against the page the reader is actually looking at. Prefetch
# on hover, and prerender only once a click has begun, keeps the arrival instant without that.
SPECULATION = json.dumps({
    "prefetch": [{"where": {"href_matches": "/*"}, "eagerness": "moderate"}],
    "prerender": [{"where": {"href_matches": "/*"}, "eagerness": "conservative"}],
}, separators=(",", ":"))


NAVY, NAVY_MID, NAVY_LIGHT = "#0a2540", "#143659", "#1a4775"
ORANGE, ORANGE_SOFT = "#fd7e14", "#fff5e9"
TEXT, MUTED, LINE, LINE_SOFT, BG, WHITE = "#243240", "#6c757d", "#e9ecef", "#f1f3f5", "#f7f8fa", "#ffffff"
GREEN, RED = "#1e7a3a", "#b04632"
GRAD = "linear-gradient(180deg, #0a2540 0%, #143659 60%, #1a4775 100%)"
BAND_COLOURS = {"A": NAVY, "B": "#3f5f85", "C": "#7d93ad", "D": "#a9b8c9", "E": "#c9d3de", "?": "#dfe5eb", "": "#dfe5eb"}

ICONS = {
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "bank": '<path d="M3 10h18"/><path d="M5 10v8"/><path d="M9 10v8"/><path d="M15 10v8"/><path d="M19 10v8"/><path d="M3 18h18"/><path d="M12 3l9 7H3l9-7z"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21h4"/>',
    "list": '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "star": '<path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9L12 3z"/>',
    "download": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    "compare": '<path d="M9 3v18"/><path d="M15 3v18"/><path d="M3 9h18"/><path d="M3 15h18"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "doc": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h8"/>',
    "chev": '<path d="M9 6l6 6-6 6"/>', "up": '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>', "down": '<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>', "flat": '<path d="M5 12h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>', "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "menu": '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>', "back": '<path d="M15 18l-6-6 6-6"/>', "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "status": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
}


def info(key: str, cls: str = "") -> str:
    """The small marker that opens a plain-English definition beside a number.

    One button, no icon file: the glyph is a character, because these appear a few dozen times on
    a page and a table of 152 rows cannot afford an SVG in every heading. The definition itself is
    not repeated in the markup - every page carries the glossary once and the popover reads it.
    """
    title = glossary.TERMS[key][0]
    return (f'<button type="button" class="i{" " + cls if cls else ""}" data-t="{key}" '
            f'aria-expanded="false" aria-label="What is {esc(title)}?">i</button>')


def term(key: str, label: str = "", cls: str = "") -> str:
    """A label with its definition marker after it."""
    return f'{esc(label or glossary.TERMS[key][0])}{info(key, cls)}'


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def ico(name: str, size: int = 18, color: str = "currentColor") -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def symbols() -> str:
    """Icons drawn many times on one page are defined once and referenced with <use>."""
    return ('<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
            f'<symbol id="i-star" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS["star"]}</symbol></svg>')


def use_icon(name: str, size: int = 15, color: str = "currentColor") -> str:
    return f'<svg width="{size}" height="{size}" style="color:{color}" aria-hidden="true"><use href="#i-{name}"/></svg>'


def fmt(v, dp=1, suffix="") -> str:
    if v is None:
        return '<span class="na">—</span>'
    return f'<span class="mono">{v:,.{dp}f}{suffix}</span>'


def spark(series: list[float], w=92, h=28, color=NAVY) -> str:
    s = [v for v in series if v is not None]
    if len(s) < 2:
        return f'<svg width="{w}" height="{h}" aria-hidden="true"></svg>'
    if len(s) > 48:                                   # a year of prices needs no more points than pixels
        step = len(s) / 48
        s = [s[int(i * step)] for i in range(48)] + [s[-1]]
    lo, hi = min(s), max(s); rng = (hi - lo) or 1; pad = 3
    pts = [(pad + i * (w - 2 * pad) / (len(s) - 1), h - pad - (v - lo) / rng * (h - 2 * pad)) for i, v in enumerate(s)]
    path = "M" + "L".join(f"{x:.0f} {y:.0f}" for x, y in pts)
    ex, ey = pts[-1]
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{ex:.0f}" cy="{ey:.0f}" r="2.6" fill="{ORANGE}"/></svg>')


def _chart_compact(pts_in, w, h, unit, req, dp, band=None, median=None, on_dark=False) -> str:
    vals = [v for _, v in pts_in]
    ref = ([req] if req else []) + (list(band) if band else []) + ([median] if median is not None else [])
    lo, hi = min(vals + ref), max(vals + ref)
    span = (hi - lo) or 1
    ymin, ymax = lo - span * 0.18, hi + span * 0.22
    padl, padr, padt, padb = 6, 6, 6, 16
    n = len(pts_in)
    X = lambda i: padl + i * (w - padl - padr) / (n - 1)
    Y = lambda v: padt + (ymax - v) / (ymax - ymin) * (h - padt - padb)
    path = "M" + "L".join(f"{X(i):.0f} {Y(v):.0f}" for i, (_, v) in enumerate(pts_in))
    reqline = f'<line x1="{padl}" x2="{w-padr}" y1="{Y(req):.0f}" y2="{Y(req):.0f}" stroke="{ORANGE}" stroke-width="1.2" stroke-dasharray="3 3"/>' if req else ""
    # the peer group's quartile band, drawn behind everything, with its median dashed
    peer = ""
    if band:
        peer = (f'<rect x="{padl}" y="{Y(band[1]):.0f}" width="{w-padl-padr}" height="{max(1, Y(band[0])-Y(band[1])):.0f}" fill="{MUTED}" fill-opacity="0.15"/>')
    if median is not None:
        peer += f'<line x1="{padl}" x2="{w-padr}" y1="{Y(median):.0f}" y2="{Y(median):.0f}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="3 2" stroke-opacity="0.75"/>' 
    last = pts_in[-1][1]
    imin, imax = vals.index(min(vals)), vals.index(max(vals))
    marks = "".join(f'<text x="{min(max(X(i), 18), w - 18):.0f}" y="{(Y(v) - 5) if k == "max" else (Y(v) + 11):.0f}" text-anchor="middle" class="axis">{v:.{dp}f}{unit}</text>'
                    for k, i, v in (("max", imax, vals[imax]), ("min", imin, vals[imin])) if i not in (0, n - 1))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" class="chart chart-sm" preserveAspectRatio="none" aria-hidden="true">'
            f'{peer}{reqline}'
            f'<path d="{path}" fill="none" stroke="{NAVY}" stroke-width="1.8" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{X(n-1):.0f}" cy="{Y(last):.0f}" r="3.2" fill="{ORANGE}"/>{marks}'
            f'<text x="{padl}" y="{h-4}" class="axis">{esc(pts_in[0][0])}</text><text x="{w-padr}" y="{h-4}" text-anchor="end" class="axis">{esc(pts_in[-1][0])}</text></svg>')


def ribbon(score, p25=None, p50=None, p75=None, w=96, h=10, fluid: bool = False) -> str:
    """The band scale with the peer quartile band, the peer median and this bank's marker.
    One element, no children: every layer is a background gradient, so a 152-row table
    carries 152 nodes rather than 800."""
    if score is None:
        return ""
    pc = lambda v: f"{max(0.0, min(100.0, v)):.1f}%"
    r = 4.6                                        # the marker travels inside the bar so it never clips at either end
    mark = (r + max(0.0, min(100.0, score)) / 100 * (w - 2 * r)) / w * 100
    # fluid keeps the marker's inset proportional to w while the bar itself fills its box
    style = f"width:{'100%' if fluid else f'{w}px'};height:{h}px;--s:{mark:.1f}%"
    cls = "ribbon"
    if p25 is not None and p75 is not None:
        style += f";--a:{pc(p25)};--b:{pc(p75)}"
        cls += " rb-band"
    if p50 is not None:
        style += f";--m:{pc(p50)}"
        cls += " rb-med"
    return f'<span class="{cls}" style="{style}" aria-hidden="true"></span>'


def chip(text: str, kind: str = "muted") -> str:
    return f'<span class="chip chip-{kind}">{text}</span>'


def band_chip(b: str) -> str:
    label = b or "?"
    title = {"?": "Insufficient data for a band", "": "No data yet"}.get(b, f"Band {b}")
    return f'<span class="band mono band-{b if b in "ABCDE" and b else "x"}" title="{title}">{label}</span>'


def agency_chips(ratings: list[dict]) -> str:
    if not ratings:
        return '<span class="na" title="No agency rates this bank; its score is capped below band A">unrated</span>'
    return '<div class="agencies">' + "".join(
        f'<span class="agency" title="{esc(r["agency"])} {esc(r["type"])} {esc(r["outlook"])} {esc(r["date"])}">'
        f'<span class="agency-letter">{esc(r["letter"])}</span><span class="mono">{esc(r["value"])}</span></span>' for r in ratings) + "</div>"


def market_glyph(m: dict) -> str:
    d, l = m.get("direction", "none"), m.get("label", "")
    if d == "none":
        return f'<span class="mkt mkt-none" title="{esc(l)}">—</span>'
    c = {"up": GREEN, "down": RED, "flat": MUTED}[d]
    return f'<span class="mkt mkt-{d}" title="{esc(l)}">{ico(d, 14, c)}</span>'


def chg(v: float | None, dp=1, suffix="") -> str:
    if v is None:
        return '<span class="na">—</span>'
    col = GREEN if v > 0 else (RED if v < 0 else MUTED)
    sign = "+" if v > 0 else ("−" if v < 0 else "")
    return f'<span class="mono" style="color:{col};font-weight:500">{sign}{abs(v):.{dp}f}{suffix}</span>'


def chart(series: list[tuple[str, float]], w=560, h=200, unit="%", req: float | None = None, req_label="Requirement",
          band: tuple[float, float] | None = None, median: float | None = None,
          ymin=None, ymax=None, step=None, dp=1, compact: bool = False, on_dark: bool = False) -> str:
    """Line chart with dots, optional requirement line and peer band. series: [(label, value)] oldest first.
    compact draws a small multiple: area and line, the requirement, first and last x labels, no dots or grid."""
    pts_in = [(l, v) for l, v in series if v is not None]
    if len(pts_in) < 2:
        return '<div class="empty">Not enough history yet</div>'
    if compact:
        return _chart_compact(pts_in, w, h, unit, req, dp, band, median, on_dark)
    vals = [v for _, v in pts_in]
    lo, hi = min(vals + ([req] if req else []) + ([band[0]] if band else [])), max(vals + ([req] if req else []) + ([band[1]] if band else []))
    if ymin is None or ymax is None:
        span = (hi - lo) or 1
        ymin = lo - span * 0.25 if ymin is None else ymin
        ymax = hi + span * 0.25 if ymax is None else ymax
    if step is None:
        step = max(round((ymax - ymin) / 4, 1), 0.1)
    widest = max(len(f"{v:.{dp}f}{unit}") for v in (ymin, ymax))
    padl, padr, padt, padb = max(44, 12 + widest * 7), 16, 14, 26
    n = len(pts_in)
    X = lambda i: padl + i * (w - padl - padr) / (n - 1)
    Y = lambda v: padt + (ymax - v) / (ymax - ymin) * (h - padt - padb)
    grid, v = [], ymin
    while v <= ymax + 1e-9:
        grid.append(f'<line x1="{padl}" x2="{w-padr}" y1="{Y(v):.0f}" y2="{Y(v):.0f}" stroke="{LINE}"/>'
                    f'<text x="{padl-8}" y="{Y(v)+4:.0f}" text-anchor="end" class="axis">{v:.{dp}f}{unit}</text>')
        v += step
    # grey for the peer band: orange is the requirement line's colour everywhere else, and the
    # two must not be read as the same thing
    bandr = f'<rect x="{padl}" y="{Y(band[1]):.0f}" width="{w-padl-padr}" height="{Y(band[0])-Y(band[1]):.0f}" fill="{MUTED}" fill-opacity="0.15"/>' if band else ""
    if median is not None:
        bandr += (f'<line x1="{padl}" x2="{w-padr}" y1="{Y(median):.0f}" y2="{Y(median):.0f}" stroke="{MUTED}" '
                  f'stroke-width="1.2" stroke-dasharray="4 3" stroke-opacity="0.8"/>'
                  f'<text x="{w-padr-4}" y="{Y(median)-4:.0f}" text-anchor="end" class="axis">peer median</text>')
    reqline = (f'<line x1="{padl}" x2="{w-padr}" y1="{Y(req):.0f}" y2="{Y(req):.0f}" stroke="{ORANGE}" stroke-width="1.5" stroke-dasharray="4 4"/>'
               f'<text x="{padl+6}" y="{Y(req)-6:.0f}" class="axis" fill="#b35900">{req_label} {req:.{dp}f}{unit}</text>') if req else ""
    pts = " ".join(f"{X(i):.0f},{Y(v):.0f}" for i, (_, v) in enumerate(pts_in))
    area = ""      # a shaded region on this site is the peer range; a line does not shade under itself
    dots = "".join(f'<circle cx="{X(i):.0f}" cy="{Y(v):.0f}" r="3" fill="{WHITE}" stroke="{NAVY}" stroke-width="2"><title>{esc(l)}: {v:.{dp}f}{unit}</title></circle>' for i, (l, v) in enumerate(pts_in))
    last = pts_in[-1][1]
    end = f'<circle cx="{X(n-1):.0f}" cy="{Y(last):.0f}" r="4" fill="{ORANGE}"/><text x="{X(n-1)-10:.0f}" y="{Y(last)-10:.0f}" text-anchor="end" class="mono" font-size="12" font-weight="600" fill="{TEXT}">{last:.{dp}f}{unit}</text>'
    every = max(1, -(-n // 7))
    idx = [i for i in range(0, n, every)]
    if idx and n - 1 - idx[-1] < every / 2:
        idx = idx[:-1]
    idx.append(n - 1)
    xl = "".join(f'<text x="{X(i):.0f}" y="{h-8}" text-anchor="{"end" if i == n - 1 else "middle"}" class="axis">{esc(pts_in[i][0])}</text>' for i in idx)
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" class="chart" style="max-width:100%">{"".join(grid)}{bandr}{reqline}{area}'
            f'<polyline points="{pts}" fill="none" stroke="{NAVY}" stroke-width="2" stroke-linejoin="round"/>{dots}{end}{xl}</svg>')


# One page does the work - policy, universe, ratings, events - so the nav names it once. Analysis
# stays separate because comparing several banks is the one thing a single name's dialog cannot do.
def stamp(generated: str) -> str:
    """This build, as a query a browser treats as a different file.

    A page and the script that runs it are cached separately for ten minutes each, so a reader can
    hold a new page and yesterday's script - which is how a tab arrived with nothing behind it.
    Every asset the shell names carries the build it belongs to, so new HTML always fetches the
    scripts and styles it was built against.
    """
    return "".join(ch for ch in generated[:16] if ch.isdigit())


def shell(title: str, content: str, active: str, root: str = "", generated: str = "", subtitle: str = "",
          preload: tuple[str, ...] = ()) -> str:
    """One page, no rail. The site is one page and three tabs of it; a navigation column of three
    links, one of them always the page you are on, spent 220px saying so. The build stamp it used to
    carry sits in the header, where it is still the first thing a reader checks."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Counterparty · PWLBtoday</title>
<meta name="color-scheme" content="light">
{"".join(f'<link rel="preload" href="{root}{p}" as="fetch" crossorigin>' for p in preload)}
<link rel="preload" href="{root}assets/fonts/inter-600-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}assets/fonts/inter-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}assets/site.css?v={stamp(generated)}">
<script type="speculationrules">{SPECULATION}</script>
</head><body>{symbols()}
<header class="top"><a class="brand" href="{root}index.html"><span class="dot"></span>PWLB<span class="brand-accent">today</span></a>
<div class="crumb"><span class="crumb-app">Counterparty</span>{'' if title == "Counterparty" else f'<span class="crumb-sep">/</span><span class="crumb-page">{esc(title)}</span>'}</div>
<div class="top-right"><span class="built">{ico("clock", 13, MUTED)} Built {esc(generated[:16].replace("T", " "))} UTC</span><span class="beta">Beta</span></div></header>
<div class="frame"><main class="main">{content}</main></div>
<dialog id="gloss-dlg" class="gloss-dlg"></dialog>
<footer class="foot"><button type="button" class="glink" id="glink">What do these numbers mean?</button> Counterparty is information, not advice. Public regulatory data, public rating registers and traded market prices; every figure carries its source and date. Scores use the published method and can be wrong. <a href="{root}admin/index.html#method">Method</a> · <a href="{root}admin/index.html#status">Data status</a></footer>
<script id="gloss" type="application/json">{glossary.payload()}</script>
<script src="{root}assets/app.js?v={stamp(generated)}"></script></body></html>"""


# ---- rating history -----------------------------------------------------------------------------
# One colour per agency, none of them the navy the composite is drawn in: seven lines on one ladder
# only work if the eye can tell them apart at a glance and still find the median under them.
AGENCY_COLOUR = {"fitch": "#2f6fd0", "sp": "#fd7e14", "moodys": "#7d5ba6", "dbrs": "#1e7a3a",
                 "kbra": "#2d8f9e", "scope": "#b04632", "jcr": "#8a6d3b"}
AGENCY_NAME = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's", "dbrs": "DBRS", "kbra": "KBRA",
               "scope": "Scope", "jcr": "JCR"}
# Where the ladder is labelled. The scale runs 1 = AAA to 17 = CCC and below; a rung every notch
# would be unreadable, so the letter grades get the lines and the notches sit between them.
# The order the weighting model reads a bank's pillar sub-scores in, shared with export.PILLAR_ORDER.
PILLAR_KEYS = ("capital", "liquidity", "asset_quality", "profitability", "stability", "rating")

SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
         "B+", "B", "B-", "CCC"]
# One ramp for every rating on the site, the same one the policy page has always used for a score:
# deep green at AAA through to red below CCC. It replaced five buckets of navy and blue, which put
# almost every covered bank in the same one or two shades - the grid was a wall of blue, and AAA
# and A- were the same colour on a page whose whole job is telling them apart.
RAMP = [(0.00, 122, 31, 40), (0.12, 156, 43, 40), (0.25, 193, 70, 42), (0.38, 210, 118, 42),
        (0.50, 208, 160, 47), (0.62, 127, 174, 73), (0.75, 63, 148, 85), (0.88, 29, 122, 94),
        (1.00, 18, 87, 74)]

def ramp_colour(t: float) -> str:
    t = max(0.0, min(1.0, t))
    for i in range(1, len(RAMP)):
        if t <= RAMP[i][0]:
            a, b = RAMP[i - 1], RAMP[i]
            k = (t - a[0]) / ((b[0] - a[0]) or 1)
            return "#%02x%02x%02x" % tuple(round(a[j] + (b[j] - a[j]) * k) for j in (1, 2, 3))
    return "#12574a"


INVESTMENT_GRADE = 10.5      # between BBB- and BB+, the one line a treasury policy is written around


def grade_colour(grade) -> str:
    """A rating's own colour on the 1 = AAA to 17 = CCC scale.

    The ramp's turn from green to amber is pinned to the investment-grade line rather than to the
    middle of the alphabet, so every name a treasurer can hold reads as a green and only the ones
    below the line go warm. Spread evenly instead, A came out the colour of a warning and the ten
    investment-grade notches shared the top third of the ramp, which is what made a page of banks
    look like one flat colour.
    """
    if grade is None:
        return "#dfe5eb"
    g = max(1.0, min(17.0, float(grade)))
    t = (1 - (g - 1) / (INVESTMENT_GRADE - 1) * 0.5 if g <= INVESTMENT_GRADE
         else 0.5 - (g - INVESTMENT_GRADE) / (17 - INVESTMENT_GRADE) * 0.5)
    return ramp_colour(t)


def on_colour(hex_colour: str) -> str:
    """Whichever of light or dark type reads better on that fill.

    The ramp runs light through its middle, so white that works on the teal at AAA is barely there
    on the gold at BBB. Picked on contrast rather than a lightness threshold, because the two are
    not the same question and a threshold gets the oranges wrong either way it is set.
    """
    def lum(rgb):
        c = [v / 255 for v in rgb]
        c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    try:
        fill = lum([int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)])
    except (ValueError, IndexError):
        return TEXT
    on_light = (fill + 0.05) / (lum((29, 43, 22)) + 0.05)
    on_white = (1.0 + 0.05) / (fill + 0.05)
    return "#fff" if on_white >= on_light else "#1d2b16"
TONE_COLOUR = {"positive": GREEN, "negative": RED, "stable": "#9aa7b4",
               "watch positive": GREEN, "watch negative": RED, "watch": MUTED}


def GRADE_BAND(g):
    if g is None:
        return "#dfe5eb"
    for upper, col in GRADE_BANDS:
        if g <= upper:
            return col
    return RED


def _letter(g):
    return SCALE[max(0, min(16, int((g or 1) + 0.5) - 1))]


def _frac(d: str) -> float:
    """A date as a year and a fraction of one, which is all a time axis needs."""
    return int(d[:4]) + (int(d[5:7]) - 1) / 12 + (int(d[8:10]) - 1) / 365


def _today() -> str:
    from datetime import date as _d
    return _d.today().isoformat()


def rating_timeline(hist: dict, w: int = 1000, today: str = "") -> str:
    """Eleven years of ratings as what they are: a state each agency held, and the tone under it.

    Five step lines on one notch axis was spaghetti - most banks live inside two notches, so the
    lines sat on top of each other and the composite disappeared beneath them. A rating is a state,
    not a measurement, so each agency gets a band of blocks, one block per rating it held, coloured
    by the range it sits in and labelled with the symbol. The composite keeps a line, alone, above
    them: one line cannot tangle, and it carries the shape of the story.

    Under each band runs the outlook, which the register has published all along and this site was
    throwing away. It is the most forward-looking thing here: S&P held Barclays on negative through
    2016, went negative again in 2020, turned positive in 2022 and upgraded in 2023.
    """
    ags = [a for a in (hist or {}).get("agencies") or [] if a.get("blocks")]
    comp = (hist or {}).get("composite") or []
    if not ags:
        return ""
    end = today or _today()
    starts = [b[0] for a in ags for b in a["blocks"]]
    lane, gap, padl, padr, padt, padb = 32, 9, 76, 56, 18, 24
    cg = [c[1] for c in comp] or [1]
    # a bank that has travelled eleven notches needs more room than one that has not moved
    ch = int(min(168, max(96, 74 + 8 * (max(cg) - min(cg))))) if comp else 0
    h = padt + ch + len(ags) * (lane + gap) + padb
    lo = _frac(min(starts))
    hi = max(_frac(end), lo + 1)
    X = lambda d: padl + (_frac(d) - lo) / (hi - lo) * (w - padl - padr)
    out = ""
    for y in range(int(lo) + 1, int(hi) + 1):
        x = X(f"{y}-01-01")
        out += (f'<line x1="{x:.0f}" x2="{x:.0f}" y1="{padt}" y2="{h-padb:.0f}" stroke="{LINE}"/>'
                f'<text x="{x:.0f}" y="{h-8}" text-anchor="middle" class="axis">{y}</text>')
    # ---- the composite, one line, above everything ----
    if comp:
        cmin, cmax = min(cg) - 0.9, max(cg) + 0.9
        Y = lambda g: padt + 8 + (g - cmin) / (cmax - cmin) * (ch - 34)
        rungs = list(range(int(cmin) + 1, int(cmax) + 1))
        per = (ch - 34) / max(0.001, cmax - cmin)
        step = max(1, int(-(-13 // per)))
        if len(rungs) > 9:
            step = max(step, 2)
        for g in rungs:
            out += f'<line x1="{padl}" x2="{w-padr}" y1="{Y(g):.0f}" y2="{Y(g):.0f}" stroke="{LINE}"/>'
            if rungs and (g - rungs[0]) % step == 0:
                out += f'<text x="{padl-8}" y="{Y(g)+4:.0f}" text-anchor="end" class="axis">{SCALE[g-1]}</text>'
        pth, prev = "", None
        for d, g in comp:
            x, y = X(d), Y(g)
            pth += (f"M{x:.0f},{y:.0f}" if prev is None else f"H{x:.0f}V{y:.0f}")
            prev = y
        pth += f"H{X(end):.0f}"
        out += (f'<path d="{pth}" fill="none" stroke="{NAVY}" stroke-width="2.5" '
                f'stroke-linejoin="round" stroke-linecap="round"/>')
        for d, g in comp:
            out += (f'<circle cx="{X(d):.0f}" cy="{Y(g):.0f}" r="3.4" fill="{WHITE}" stroke="{NAVY}" '
                    f'stroke-width="2"><title>composite {esc(_letter(g))} from {esc(d)}</title></circle>')
        out += (f'<text x="{X(end)+6:.0f}" y="{Y(comp[-1][1])+4:.0f}" class="mono" font-size="12.5" '
                f'font-weight="700" fill="{NAVY}">{esc(_letter(comp[-1][1]))}</text>'
                f'<text x="{padl-8}" y="{padt}" text-anchor="end" class="axis" font-weight="600">COMPOSITE</text>')
    # ---- a band per agency ----
    for i, a in enumerate(ags):
        top = padt + ch + i * (lane + gap)
        who = esc(AGENCY_NAME.get(a["agency"], a["agency"]))
        out += (f'<text x="{padl-8}" y="{top+lane/2+4:.0f}" text-anchor="end" font-size="11.5" '
                f'font-weight="600" fill="{TEXT}">{who}</text>'
                # the years before an agency first rated the bank, and any gap after a withdrawal
                f'<line x1="{padl}" x2="{w-padr}" y1="{top+lane/2:.0f}" y2="{top+lane/2:.0f}" '
                f'stroke="#dfe5eb" stroke-width="1.5" stroke-dasharray="2 4"/>')
        for start, stop, value, grade in a["blocks"]:
            x1, x2 = X(start), X(stop or end)
            col = grade_colour(grade)
            held = f"from {esc(start)}" + (f" to {esc(stop)}" if stop else ", still")
            out += (f'<g><title>{who} {esc(value)} {held}</title>'
                    f'<rect x="{x1:.0f}" y="{top}" width="{max(2, x2-x1):.0f}" height="{lane}" fill="{col}" rx="3"/>')
            if x2 - x1 > 32:
                out += (f'<text x="{(x1+x2)/2:.0f}" y="{top+lane/2+4:.0f}" text-anchor="middle" class="mono" '
                        f'font-size="11" font-weight="600" fill="{on_colour(col)}">'
                        f'{esc(value)}</text>')
            out += "</g>"
        for start, stop, tone in a["marks"]:
            x1, x2 = X(start), X(stop or end)
            col = TONE_COLOUR.get(tone, MUTED)
            out += (f'<g><title>{who}: {esc(tone)} outlook from {esc(start)}</title>'
                    f'<rect x="{x1:.0f}" y="{top+lane+2}" width="{max(2, x2-x1):.0f}" height="3.5" '
                    f'fill="{col}" rx="1.75"/>')
            if tone.startswith("watch"):
                out += f'<path d="M{x1:.0f},{top-3} l4,-5 l4,5 z" fill="{col}"/>'
            out += "</g>"
        last = a["blocks"][-1]
        if last[1] is None:
            out += (f'<text x="{X(end)+6:.0f}" y="{top+lane/2+4:.0f}" class="mono" font-size="11.5" '
                    f'font-weight="600" fill="{grade_colour(last[3])}">{esc(last[2])}</text>')
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" class="chart ladder" role="img" '
            f'aria-label="Ratings and outlooks since {esc((hist or {}).get("start") or "2015")}">{out}</svg>')


def rating_legend(hist: dict) -> str:
    """What the colours mean, and where each agency stands now."""
    if not (hist or {}).get("agencies"):
        return ""
    steps = "".join(f'<i style="background:{grade_colour(g)}"></i>' for g in range(1, 18))
    bands = (f'<span class="rl-k rl-ramp">AAA<span class="rl-scale">{steps}</span>CCC</span>')
    tones = "".join(f'<span class="rl-k rl-o"><i style="background:{col}"></i>{esc(lab)}</span>'
                    for lab, col in (("positive outlook", GREEN), ("stable", "#9aa7b4"),
                                     ("negative", RED)))
    tones += f'<span class="rl-k rl-w"><i></i>went on watch</span>'
    return f'<div class="rl-key">{bands}<span class="rl-sep"></span>{tones}</div>'
