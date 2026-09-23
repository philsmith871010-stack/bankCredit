"""One rating from three, and nothing that names an agency.

The site shows the average and the weakest of the long-term ratings the three main agencies
hold on a name, on one scale, and how many of them have the name on a positive or negative
outlook or watch. It does not say which agency said what. A rating shown with its agency's name
on it is that agency's product, and republishing it needs a licence from the agency; an average
and a count are ours, worked out from a public register (docs/ratings-composite.md). Fitch,
S&P and Moody's are the three because a treasury policy is written around those three, and a
fourth agency that rates a handful of the covered names would move the average of some banks
and not others.

Everything a page shows about a rating comes through here: the letters are the site's own
notation for a position on the scale, never an agency's symbol, so an A3 is shown as A- and
nothing on the page says whose A- it was.
"""
from __future__ import annotations

AGENCIES = ("fitch", "sp", "moodys")
THREE = "the three main agencies"

# One numeric scale across agencies (1 = AAA/Aaa ... 10 = BBB-/Baa3 ... 17 = CCC and below), lower is stronger.
SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC"]
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
    return SCALE.index(v) + 1 if v in SCALE else None


def grade_letter(grade: float | None) -> str:
    """The site's letter for a position on the scale; a half sits with the weaker notch."""
    if grade is None:
        return ""
    return SCALE[max(0, min(16, int(grade + 0.5) - 1))]


# ---- tones ----------------------------------------------------------------------------------
# The register's outlook and watch labels, reduced to the five things a treasurer looks for.
TONES = ("watch negative", "negative", "watch positive", "positive", "stable")
TONE_RANK = {t: i for i, t in enumerate(TONES)}
TONE_RANK[""] = len(TONES)


def tone(outlook: str | None) -> str:
    """'watch negative' | 'negative' | 'watch positive' | 'positive' | 'stable' | '' (none published)."""
    o = (outlook or "").lower()
    if "watch" in o or "review" in o:
        return "watch negative" if "neg" in o or "down" in o else ("watch positive" if "pos" in o or "up" in o else "")
    if "neg" in o:
        return "negative"
    if "pos" in o:
        return "positive"
    if "stab" in o:
        return "stable"
    return ""


def sort_tones(tones) -> list[str]:
    """Worst first, so the glyphs read the same way on every page."""
    return sorted((tone(t) for t in tones), key=lambda t: TONE_RANK.get(t, 9))


NUMBER = {0: "none", 1: "one", 2: "two", 3: "three"}


def of_three(n: int, total: int = 3) -> str:
    """'all three', 'two of the three', 'one of the three', 'none of the three'."""
    if total == 3 and n == 3:
        return "all three"
    return f"{NUMBER.get(n, str(n))} of the three"


def tone_counts(tones) -> dict[str, int]:
    out = {t: 0 for t in TONES}
    out[""] = 0
    for t in tones:
        out[tone(t)] += 1
    return out


def tone_words(tones) -> str:
    """'two on a stable outlook and one on negative watch'; 'all three on a stable outlook' when
    they agree; '' when nothing is published."""
    tones = list(tones)
    counts = tone_counts(tones)
    parts = []
    for t in TONES:
        n = counts[t]
        if not n:
            continue
        who = NUMBER.get(n, str(n))
        if n == len(tones) and n > 1:
            who = "all three" if n == 3 else "both"
        if t.startswith("watch"):
            parts.append(f"{who} on {t.split()[1]} watch")
        else:
            parts.append(f"{who} on a {t} outlook")
    if counts[""] and parts:
        parts.append(f"{NUMBER.get(counts[''], str(counts['']))} with no outlook published")
    return _join(parts)


def _join(parts: list[str]) -> str:
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def composite(rows: list[dict]) -> dict | None:
    """The one record a page shows: from the three main agencies' headline long-term ratings.

    rows: [{agency, value, outlook, date}], one per agency. Agencies outside the three are
    ignored, not averaged in. None when none of the three rates the name.
    """
    held = [r for r in rows if r.get("agency") in AGENCIES and rating_grade(r.get("value")) is not None]
    if not held:
        return None
    grades = [rating_grade(r["value"]) for r in held]
    avg = round(sum(grades) / len(grades), 2)
    worst = max(grades)
    return {"n": len(held), "avg": avg, "worst": worst,
            "letter": grade_letter(avg), "worst_letter": grade_letter(worst),
            "tones": sort_tones(r.get("outlook") or "" for r in held),
            "date": max((str(r.get("date") or "")[:10] for r in held), default="")}


def describe(comp: dict | None) -> str:
    """'A on average across all three, the weakest of them at A-, two on a stable outlook and one on negative watch'."""
    if not comp:
        return f"no public rating from any of {THREE}"
    n = comp["n"]
    s = f"{comp['letter']} on average across {of_three(n)}"
    if n > 1 and comp["worst_letter"] != comp["letter"]:
        s += f", the weakest of them at {comp['worst_letter']}"
    tw = tone_words(comp.get("tones") or [])
    if tw:
        s += f", {tw}" if n > 1 else f", {tw.replace('one on', 'on')}"
    return s


# ---- what the register's own actions are called once the agency's name is off them -------------
def public_action(action: str, horizon: str = "long") -> str:
    """'Fitch upgrade: Long Term Issuer Default Rating A+' becomes 'One of the three agencies upgraded
    its long-term rating'. The value is left off: an agency's own symbol names the agency."""
    a = (action or "").lower().strip()
    h = "short-term" if str(horizon or "").lower().startswith("s") else "long-term"
    who = "One of the three agencies"
    if a.startswith("upgrade"):
        return f"{who} upgraded its {h} rating"
    if a.startswith("downgrade"):
        return f"{who} downgraded its {h} rating"
    if a.startswith("affirm"):
        return f"{who} affirmed its {h} rating"
    if a.startswith("withdraw"):
        return f"{who} withdrew its {h} rating"
    if a.startswith("new") or "initial" in a:
        return f"{who} assigned a new {h} rating"
    if a.startswith(("placed", "maintained", "removed")):
        verb = a.split()[0]
        rest = a.split("under", 1)[1].strip() if "under" in a else a
        return f"{who} {verb} its {h} rating under {rest}"
    return f"{who} took an action on its {h} rating"
