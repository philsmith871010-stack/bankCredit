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
TYPE_WORD = {"bank": "bank", "building_society": "building society", "holding": "banking group", "subsidiary": "bank"}
COUNTRY = {"GB": "the UK", "US": "the US", "DE": "Germany", "FR": "France", "NL": "the Netherlands", "ES": "Spain", "IT": "Italy",
           "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "FI": "Finland", "CH": "Switzerland", "IE": "Ireland", "BE": "Belgium",
           "AT": "Austria", "CA": "Canada", "AU": "Australia", "SG": "Singapore", "HK": "Hong Kong", "JP": "Japan", "AE": "the UAE",
           "QA": "Qatar", "SA": "Saudi Arabia", "KW": "Kuwait", "CN": "China", "IN": "India", "KR": "South Korea", "LU": "Luxembourg"}


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


PLACE = {"top quarter": "in the top quarter", "above median": "above the median", "below median": "below the median",
         "bottom quarter": "in the bottom quarter"}


def _ratio_clause(label, v, unit, dp, q, pr) -> str:
    return f"{label} of {v:.{dp}f}{unit} is {PLACE[q]} (median {pr['p50']:.{dp}f}{unit})" if q else f"{label} is {v:.{dp}f}{unit}"


def _last_move(m: dict) -> str:
    """'Fitch's upgrade to A on 2 Nov 2025'; a withdrawal or a first rating said as such."""
    who = AGENCY[m["agency"]]
    poss = who if who.endswith("s") else who + "'s"
    act, when = m.get("action") or "action", fdate(m.get("date"))
    if act == "withdrawal":
        was = f" of its {m['from']} rating" if m.get("from") else " of its rating"
        return f"{poss} withdrawal{was} on {when}"
    if act == "new":
        return f"{poss} first rating, {m.get('value')}, on {when}"
    return f"{poss} {act} to {m.get('value')} on {when}"


