"""Visual components shared by every page. Same language as design/gen.py (PWLBtoday tokens)."""
from __future__ import annotations

import html

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
            f'<path d="{path}V{h-pad}H{pad}Z" fill="{color}" fill-opacity="0.08"/>'
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{ex:.0f}" cy="{ey:.0f}" r="2.6" fill="{ORANGE}"/></svg>')


def _chart_compact(pts_in, w, h, unit, req, dp) -> str:
    vals = [v for _, v in pts_in]
    lo, hi = min(vals + ([req] if req else [])), max(vals + ([req] if req else []))
    span = (hi - lo) or 1
    ymin, ymax = lo - span * 0.18, hi + span * 0.22
    padl, padr, padt, padb = 6, 6, 6, 16
    n = len(pts_in)
    X = lambda i: padl + i * (w - padl - padr) / (n - 1)
    Y = lambda v: padt + (ymax - v) / (ymax - ymin) * (h - padt - padb)
    path = "M" + "L".join(f"{X(i):.0f} {Y(v):.0f}" for i, (_, v) in enumerate(pts_in))
    reqline = f'<line x1="{padl}" x2="{w-padr}" y1="{Y(req):.0f}" y2="{Y(req):.0f}" stroke="{ORANGE}" stroke-width="1.2" stroke-dasharray="3 3"/>' if req else ""
    last = pts_in[-1][1]
    imin, imax = vals.index(min(vals)), vals.index(max(vals))
    marks = "".join(f'<text x="{min(max(X(i), 18), w - 18):.0f}" y="{(Y(v) - 5) if k == "max" else (Y(v) + 11):.0f}" text-anchor="middle" class="axis">{v:.{dp}f}{unit}</text>'
                    for k, i, v in (("max", imax, vals[imax]), ("min", imin, vals[imin])) if i not in (0, n - 1))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" class="chart chart-sm" preserveAspectRatio="none" aria-hidden="true">'
            f'<path d="{path}V{Y(ymin):.0f}H{padl}Z" fill="{NAVY}" fill-opacity="0.07"/>{reqline}'
            f'<path d="{path}" fill="none" stroke="{NAVY}" stroke-width="1.8" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{X(n-1):.0f}" cy="{Y(last):.0f}" r="3.2" fill="{ORANGE}"/>{marks}'
            f'<text x="{padl}" y="{h-4}" class="axis">{esc(pts_in[0][0])}</text><text x="{w-padr}" y="{h-4}" text-anchor="end" class="axis">{esc(pts_in[-1][0])}</text></svg>')


def ribbon(score, p25=None, p50=None, p75=None, w=96, h=10) -> str:
    """The band scale with the peer quartile band, the peer median and this bank's marker.
    One element, no children: every layer is a background gradient, so a 152-row table
    carries 152 nodes rather than 800."""
    if score is None:
        return ""
    pc = lambda v: f"{max(0.0, min(100.0, v)):.1f}%"
    r = 4.6                                        # the marker travels inside the bar so it never clips at either end
    mark = (r + max(0.0, min(100.0, score)) / 100 * (w - 2 * r)) / w * 100
    style = f"width:{w}px;height:{h}px;--s:{mark:.1f}%"
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
          band: tuple[float, float] | None = None, ymin=None, ymax=None, step=None, dp=1, compact: bool = False) -> str:
    """Line chart with dots, optional requirement line and peer band. series: [(label, value)] oldest first.
    compact draws a small multiple: area and line, the requirement, first and last x labels, no dots or grid."""
    pts_in = [(l, v) for l, v in series if v is not None]
    if len(pts_in) < 2:
        return '<div class="empty">Not enough history yet</div>'
    if compact:
        return _chart_compact(pts_in, w, h, unit, req, dp)
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
    bandr = f'<rect x="{padl}" y="{Y(band[1]):.0f}" width="{w-padl-padr}" height="{Y(band[0])-Y(band[1]):.0f}" fill="{ORANGE}" fill-opacity="0.10"/>' if band else ""
    reqline = (f'<line x1="{padl}" x2="{w-padr}" y1="{Y(req):.0f}" y2="{Y(req):.0f}" stroke="{ORANGE}" stroke-width="1.5" stroke-dasharray="4 4"/>'
               f'<text x="{padl+6}" y="{Y(req)-6:.0f}" class="axis" fill="#b35900">{req_label} {req:.{dp}f}{unit}</text>') if req else ""
    pts = " ".join(f"{X(i):.0f},{Y(v):.0f}" for i, (_, v) in enumerate(pts_in))
    area = f'<polygon points="{X(0):.0f},{Y(ymin):.0f} {pts} {X(n-1):.0f},{Y(ymin):.0f}" fill="{NAVY}" fill-opacity="0.06"/>'
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


NAV = [("board", "Board", "grid", "index.html"), ("policy", "My policy", "compare", "policy/index.html"), ("compare", "Analysis", "activity", "compare/index.html"), ("ratings", "Ratings", "star", "ratings/index.html"), ("banks", "Banks", "bank", "banks/index.html"),
       ("events", "Events", "activity", "events/index.html"),
       ("method", "Method", "list", "method/index.html"),
       ("coverage", "Coverage", "search", "coverage/index.html"),
       ("status", "Status", "status", "status/index.html")]


def shell(title: str, content: str, active: str, root: str = "", generated: str = "", subtitle: str = "") -> str:
    items = "".join(
        f'<a class="nav{" active" if k == active else ""}" href="{root}{href}">{ico(ic, 17, ORANGE if k == active else "rgba(255,255,255,0.7)")}<span>{lab}</span></a>'
        for k, lab, ic, href in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Counterparty · PWLBtoday</title>
<meta name="color-scheme" content="light">
<link rel="preload" href="{root}assets/fonts/inter-600-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}assets/fonts/inter-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}assets/site.css">
<script type="speculationrules">{{"prerender":[{{"where":{{"href_matches":"/*"}},"eagerness":"moderate"}}]}}</script>
</head><body>{symbols()}
<header class="top"><a class="brand" href="{root}index.html"><span class="dot"></span>PWLB<span class="brand-accent">today</span></a>
<button class="menu-btn" id="menuBtn" aria-label="Menu">{ico("menu", 20, NAVY)}</button>
<div class="crumb"><span class="crumb-app">Counterparty</span><span class="crumb-sep">/</span><span class="crumb-page">{esc(title)}</span></div>
<div class="top-right"><span class="beta">Beta</span></div></header>
<div class="frame"><aside class="side" id="side"><div class="side-label">Counterparty</div>{items}<div class="side-fill"></div>
<div class="side-status">{ico("clock", 14, ORANGE)} Built {esc(generated[:16].replace("T", " "))} UTC</div></aside>
<main class="main">{content}</main></div>
<footer class="foot">Counterparty is information, not advice. Public regulatory data, public rating registers and traded market prices; every figure carries its source and date. Scores use the published method and can be wrong. <a href="{root}method/index.html">Method</a> · <a href="{root}status/index.html">Data status</a></footer>
<script src="{root}assets/app.js"></script></body></html>"""
