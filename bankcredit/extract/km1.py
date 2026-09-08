"""KM1 key-metrics extractor for Pillar 3 PDFs. Rules only, no AI service.

The UK, EU and Basel KM1 templates share their row numbering, so the extractor
walks the text of the page(s) that hold the template, keys each row on its
number, confirms it with a label pattern, and reads the current-period column.
Every result carries a list of validation findings; the caller decides whether a
result is loaded, loaded as unverified, or sent to the review queue.

    from bankcredit.extract import km1
    res = km1.extract("skipton.pdf")
    res.values["cet1_ratio"], res.reference_date, res.page, res.checks

Layout assumptions (checked against UK banks and building societies):
  * the row number is on its own line or starts the label line ("UK 11a Overall ...");
  * the label may wrap onto several lines; the values follow as numeric tokens,
    one per period column, current period first unless the header dates say otherwise;
  * amounts are in millions unless the page says thousands or billions.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date

import fitz  # PyMuPDF

# ---- template rows -------------------------------------------------------
# row number -> (metric, label pattern, kind). kind: amount | pct
ROWS = {
    "1": ("cet1_capital", r"(common equity tier ?1|cet ?1)(?!.*ratio)", "amount"),
    "2": ("tier1_capital", r"^(?:total )?tier ?1\b(?!.*ratio)", "amount"),
    "3": ("total_capital", r"^total (?:own funds|capital)(?!.*ratio)", "amount"),
    "4": ("rwa", r"risk[- ]?weighted|rwea|rwa", "amount"),
    "5": ("cet1_ratio", r"(common equity tier ?1|cet ?1).*ratio|cet ?1.*\(%\)", "pct"),
    "6": ("tier1_ratio", r"^tier ?1 (?:capital )?ratio", "pct"),
    "7": ("total_capital_ratio", r"total (?:capital|own funds) ratio", "pct"),
    "7d": ("total_srep_requirement", r"total srep", "pct"),
    "11": ("combined_buffer", r"combined buffer|total.*buffer", "pct"),
    "11a": ("overall_capital_requirement", r"overall capital requirement", "pct"),
    "12": ("cet1_headroom", r"cet ?1 available|available after", "pct"),
    "13": ("leverage_exposure", r"exposure measure|leverage.*exposure", "amount"),
    "14": ("leverage_ratio", r"leverage ratio", "pct"),
    "15": ("hqla", r"hqla|high[- ]quality liquid", "amount"),
    "16": ("net_cash_outflows", r"net cash outflow", "amount"),
    "17": ("lcr", r"liquidity coverage|lcr", "pct"),
    "18": ("available_stable_funding", r"available stable funding", "amount"),
    "19": ("required_stable_funding", r"required stable funding", "amount"),
    "20": ("nsfr", r"net stable funding|nsfr", "pct"),
}
# Strict label patterns for tables that carry no row numbers. Applied to a normalised
# label (lower case, parentheticals and footnote marks removed). Order matters: the
# first pattern that matches an unfilled metric wins, so specific rows come first.
LABEL_ROWS = [
    ("cet1_headroom", r"^cet ?1 available after"),
    ("cet1_ratio", r"^(?:common equity tier ?1|cet ?1)(?: capital)? ratio$"),
    ("tier1_ratio", r"^tier ?1(?: capital)? ratio$"),
    ("total_capital_ratio", r"^total capital ratio$"),
    ("cet1_capital", r"^(?:total )?(?:common equity tier ?1|cet ?1)(?: capital)?$"),
    ("tier1_capital", r"^(?:total )?tier ?1(?: capital)?$"),
    ("total_capital", r"^total capital$"),
    ("rwa", r"^(?:total )?risk[- ]?w ?eighted (?:exposure amounts?|assets)|^total (?:rweas?|rwas?)$"),
    ("total_srep_requirement", r"^total srep own funds requirements?$"),
    ("overall_capital_requirement", r"^overall capital requirements?$"),
    ("leverage_exposure", r"^(?:uk )?(?:total exposure measure|leverage(?: ratio)? (?:total )?exposure(?: measure)?)"),
    ("leverage_ratio", r"^(?:uk )?leverage ratio(?: excluding claims on central banks)?$"),
    ("hqla", r"^total high[- ]?quality liquid assets"),
    ("net_cash_outflows", r"^total net cash outflows?"),
    ("lcr", r"^liquidity coverage ratio$"),
    ("available_stable_funding", r"^total available stable funding$"),
    ("required_stable_funding", r"^total required stable funding$"),
    ("nsfr", r"^(?:net stable funding ratio|nsfr(?: ratio)?)$"),
]
KIND = {m: k for _, (m, _, k) in ROWS.items()}
KIND["tier1_leverage"] = "pct"
CORE = ("cet1_capital", "rwa", "cet1_ratio", "leverage_ratio")
# metrics that go to the facts table (the rest are kept in the document record only)
PUBLISH = ("cet1_capital", "tier1_capital", "total_capital", "rwa", "cet1_ratio", "tier1_ratio",
           "total_capital_ratio", "overall_capital_requirement", "leverage_exposure", "leverage_ratio",
           "lcr", "nsfr", "tier1_leverage")
BOUNDS = {"cet1_ratio": (3, 80), "tier1_ratio": (3, 80), "total_capital_ratio": (3, 90),
          "leverage_ratio": (1.5, 40), "lcr": (60, 2500), "nsfr": (60, 1200),
          "overall_capital_requirement": (6, 30), "total_srep_requirement": (3, 25),
          "combined_buffer": (0, 15), "cet1_headroom": (0, 70)}

NUM_RE = re.compile(r"^\(?[-–]?[£$€]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?$|^\(?[-–]?\d+\.\d+\)?%?$|^\(?[-–]?\d{3,}\)?%?$")
DASH_RE = re.compile(r"^(?:[-–—]+%?|n/?a|nm|n\.a\.)$", re.I)
STRONG_RE = re.compile(r"[,.%()]|\d{3}")   # a real cell value, as opposed to a row or page number
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_MONTH_AHEAD = r"(?![ \t./-]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))"


def _year_group(tag: str) -> str:
    """A four-digit year may sit on the next line; a two-digit year must share the line with its month
    and must not be followed on that line by another month name ("June 31 December")."""
    return r"(?:[\s./,'-]*(?P<y4" + tag + r">\d{4})|[ \t./,'-]*(?P<y2" + tag + r">\d{2}" + _MONTH_AHEAD + r"))\b"


# One scanner with ordered alternatives, so "Mar-26" is read as month-year before "26 Dec" could be read as a day.
DATE_SCAN = re.compile(
    r"\b(?P<d1>\d{1,2})\s?(?:st|nd|rd|th)?[\s./-]?" + MON.replace("(", "(?P<m1>", 1) + r"\.?" + _year_group("a")
    + r"|\b(?P<d2>\d{1,2})[./](?P<m2>\d{1,2})[./](?P<y2>\d{4}|\d{2})\b"      # 31.12.25 and UBS's 30.6.26
    + r"|\b" + MON.replace("(", "(?P<m4>", 1) + r"\s+(?P<d4>\d{1,2})(?!\d)[,.]?" + _year_group("c")
    + r"|\b" + MON.replace("(", "(?P<m3>", 1) + _year_group("b")
    + r"|\b(?P<qh>[QH])(?P<n>[1-4])\s?[-']?\s?(?P<y4>\d{4}|\d{2})\b", re.I)
CURRENCY = [("£", "GBP"), ("A$", "AUD"), ("C$", "CAD"), ("S$", "SGD"), ("HK$", "HKD"), ("US$", "USD"),
            ("$", "USD"), ("€", "EUR"), ("¥", "JPY"), ("AED", "AED"), ("QAR", "QAR"), ("CHF", "CHF"),
            ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP")]      # codes, as in UBS's "USD m"


@dataclass
class Result:
    values: dict = field(default_factory=dict)         # metric -> float (pct or currency millions)
    rows_found: dict = field(default_factory=dict)     # row number -> raw label
    page: int | None = None                            # 1-based page of the template
    pages: list = field(default_factory=list)
    reference_date: date | None = None
    period_dates: list = field(default_factory=list)   # header dates as parsed, in column order
    currency: str = ""
    scale: float = 1.0                                 # multiplier applied to raw amounts -> millions
    checks: list = field(default_factory=list)         # (severity, message); severity error|warn
    template: str = ""                                 # UK KM1 | EU KM1 | KM1 | US Pillar 3 | US LCR
    fixed_confidence: float | None = None              # set by extractors with their own scale (US documents)
    history: dict = field(default_factory=dict)
    derived: set = field(default_factory=set)          # metrics computed from others rather than read        # prior-period columns: iso date -> {metric: value}
    confidence_bonus: float = 0.0                      # continuity with the last verified disclosure

    @property
    def ok(self) -> bool:
        """No validation errors and the capital rows present; a missing leverage row is an error only
        where the template requires it (validate() decides), so it is not re-checked here."""
        if self.template.startswith("US"):
            return not any(s == "error" for s, _ in self.checks) and bool(self.values)
        return not any(s == "error" for s, _ in self.checks) and all(m in self.values for m in ("cet1_capital", "rwa", "cet1_ratio"))

    @property
    def confidence(self) -> float:
        if self.fixed_confidence is not None:
            return self.fixed_confidence
        if not self.values:
            return 0.0
        errors = sum(1 for s, _ in self.checks if s == "error")
        warns = sum(1 for s, _ in self.checks if s == "warn")
        core_missing = sum(1 for m in CORE if m not in self.values)
        return max(0.0, min(0.98, round(0.95 - 0.3 * errors - 0.08 * warns - 0.1 * core_missing + self.confidence_bonus, 2)))


# ---- helpers -------------------------------------------------------------
def _norm_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")      # £’000 is £'000
    return re.sub(r"(\d)\s+%", r"\1%", text)


# Rows printed beside a base row on a different basis. The template asks for the base row, so
# these are never read: "fully loaded" next to the transitional figure, "pre-floor" next to the
# floored one (the Hong Kong and Basel 3.1 layouts), the pre-IFRS 9 comparatives.
VARIANT_RE = re.compile(r"fully[- ]loaded|fully[- ]phased|ecl accounting model|pre[- ]ifrs ?9|"
                        r"pre[- ]?floor|floor[- ]adjusted|excluding (?:the )?(?:ifrs ?9|ecl)", re.I)


def _norm_label(label: str) -> str:
    low = _norm_text(label).lower()
    # (CET1), (£m), (%), (a), and a footnote marker glued to the bracket: "CET1 ratio (%)3"
    low = re.sub(r"\([^)]*\)\d{0,2}", " ", low)
    low = re.sub(r"(?<=[a-z])(?<!cet)(?<!tier)(?<!\bat)(?<!\bt)\d\b", "", low)   # footnote digit glued to a word: capital1
    low = re.sub(r"[^a-z0-9 /-]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    return low


def _num(tok: str) -> float | None:
    if re.fullmatch(r"\(\d{1,2}\)", tok.strip()):
        return None                                  # footnote reference, not a negative value
    t = tok.strip().replace("£", "").replace("$", "").replace("€", "").replace("–", "-").replace("—", "-")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").rstrip("%").replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _tokens(line: str) -> list[str]:
    return [t for t in re.split(r"\s+", line.strip()) if t]


def _is_num_tok(t: str) -> bool:
    return bool(NUM_RE.match(t)) and t.count("(") == t.count(")")


def _is_value_line(line: str) -> bool:
    toks = _tokens(line)
    return bool(toks) and all(_is_num_tok(t) or DASH_RE.match(t) for t in toks)


def _year(y: str) -> int:
    y = int(y)
    return y + 2000 if y < 100 else y


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def fiscal_quarter_end(year: int, n: int, year_end: str = "12-31") -> date:
    """End of quarter n of the fiscal year ending on year_end of `year`."""
    ye_m, ye_d = (int(x) for x in year_end.split("-"))
    if (ye_m, ye_d) == (12, 31):
        return _month_end(year, 3 * n)
    y, m = year, ye_m - (4 - n) * 3
    while m < 1:
        m += 12; y -= 1
    if ye_d >= 28:
        return _month_end(y, m)
    d = date(y, m, min(ye_d, calendar.monthrange(y, m)[1]))
    return d if d.day >= 15 else _month_end(d.year, d.month - 1)


def parse_dates(text: str, explicit_only: bool = False, year_end: str = "12-31") -> list[date]:
    """All period-like dates in reading order, de-duplicated, without sorting.

    explicit_only skips the Q1 2026 / H1 2026 forms, whose meaning depends on the year end;
    otherwise those forms are read against year_end (fiscal quarters for October year ends etc.).
    """
    out: list[date] = []
    for m in DATE_SCAN.finditer(text):
        g = m.groupdict()
        try:
            if g["d1"]:
                d = date(_year(g["y4a"] or g["y2a"]), MONTHS[g["m1"].lower()[:3]], int(g["d1"]))
            elif g["d2"]:
                d = date(_year(g["y2"]), int(g["m2"]), int(g["d2"]))
            elif g["d4"]:
                d = date(_year(g["y4c"] or g["y2c"]), MONTHS[g["m4"].lower()[:3]], int(g["d4"]))
            elif g["m3"]:
                d = _month_end(_year(g["y4b"] or g["y2b"]), MONTHS[g["m3"].lower()[:3]])
            else:
                if explicit_only:
                    continue
                n, y = int(g["n"]), _year(g["y4"])
                if g["qh"].upper() == "Q":
                    d = fiscal_quarter_end(y, n, year_end)
                elif n in (1, 2):
                    d = fiscal_quarter_end(y, 2 * n, year_end)
                else:
                    continue
        except (ValueError, KeyError):
            continue
        if 2005 <= d.year <= date.today().year + 1 and d not in out:
            out.append(d)
    return out


DAY_MONTH = re.compile(r"\b(\d{1,2})\s+" + MON + r"\b(?![\s,.]*\d{4})", re.I)
YEAR_ONLY = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def join_split_headers(cells: str, year_end: str = "12-31") -> tuple[list[date], int]:
    """Column headers read in order, pairing a day-month printed on one line with the year printed on a
    later line (NatWest and RBC print a block of day-months, then a block of years; Aldermore prints
    "30 June" / "2023" for the first column and full dates for the rest). Returns (dates, unresolved):
    unresolved counts day-months that never met a year, the sign of a header the reader cannot trust."""
    out: list[date] = []
    pending: list[tuple[int, int]] = []
    for l in cells.splitlines():
        t = l.strip()
        if not t:
            continue
        if re.fullmatch(r"(?:20\d{2}[\s,]*)+", t) or (pending and re.fullmatch(r"(?:\d{2}[\s,]*)+", t)):
            for y in re.findall(r"\d{4}|\d{2}", t):
                if not pending:
                    break
                y = int(y) if len(y) == 4 else 2000 + int(y)          # "31 Dec" over "22" (Co-operative Bank)
                dd, mm = pending.pop(0)
                d = date(y, mm, min(dd, calendar.monthrange(y, mm)[1]))   # "31 September" is a typo
                if d not in out:
                    out.append(d)
            continue
        t = re.sub(r"(\b\d{1,2}\s+" + MON + r"\s+\d{2})(\d)\b", r"\1", t, flags=re.I)   # "31 Dec 231": footnote glued to the year
        loose = DAY_MONTH.findall(t)
        full = parse_dates(t, year_end=year_end)
        if loose and not full:
            pending += [(int(dd), MONTHS[mm.lower()[:3]]) for dd, mm in loose]
        for d in full:
            if d not in out:
                out.append(d)
    return out, len(pending)


def _is_cell_line(line: str) -> bool:
    """A column-header cell: dates or short labels, not narrative text."""
    rest = DATE_SCAN.sub(" ", line)
    words = [t for t in _tokens(rest) if re.search(r"[a-z]{3,}", t, re.I)]
    return len(words) <= 2 and len(_tokens(line)) <= 24


def detect_units(text: str) -> tuple[str, float]:
    head = text[:4000]
    low = head.lower()
    scale = 1.0
    # the unit statement nearest the top of the table wins: RBC's "(Millions of Canadian dollars)" header
    # must not lose to "RWA increased by $29 billion" in the commentary below it
    hits = [(m.start(), sc) for pat, sc in ((r"[£$€]\s?'?\s?000s?\b|\bthousands?\b|\(000s?\)", 0.001),
                                           (r"[£$€]\s?m\b|\bmillions?\b|\(m\)|\bmn\b", 1.0),
                                           (r"[£$€]\s?bn\b|\bbillions?\b", 1000.0))
            for m in [re.search(pat, low)] if m]
    if hits:
        scale = min(hits)[1]
    ccy = ""
    for sym, code in CURRENCY:
        if sym.lower() in low:
            ccy = code
            break
    return ccy, scale


# ---- row parsing ---------------------------------------------------------
BARE_ROW_RE = re.compile(r"^(?:(?:UK|EU|CAN|AU|SG)\s?-?\s?)?(\d{1,2})\s?([a-h])?$", re.I)
INLINE_ROW_RE = re.compile(r"^(?:(?:UK|EU|CAN|AU|SG)\s?-?\s?)?(\d{1,2})\s?([a-h])?\s+([A-Za-z(].*)$", re.I)


def _row_key(m) -> str | None:
    key = (m.group(1) + (m.group(2) or "")).lower()
    if key in ROWS:
        return key
    if key in ("14a", "14b", "14c"):
        return key           # APRA/Basel leverage variants; used only when row 14 is absent
    return None


def _sub_row_marker(line: str) -> bool:
    """True for a numbered variant row the template does not track (1a, 2a, 5a: the fully loaded
    or ECL-transitional twins Barclays and others print under each base row). Such a line ends
    the row before it; its own values are never read."""
    line = line.strip()
    m = BARE_ROW_RE.match(line) or (INLINE_ROW_RE.match(line) if not _is_value_line(line) else None)
    return bool(m and m.group(2) and _row_key(m) is None)


def _row_start(lines: list[str], i: int) -> tuple[str, str, int] | None:
    """(row key, inline label, index of the first label line) if line i starts a template row, else None."""
    line = lines[i].strip()
    m = BARE_ROW_RE.match(line)
    if m:
        key = _row_key(m)
        if not key:
            return None
        j = i + 1
        # a second reference column (e.g. the LR2 row number) may sit between the KM1 number and the label
        if j + 1 < len(lines) and re.fullmatch(r"(?:UK|EU)?\s?-?\d{1,2}[a-h]?", lines[j].strip(), re.I) and not _is_value_line(lines[j + 1]) and not BARE_ROW_RE.match(lines[j + 1].strip()):
            j += 1
        if j < len(lines) and not _is_value_line(lines[j]) and not BARE_ROW_RE.match(lines[j].strip()):
            return key, "", j
        return None
    m = INLINE_ROW_RE.match(line)
    if m and not _is_value_line(line):
        key = _row_key(m)
        if key:
            return key, m.group(3).strip(), i + 1
    return None


def parse_rows(lines: list[str]) -> tuple[dict, dict]:
    """Return {row_no: [raw values...]} and {row_no: label} from text lines in reading order.

    A row is kept only when its label confirms the template row, and the first
    confirmed occurrence wins, so page numbers and repeated tables do not clobber it.
    """
    entries: list[tuple[str, str, list[str]]] = []
    i, n = 0, len(lines)
    current = None
    while i < n:
        line = lines[i].strip()
        start = _row_start(lines, i)
        if start:
            key, label, i = start
            while i < n and not _is_value_line(lines[i]) and not _row_start(lines, i) and not _sub_row_marker(lines[i]):
                label = (label + " " + lines[i].strip()).strip()
                i += 1
            if i < n and _sub_row_marker(lines[i]):
                entries.append([key, label, []])   # base row printed without values here; its twin's are not ours
                i += 1
                continue
            # values printed on the label line itself: "NSFR ratio (%) 112.1% 113.3%"
            toks = _tokens(label)
            while toks and re.fullmatch(r"\(\d{1,2}\)|\d", toks[-1]):
                toks.pop()                       # footnote references: "(3)", "1"
            k = len(toks)
            while k > 0 and (_is_num_tok(toks[k - 1]) or DASH_RE.match(toks[k - 1])):
                k -= 1
            inline = toks[k:] if k < len(toks) and any(STRONG_RE.search(t) for t in toks[k:]) else []
            if inline:
                label = " ".join(toks[:k])
            current = [key, label, list(inline)]
            entries.append(current)
            continue
        if current and _is_value_line(line):
            toks = _tokens(line)
            if not current[2] and not any(STRONG_RE.search(t) or DASH_RE.match(t) for t in toks):
                current = None       # a bare small integer is a row or page number, not a value
            else:
                current[2].extend(toks)
        elif current and line:
            current = None  # a non-numeric line ends the row (section header or note)
        i += 1
    values: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    for key, label, vals in entries:
        if key in values or not vals or not _confirm(key, label):
            continue
        values[key] = vals
        labels[key] = label
    for alt in ("14a", "14b", "14c"):
        if alt in values:
            if "14" not in values:
                values["14"], labels["14"] = values[alt], labels[alt]
            del values[alt], labels[alt]
    return values, labels


def _confirm(row: str, label: str) -> str | None:
    """Metric for the row if the label agrees, else None."""
    spec = ROWS.get(row) or (ROWS.get("14") if row in ("14a", "14b", "14c") else None)
    if not spec:
        return None
    metric, pat, _ = spec
    low = re.sub(r"\s+", " ", _norm_text(label).lower()).strip()
    if metric in ("cet1_ratio", "tier1_ratio", "total_capital_ratio") and "ratio" not in low and "srep" not in low:
        # HSBC style: rows 5-7 labelled just "CET1", "Tier 1", "Total capital" under a "Capital ratios" heading
        short = {"cet1_ratio": r"^(?:common equity tier ?1|cet ?1)(?: capital)?$", "tier1_ratio": r"^tier ?1(?: capital)?$",
                 "total_capital_ratio": r"^total capital$"}[metric]
        return metric if re.search(short, _norm_label(low)) else None
    if metric == "rwa":
        pat = r"total.*risk[- ]?w ?eighted|risk[- ]?w ?eighted (?:exposure amount|assets)|\brweas?\b|\brwas?\b"
    if re.search(pat, low):
        if re.search(r"\bnotes?\b$|pillar 3|page \d|overview|key metrics|template|annex|contents", low):
            return None
        if VARIANT_RE.search(low):
            return None          # the base row is the one the template asks for
        # disambiguate ratio rows that share words
        if metric == "tier1_ratio" and re.search(r"common equity|cet", low):
            return None
        if metric in ("cet1_capital", "tier1_capital", "total_capital") and "ratio" in low:
            return None
        return metric
    return None


def parse_by_label(lines: list[str]) -> dict[str, list[str]]:
    """{metric: [raw values...]} for tables without row numbers, matching normalised labels."""
    out: dict[str, list[str]] = {}
    i, n = 0, len(lines)
    while i < n:
        line = _norm_text(lines[i]).strip()
        if not line or _is_value_line(line):
            i += 1
            continue
        # allow a wrapped label: try the line alone, then joined with the next non-value line
        cands = [line]
        if i + 1 < n and not _is_value_line(lines[i + 1]):
            cands.append(line + " " + _norm_text(lines[i + 1]).strip())
        hit, used = None, 1
        for k, cand in enumerate(cands):
            if VARIANT_RE.search(cand):
                continue         # normalising strips the qualifier, so it has to be caught here
            nl = _norm_label(cand)
            for metric, pat in LABEL_ROWS:
                if metric not in out and re.search(pat, nl):
                    hit, used = metric, k + 1
                    break
            if hit:
                break
        if not hit:
            i += 1
            continue
        j = i + used
        # OSFI layout: the row number follows the label, and currency signs sit on their own lines
        if j < n and re.fullmatch(r"\d{1,2}[a-e]?", lines[j].strip()) and j + 1 < n and (_is_value_line(lines[j + 1]) or lines[j + 1].strip() in ("$", "£", "€")):
            j += 1
        vals: list[str] = []
        while j < n and (_is_value_line(lines[j]) or lines[j].strip() in ("$", "£", "€")):
            if lines[j].strip() not in ("$", "£", "€"):
                vals.extend(_tokens(lines[j]))
            j += 1
        if vals and not any(STRONG_RE.search(t) or DASH_RE.match(t) for t in vals[:1]):
            vals = []
        if vals:
            out[hit] = vals
            i = j
        else:
            i += 1
    return out


def page_score(text: str) -> int:
    lines = [l for l in text.splitlines() if l.strip()]
    vals, labels = parse_rows(lines)
    numbered = sum(1 for r, v in vals.items() if v and _confirm(r, labels.get(r, "")))
    return max(numbered, len(parse_by_label(lines)))


# ---- main entry ----------------------------------------------------------
OCR_MIN_CHARS = 80      # a page with less text than this, in a document that is mostly like that, is an image


def page_texts(doc, max_pages: int) -> tuple[list[str], bool]:
    """Text of the first pages; image-only documents are read with Tesseract when it is installed.
    Returns (texts, ocr_used)."""
    n = min(doc.page_count, max_pages)
    texts = [doc[i].get_text("text") for i in range(n)]
    thin = sum(1 for t in texts if len(t.strip()) < OCR_MIN_CHARS)
    if n and thin >= max(1, n - 2):                # nearly every page has no text layer: scanned or outlined fonts
        try:
            for i in range(n):
                if len(texts[i].strip()) < OCR_MIN_CHARS:
                    page = doc[i]
                    tp = page.get_textpage_ocr(language="eng", dpi=220, full=True)
                    texts[i] = page.get_text(textpage=tp)
            return texts, True
        except Exception as exc:                    # no Tesseract on this machine: the document stays unread
            log_ocr(exc)
    return texts, False


def log_ocr(exc) -> None:
    import logging
    logging.getLogger("bankcredit.extract").warning("OCR unavailable or failed (%s); install tesseract-ocr to read image-only PDFs", exc)


# Far enough in to reach KM1 in a full annual Pillar 3 report: CBA prints it on page 116 of 137,
# and a 40-page budget saw only the contents page, whose page numbers read as a capital table.
def extract(pdf_path: str, hint_date: date | None = None, max_pages: int = 250, currency_hint: str = "",
            year_end: str = "12-31", page_hint: int | None = None) -> Result:
    res = Result()
    doc = fitz.open(pdf_path)
    raw_texts, ocr = page_texts(doc, max_pages)
    texts = [_norm_text(t) for t in raw_texts]
    if ocr:
        res.checks.append(("warn", "text recovered by OCR from an image-only document"))
    scores = [page_score(t) for t in texts]
    # best page: KM1 wording plus parsable rows; a table without wording needs a high score
    scored = []
    for i, t in enumerate(texts):
        # A contents page lists "KM1 Key metrics ... 12" and scores like the template, but its
        # numbers are page numbers: read as a table it puts ratios in the capital rows.
        if re.search(r"\bContents\b", t[:400], re.I):
            continue
        worded = bool(re.search(r"\bKM ?1\b|key (?:prudential |regulatory )?metrics", t, re.I))
        if (worded and scores[i] >= 3) or scores[i] >= 8:
            scored.append((scores[i] + (1 if worded else 0), -i, i))
    # a page the reviewer confirmed last time (1-based) wins when it, or a neighbour, still looks like the template
    if page_hint and 0 < page_hint <= len(texts):
        near = [(scores[i] + 2, -i, i) for i in range(max(0, page_hint - 3), min(len(texts), page_hint + 2)) if scores[i] >= 2]
        if near:
            scored = near + [s for s in scored if s[2] not in {n[2] for n in near}]
    if not scored:
        res.checks.append(("error", "no KM1 page found"))
        return res
    scored.sort(reverse=True)
    best = scored[0][2]
    pages = [best]
    # the template may start on the previous page or continue on the next
    best_rows, _ = parse_rows([x for x in texts[best].splitlines() if x.strip()])
    if best > 0 and "1" not in best_rows and not re.search(r"\bKM ?2\b|\bOV1\b|Contents", texts[best - 1][:400]):
        prev_rows, _ = parse_rows([x for x in texts[best - 1].splitlines() if x.strip()])
        if "1" in prev_rows and len(prev_rows) >= 2:
            pages.insert(0, best - 1)
    if best + 1 < len(texts) and scores[best + 1] >= 2 and not re.search(r"\bKM ?2\b|\bOV1\b", texts[best + 1][:400]):
        pages.append(best + 1)
    res.page, res.pages = best + 1, [p + 1 for p in pages]
    text = "\n".join(texts[p] for p in pages)
    res.template = "UK KM1" if re.search(r"UK[ -]?KM ?1", text) else ("EU KM1" if re.search(r"EU[ -]?KM ?1", text) else "KM1")

    lines = [l for l in text.splitlines() if l.strip()]
    raw, labels = {}, {}
    by_label: dict[str, list[str]] = {}
    for p in pages:
        plines = [x for x in texts[p].splitlines() if x.strip()]
        v, l = parse_rows(plines)
        for k in v:
            if k not in raw:
                raw[k], labels[k] = v[k], l[k]
        for m, vals in parse_by_label(plines).items():
            by_label.setdefault(m, vals)
    # header dates: everything before row 1 on the page that holds row 1 (or the top of the best page)
    header = ""
    for p in pages:
        plines = [x for x in texts[p].splitlines() if x.strip()]
        k = next((k for k in range(len(plines)) if (_row_start(plines, k) or ("",))[0] == "1"), None)
        if k:
            header = "\n".join(plines[:k])
            break
    if not header:
        plines = [x for x in texts[best].splitlines() if x.strip()]
        k = next((k for k, l in enumerate(plines) if re.search(r"common equity tier|cet ?1", l, re.I)), 25)
        header = "\n".join(plines[:k])
    # column dates: short header cells first, then date-only lines anywhere on the pages, then narrative text
    cells = "\n".join(l for l in header.splitlines() if _is_cell_line(l))
    res.period_dates = parse_dates(cells, year_end=year_end)
    joined, unresolved = join_split_headers(cells, year_end)
    if len(joined) > len(res.period_dates):
        res.period_dates = joined            # day-month lines and year lines printed as two blocks
    if not res.period_dates:
        standalone = [l.strip() for l in lines if len(l.strip()) <= 20 and parse_dates(l, year_end=year_end)]
        res.period_dates = parse_dates("\n".join(standalone), year_end=year_end)
    narrative = False
    if not res.period_dates:
        found = parse_dates(header, year_end=year_end)
        if found:
            # narrative text: the date after "as at" / "as of" / "ended" names the period; otherwise the latest date
            m = re.search(r"\b(?:as at|as of|at|ended|ending|period end(?:ed)?)\s+(\d{1,2}\s+" + MON + r"\.?\s+\d{2,4}|" + MON + r"\s+\d{1,2},?\s+\d{4})", _norm_text(header), re.I)
            named = parse_dates(m.group(1), year_end=year_end) if m else []
            first = named[0] if named else max(found)
            res.period_dates = [first] + [d for d in found if d != first]
            narrative = True
            res.checks.append(("warn", "reference date taken from narrative text, not a column header"))
    descending = True
    if len(res.period_dates) >= 2 and res.period_dates[0] < res.period_dates[1]:
        descending = False
    if unresolved:
        res.checks.append(("warn", "column headers split month and year across lines; reference date needs a check"))
    res.currency, res.scale = detect_units(text)
    if currency_hint and (not res.currency or (res.currency == "USD" and currency_hint != "USD" and "US$" not in text)):
        res.currency = currency_hint

    picked: list[tuple[str, list[str], str]] = []
    for row, toks in raw.items():
        metric = _confirm(row, labels.get(row, ""))
        if metric and toks and metric not in {m for m, _, _ in picked}:
            picked.append((metric, toks, row))
    numbered = {m for m, _, _ in picked}
    for metric, toks in by_label.items():
        if metric not in numbered:
            picked.append((metric, toks, "label"))
    if picked and not numbered:
        res.checks.append(("warn", "rows identified by label only (no row numbers in the table)"))
    res.history = {} if narrative else prior_columns(picked, res.period_dates, descending, res.scale)   # narrative dates are not columns
    for metric, toks, row in picked:
        kind = KIND[metric]
        pick = toks[0] if descending else toks[-1]
        if DASH_RE.match(pick):
            continue
        v = _num(pick)
        if v is None:
            continue
        if kind == "amount":
            v = v * res.scale
        else:
            if 0 < v < 1.0 and metric in ("cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "lcr", "nsfr"):
                v = v * 100
                res.checks.append(("warn", f"{metric}: value read as a fraction and scaled to percent"))
        res.values[metric] = v
        res.rows_found[row] = labels.get(row, metric)

    # reference date
    split_header = any("split month and year" in m for _, m in res.checks)
    if res.period_dates and not (split_header and hint_date):
        res.reference_date = res.period_dates[0] if descending else res.period_dates[-1]
        if hint_date and abs((res.reference_date - hint_date).days) > 45:
            # the file name is weak evidence and the header is direct; keep the header's date but say so
            res.checks.append(("warn", f"header date {res.reference_date} disagrees with expected {hint_date}"))
    elif split_header and hint_date:
        res.reference_date = hint_date
    elif hint_date:
        res.reference_date = hint_date
        res.checks.append(("warn", "no period date found in the template header; using the expected date"))
    else:
        res.checks.append(("error", "no reference date"))

    validate(res)
    return res


def _cell(metric: str, tok: str, scale: float) -> float | None:
    if DASH_RE.match(tok):
        return None
    v = _num(tok)
    if v is None:
        return None
    if KIND[metric] == "amount":
        return v * scale
    if 0 < v < 1.0 and metric in ("cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "lcr", "nsfr"):
        return v * 100
    return v


def prior_columns(picked: list, period_dates: list, descending: bool, scale: float) -> dict:
    """The template's earlier columns (T-1 ... T-4) as {iso date: {metric: value}}.

    A row contributes only when it carries exactly one value per header date, so a stray footnote or a
    merged cell cannot shift a value into the wrong period. Each prior column must pass the same
    capital arithmetic as the current one before it is kept."""
    if len(period_dates) < 2:
        return {}
    dates = list(period_dates) if descending else list(reversed(period_dates))
    out: dict[str, dict] = {}
    for metric, toks, _row in picked:
        if len(toks) != len(dates):
            continue
        cols = list(toks) if descending else list(reversed(toks))
        for d, tok in zip(dates[1:], cols[1:]):
            v = _cell(metric, tok, scale)
            if v is not None:
                out.setdefault(d.isoformat(), {})[metric] = v
    keep = {}
    for d, vals in out.items():
        if "cet1_capital" in vals and "rwa" in vals and "cet1_ratio" in vals and vals["rwa"]:
            if abs(vals["cet1_capital"] / vals["rwa"] * 100 - vals["cet1_ratio"]) > 0.35:
                continue
        if any(not (0 < vals[m] < 80) for m in ("cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio") if m in vals):
            continue
        if any(not (20 < vals[m] < 1000) for m in ("lcr", "nsfr") if m in vals):
            continue
        keep[d] = vals
    return keep


def validate(res: Result) -> None:
    v = res.values
    # a table stating capital and RWA but omitting the ratio row (SMFG's single-table KM1) gives the
    # ratio exactly; it is recorded as derived so a profile can say where the figure came from
    for cap, ratio in (("cet1_capital", "cet1_ratio"), ("tier1_capital", "tier1_ratio"), ("total_capital", "total_capital_ratio")):
        if ratio not in v and cap in v and v.get("rwa"):
            implied = round(v[cap] / v["rwa"] * 100, 2)
            lo, hi = BOUNDS.get(ratio, (3, 80))
            # only derive a figure the validator would accept: a capital row misread as a ratio
            # gives an implied value near zero, and deriving it manufactures an error downstream
            if lo <= implied <= hi:
                v[ratio] = round(implied, 2)
                res.derived.add(ratio)
                res.checks.append(("info", f"{ratio} derived from {cap} over RWA"))
    for m in CORE:
        if m not in v:
            if m == "leverage_ratio" and res.template == "KM1":
                res.checks.append(("info", "no leverage ratio row (not all Basel KM1 filers disclose one)"))
            else:
                res.checks.append(("error", f"missing core row {m}"))
    if "lcr" not in v:
        res.checks.append(("info", "no LCR row (not disclosed at this level, or not read)"))
    for m, (lo, hi) in BOUNDS.items():
        if m in v and not (lo <= v[m] <= hi):
            res.checks.append(("error", f"{m} {v[m]:g} outside {lo}..{hi}"))

    def close(a, b, tol):
        return a in v and b in v and abs(v[a] - v[b]) <= tol

    if "cet1_capital" in v and "rwa" in v and "cet1_ratio" in v and v["rwa"]:
        implied = v["cet1_capital"] / v["rwa"] * 100
        if abs(implied - v["cet1_ratio"]) > 0.35:
            res.checks.append(("error", f"cet1_ratio {v['cet1_ratio']:.2f} vs implied {implied:.2f} from capital/RWA"))
        else:
            # capital, RWA and the ratio agree: rows matched by label alone are confirmed by arithmetic
            res.checks = [("info", m + "; confirmed by capital arithmetic") if s == "warn" and m.startswith("rows identified by label only") else (s, m)
                          for s, m in res.checks]
    if "tier1_capital" in v and "leverage_exposure" in v and "leverage_ratio" in v and v["leverage_exposure"]:
        implied = v["tier1_capital"] / v["leverage_exposure"] * 100
        if v["leverage_ratio"] and 800 < implied / v["leverage_ratio"] < 1250:
            v["leverage_exposure"] *= 1000
            implied /= 1000
            res.checks.append(("warn", "leverage_exposure was in billions; scaled to millions"))
        if abs(implied - v["leverage_ratio"]) > 0.6:
            res.checks.append(("warn", f"leverage_ratio {v['leverage_ratio']:.2f} vs implied {implied:.2f}"))
    if "hqla" in v and "net_cash_outflows" in v and "lcr" in v and v["net_cash_outflows"]:
        implied = v["hqla"] / v["net_cash_outflows"] * 100
        if abs(implied - v["lcr"]) > 5:
            res.checks.append(("warn", f"lcr {v['lcr']:.1f} vs implied {implied:.1f}"))
    if "available_stable_funding" in v and "required_stable_funding" in v and "nsfr" in v and v["required_stable_funding"]:
        implied = v["available_stable_funding"] / v["required_stable_funding"] * 100
        if abs(implied - v["nsfr"]) > 3:
            res.checks.append(("warn", f"nsfr {v['nsfr']:.1f} vs implied {implied:.1f}"))
    if "cet1_ratio" in v and "tier1_ratio" in v and v["tier1_ratio"] < v["cet1_ratio"] - 0.05:
        res.checks.append(("error", "tier1_ratio below cet1_ratio"))
    if "tier1_ratio" in v and "total_capital_ratio" in v and v["total_capital_ratio"] < v["tier1_ratio"] - 0.05:
        res.checks.append(("error", "total_capital_ratio below tier1_ratio"))
    if "cet1_capital" in v and "tier1_capital" in v and v["tier1_capital"] < v["cet1_capital"] - 0.5:
        res.checks.append(("error", "tier1_capital below cet1_capital"))
    if not res.currency:
        res.checks.append(("warn", "currency not detected"))