def brief(d: dict, today: date | None = None) -> dict:
    """The dated sentences the data supports, in plain English, and the fingerprint they rest on.

    Nothing here quotes the site's own score or band: a reader who has moved the weightings sees
    a different score, and the paragraph must not contradict the card beside it. It rests on what
    is published - the agencies' ratings and the banks' own ratios - and on where those sit among
    peers.
    """
    today = today or date.today()
    name = d.get("short") or d.get("name") or d.get("id")
    group = PEER_LABEL.get(d.get("peer_group") or "", "its peer group")
    out = {"standing": "", "capital": "", "liquidity": "", "trends": "", "news": "", "asof": d.get("asof")}

    # who, and what the agencies say
    kind = TYPE_WORD.get(d.get("type") or "", "bank")
    where = COUNTRY.get(d.get("country") or "")
    who = f"{name} is a {kind}" + (f" in {where}" if where else "")
    held = {r["agency"]: r for r in (d.get("ratings") or []) if r.get("agency") in AGENCIES}
    if held:
        rs = [f"{held[a]['value']} by {AGENCY[a]}" for a in AGENCIES if a in held]
        outlooks = {(held[a].get("outlook") or "").lower() for a in AGENCIES if a in held}
        s = f"{who}, rated {_join(rs)}"
        if len(outlooks) == 1 and "" not in outlooks:
            o = outlooks.pop()
            s += f", {'all' if len(rs) > 2 else 'both'} with a {o} outlook" if len(rs) > 1 else f", with a {o} outlook"
        elif len(outlooks) > 1:
            s += " (" + ", ".join(f"{AGENCY[a]} {held[a].get('outlook') or 'no outlook'}" for a in AGENCIES if a in held) + ")"
        moves = [m for m in ((d.get("rating_history") or {}).get("moves") or []) if m.get("agency") in AGENCIES]
        if moves:
            m = moves[0]
            s += f"; the last move was {_last_move(m)}"
        out["standing"] = s + "."
    else:
        out["standing"] = f"{who} with no public rating from Fitch, S&P or Moody's."

    # capital and liquidity, each against the peer group
    pr_all = d.get("peer_ratios") or {}
    def block(keys, noun):
        clauses, qs = [], []
        for key, pkey, label, unit, dp, _thr in RATIOS:
            if key not in keys:
                continue
            v, pr = d.get(key), pr_all.get(pkey)
            if v is None:
                continue
            q = _quartile(v, pr)
            qs.append(q)
            clauses.append(_ratio_clause(label, v, unit, dp, q, pr))
        if not clauses:
            return ""
        known = [q for q in qs if q]
        if not known:
            lead = f"{noun}: "
        elif all(q in ("top quarter", "above median") for q in known):
            lead = f"{noun} is strong against {group}: "
        elif all(q in ("bottom quarter", "below median") for q in known):
            lead = f"{noun} is on the weak side of {group}: "
        else:
            lead = f"{noun} is mixed against {group}: "
        return lead + "; ".join(clauses) + "."
    out["capital"] = block(("cet1", "leverage"), "Capital")
    out["liquidity"] = block(("lcr", "nsfr"), "Liquidity")

    # trends over the last four periods, in points
    series = d.get("series") or {}
    moved, flat, dates = [], [], set()
    for key, pkey, label, unit, dp, thr in RATIOS:
        pts = [p for p in (series.get(pkey) or []) if p.get("v") is not None]
        if len(pts) < 2:
            continue
        back = pts[-5] if len(pts) >= 5 else pts[0]
        delta = pts[-1]["v"] - back["v"]
        if abs(delta) >= thr:
            moved.append((label, "risen" if delta > 0 else "fallen", f"{abs(delta):.{dp}f}", fdate(back["d"])))
            dates.add(fdate(back["d"]))
        else:
            flat.append(label)
    asof = f" (figures to {fdate(d['asof'])})" if d.get("asof") else ""
    if moved:
        # one date where every move is measured from the same one; each its own otherwise
        if len(dates) == 1:
            lead = f"Since {dates.pop()}, "
            parts = [f"{l} has {v} {n} points" for l, v, n, _ in moved]
        else:
            lead = "Over the past four periods "
            parts = [f"{l} has {v} {n} points since {dt}" for l, v, n, dt in moved]
        tail = f", while {_join(flat)} {'has' if len(flat) == 1 else 'have'} been broadly flat" if flat else ""
        out["trends"] = f"{lead}{_join(parts)}{tail}{asof}."
    elif flat:
        out["trends"] = f"None of the ratios has moved materially over the past four periods{asof}."

    # the flagged events of the last 90 days
    cut = (today - timedelta(days=90)).isoformat()
    flagged = sorted((e for e in (d.get("events") or []) if (e.get("severity") or "info") in FLAGGED and str(e.get("date") or "") >= cut),
                     key=lambda e: e["date"], reverse=True)
    if flagged:
        items = "; ".join(f"{fdate(e['date'])}, {e.get('severity')}: {headline(e.get('title'))}" for e in flagged[:3])
        more = f", and {len(flagged) - 3} more" if len(flagged) > 3 else ""
        out["news"] = f"Flagged in the last 90 days: {items}{more}."
    else:
        out["news"] = "Nothing has been flagged in the last 90 days."
    out["fingerprint"] = fingerprint(d)
    return out


def headline(title) -> str:
    """A headline without the outlet Google News appends to it, cut to a line."""
    s = str(title or "").strip()
    if " - " in s:
        s = s.rsplit(" - ", 1)[0].strip()
    return s if len(s) <= 90 else s[:87].rstrip() + "\u2026"


SENTENCES = ("standing", "capital", "liquidity", "trends", "news")


def brief_text(b: dict) -> str:
    return " ".join(b[k] for k in SENTENCES if b.get(k))


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
    if moved:
        return "; ".join(moved)
    # a figure it quotes that today's paragraph no longer carries - a peer median that moved, a
    # headline that dropped out of the window - means it no longer holds, whatever the fingerprint says
    faults = check(s, brief_text(brief(d, today)))
    return ("no longer holds: " + "; ".join(faults)) if faults else None


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
    # the site's score and band depend on weightings the reader may have changed; the written
    # text rests on what is published, never on them
    if re.search(r"\bscore[sd]?\b|\bband [A-E]\b|\bbands?\b", text, re.I):
        faults.append("mentions the site's score or band, which depend on the reader's weightings")
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
