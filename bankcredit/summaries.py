"""The written summary on every profile, in two layers.

Layer one is arithmetic on what is already held, rendered as dated sentences by every build -
standing, peers, ratings, trends, news - and costs nothing. Layer two is the two things
arithmetic cannot do, one background sentence and a short synthesis, written by Claude on the
maintainer's machine under the subscription, and rewritten only when the inputs it was written
from have moved or it is over ninety days old. The design is docs/entity-summaries.md.

A summary is one JSON file per name under data/review/summaries/:

    {"id": "barclays-bank", "written": "2026-09-16",
     "background": "...", "synthesis": "...", "inputs": {...the fingerprint it was written from...}}

Every number in a synthesis must appear in the layer-one paragraph it was written from; `check`
enforces that, so a figure the model did not get from us cannot reach the page.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import store

SUMMARIES = store.DATA / "review" / "summaries"
TODO = store.DATA / "cache" / "summaries_todo.json"
MAX_AGE_DAYS = 90
AGENCIES = ("fitch", "sp", "moodys")                     # the three a treasury policy names
AGENCY = {"fitch": "Fitch", "sp": "S&P", "moodys": "Moody's"}
PEER_LABEL = {"uk_large": "UK majors", "uk_mid": "UK mid-sized banks", "uk_small": "UK small banks",
              "uk_bs": "UK building societies", "eu_large": "EU and Nordic banks", "us": "US banks",
              "ch": "Swiss banks", "aus": "Australian banks", "can": "Canadian banks", "asia": "Asian banks",
              "gulf": "Gulf banks"}
RATIOS = (("cet1", "cet1_ratio", "CET1", "%", 1, 0.5), ("leverage", "leverage_ratio", "leverage", "%", 1, 0.3),
          ("lcr", "lcr", "LCR", "%", 0, 10.0), ("nsfr", "nsfr", "NSFR", "%", 0, 5.0))
FLAGGED = ("bad", "warn", "good")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fdate(s) -> str:
    s = str(s or "")[:10]
    try:
        y, m, d = s.split("-")
        return f"{int(d)} {MONTHS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return s


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _quartile(v, pr) -> str | None:
    if v is None or not pr or pr.get("p50") is None:
        return None
    if v >= pr["p75"]:
        return "top quarter"
    if v >= pr["p50"]:
        return "above median"
    if v >= pr["p25"]:
        return "below median"
    return "bottom quarter"


# ---- layer one --------------------------------------------------------------------------------
def brief(d: dict, today: date | None = None) -> dict:
    """The dated sentences the data supports, one per theme, and the fingerprint they rest on."""
    today = today or date.today()
    name = d.get("short") or d.get("name") or d.get("id")
    group = PEER_LABEL.get(d.get("peer_group") or "", "its peer group")
    out = {"standing": "", "peers": "", "ratings": "", "trends": "", "news": "", "asof": d.get("asof")}

    # standing
    if d.get("score") is None or d.get("unscored"):
        why = d.get("unscored") or "not enough current figures"
        out["standing"] = f"{name} is not scored: {why}."
    else:
        s = f"{name} is band {d.get('band') or '?'} with a counterparty score of {d['score']:.0f}"
        peer = d.get("peer") or {}
        if d.get("percentile") is not None and peer.get("n"):
            s += f", {ordinal(int(d['percentile']))} percentile of {peer['n']} {group}"
        hist = [(x[0], x[1]) for x in ((d.get("history") or {}).get("score") or []) if x[1] is not None]
        if len(hist) >= 2:
            delta = hist[-1][1] - hist[-2][1]
            if abs(delta) >= 0.5:
                s += f", {'up' if delta > 0 else 'down'} {abs(delta):.1f} since {fdate(hist[-2][0])}"
            else:
                s += f", unchanged since {fdate(hist[-2][0])}"
        out["standing"] = s + "."

    # peers
    pr_all = d.get("peer_ratios") or {}
    parts = []
    for key, pkey, label, unit, dp, _thr in RATIOS:
        v, pr = d.get(key), pr_all.get(pkey)
        q = _quartile(v, pr)
        if q:
            parts.append(f"{label} {v:.{dp}f}{unit} is {q} of the group (median {pr['p50']:.{dp}f}{unit})")
        elif v is not None:
            parts.append(f"{label} {v:.{dp}f}{unit}")
    if parts:
        out["peers"] = "; ".join(parts) + (f", figures to {fdate(d['asof'])}." if d.get("asof") else ".")

    # ratings
    held = {r["agency"]: r for r in (d.get("ratings") or []) if r.get("agency") in AGENCIES}
    if held:
        rs = []
        for a in AGENCIES:
            if a in held:
                r = held[a]
                rs.append(f"{AGENCY[a]} {r['value']}" + (f" ({r['outlook']})" if r.get("outlook") else ""))
        s = f"Composite rating {d.get('rating_composite') or '—'}: " + ", ".join(rs)
        moves = [m for m in ((d.get("rating_history") or {}).get("moves") or []) if m.get("agency") in AGENCIES]
        if moves:
            m = moves[0]
            s += f"; last move {AGENCY[m['agency']]} {m.get('action', 'action')} to {m.get('value')} on {fdate(m.get('date'))}"
        out["ratings"] = s + "."
    elif d.get("unrated"):
        out["ratings"] = "No public rating from Fitch, S&P or Moody's."

    # trends: over the last four periods, the ratios that moved by more than noise
    series = d.get("series") or {}
    moved, flat = [], []
    for key, pkey, label, unit, dp, thr in RATIOS:
        pts = [p for p in (series.get(pkey) or []) if p.get("v") is not None]
        if len(pts) < 2:
            continue
        back = pts[-5] if len(pts) >= 5 else pts[0]
        delta = pts[-1]["v"] - back["v"]
        span = f"since {fdate(back['d'])}"
        if abs(delta) >= thr:
            moved.append(f"{label} {'up' if delta > 0 else 'down'} {abs(delta):.{dp}f} points {span}")
        else:
            flat.append(label)
    if moved or flat:
        s = ("Over the last four periods " + ", ".join(moved)) if moved else "Over the last four periods no ratio has moved materially"
        if moved and flat:
            s += f"; {', '.join(flat)} broadly unchanged"
        out["trends"] = s + "."

    # news: the flagged events of the last 90 days
    cut = (today - timedelta(days=90)).isoformat()
    flagged = sorted((e for e in (d.get("events") or []) if (e.get("severity") or "info") in FLAGGED and str(e.get("date") or "") >= cut),
                     key=lambda e: e["date"], reverse=True)
    if flagged:
        items = "; ".join(f"{fdate(e['date'])}, {e.get('severity')}: {headline(e.get('title'))}" for e in flagged[:3])
        more = f" and {len(flagged) - 3} more" if len(flagged) > 3 else ""
        out["news"] = f"Flagged in the last 90 days: {items}{more}."
    else:
        out["news"] = "Nothing flagged in the last 90 days."
    out["fingerprint"] = fingerprint(d)
    return out


def headline(title) -> str:
    """A headline without the outlet Google News appends to it, cut to a line."""
    s = str(title or "").strip()
    if " - " in s:
        s = s.rsplit(" - ", 1)[0].strip()
    return s if len(s) <= 90 else s[:87].rstrip() + "\u2026"


def brief_text(b: dict) -> str:
    return " ".join(b[k] for k in ("standing", "peers", "ratings", "trends", "news") if b.get(k))


# ---- the fingerprint: what a written summary rests on ---------------------------------------------
def fingerprint(d: dict) -> dict:
    held = {r["agency"]: f"{r['value']}{' ' + r['outlook'] if r.get('outlook') else ''}"
            for r in (d.get("ratings") or []) if r.get("agency") in AGENCIES}
    flagged = [str(e.get("date"))[:10] for e in (d.get("events") or []) if (e.get("severity") or "info") in FLAGGED]
    return {"band": d.get("band") or "", "composite": d.get("rating_composite") or "", "ratings": held,
            "asof": str(d.get("asof") or ""), "last_flagged": max(flagged) if flagged else ""}


def changes_since(then: dict, now: dict) -> list[str]:
    """What has moved since a summary was written, in the words the profile shows."""
    out = []
    then, now = then or {}, now or {}
    if then.get("band") != now.get("band"):
        out.append(f"band moved from {then.get('band') or '—'} to {now.get('band') or '—'}")
    if then.get("composite") != now.get("composite"):
        out.append(f"composite rating moved from {then.get('composite') or '—'} to {now.get('composite') or '—'}")
    for a in AGENCIES:
        a_then, a_now = (then.get("ratings") or {}).get(a), (now.get("ratings") or {}).get(a)
        if a_then != a_now:
            out.append(f"{AGENCY[a]} moved from {a_then or 'no rating'} to {a_now or 'no rating'}")
    if then.get("asof") != now.get("asof") and now.get("asof"):
        out.append(f"figures updated to {fdate(now['asof'])}" + (f" (were {fdate(then['asof'])})" if then.get("asof") else ""))
    if (now.get("last_flagged") or "") > (then.get("last_flagged") or ""):
        out.append(f"a flagged event on {fdate(now['last_flagged'])} postdates it")
    return out


# ---- the files ------------------------------------------------------------------------------------
def load(entity_id: str) -> dict | None:
    p = SUMMARIES / f"{entity_id}.json"
    if not p.exists():
        return None
    try:
        s = json.loads(p.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return s if isinstance(s, dict) and s.get("synthesis") else None


def why_due(s: dict | None, d: dict, today: date) -> str | None:
    """The reason a summary is owed, or None when the one held still stands."""
    if not s:
        return "no summary yet"
    try:
        age = (today - date.fromisoformat(str(s.get("written"))[:10])).days
    except ValueError:
        return "no date on the summary held"
    if age > MAX_AGE_DAYS:
        return f"written {age} days ago"
    moved = changes_since(s.get("inputs") or {}, fingerprint(d))
    return ("; ".join(moved)) if moved else None


def due(details: dict[str, dict], today: date | None = None) -> list[dict]:
    """Every name whose summary is owed, with the paragraph and the fingerprint to write it from."""
    today = today or date.today()
    out = []
    for eid, d in details.items():
        reason = why_due(load(eid), d, today)
        if reason:
            b = brief(d, today)
            out.append({"id": eid, "name": d.get("name"), "type": d.get("type"), "country": d.get("country"),
                        "reason": reason, "brief": brief_text(b), "inputs": b["fingerprint"],
                        "previous": (load(eid) or {}).get("background")})
    return out


NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![.,]?\d)")     # 46bn and 14.0% are figures; 2026-09-16 is three


def check(s: dict, brief_para: str) -> list[str]:
    """Faults in a summary: a figure the paragraph does not carry, the wrong length, a dated word."""
    faults = []
    for k in ("id", "written", "background", "synthesis", "inputs"):
        if not s.get(k):
            faults.append(f"missing {k}")
    if faults:
        return faults
    allowed = set(NUMBER.findall(brief_para)) | {str(date.fromisoformat(str(s["written"])[:10]).year)}
    text = f"{s['background']} {s['synthesis']}"
    strays = sorted(set(NUMBER.findall(s["synthesis"])) - allowed)
    if strays:
        faults.append("figures not in the paragraph it was written from: " + ", ".join(strays))
    words = len(text.split())
    if not 40 <= words <= 220:
        faults.append(f"{words} words; 40 to 220 is the range")
    for w in ("recently", "this year", "last year", "currently", "CEO", "chief executive", "chairman"):
        if w.lower() in text.lower():
            faults.append(f"dated wording: '{w}'")
    return faults


def write_todo(items: list[dict]) -> Path:
    TODO.parent.mkdir(parents=True, exist_ok=True)
    TODO.write_text(json.dumps(items, indent=1, ensure_ascii=False))
    return TODO


def check_all(details: dict[str, dict], today: date | None = None) -> dict[str, list[str]]:
    """Every summary held, against the paragraph today's data gives it."""
    today = today or date.today()
    out = {}
    if not SUMMARIES.exists():
        return out
    for p in sorted(SUMMARIES.glob("*.json")):
        eid = p.stem
        s = load(eid)
        d = details.get(eid)
        if not s:
            out[eid] = ["not readable, or no synthesis"]
        elif not d:
            out[eid] = ["no such name in the data"]
        else:
            faults = check(s, brief_text(brief(d, today)))
            if faults:
                out[eid] = faults
    return out


def details_from_json() -> dict[str, dict]:
    src = store.DATA / "json" / "banks"
    out = {}
    for f in sorted(src.glob("*.json")) if src.exists() else []:
        try:
            d = json.loads(f.read_text())
            out[d["id"]] = d
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
            continue
    return out
