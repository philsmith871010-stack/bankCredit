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
    "4": ("rwa", r"risk\s?-?\s?weighted|rwea|rwa", "amount"),
    "5": ("cet1_ratio", r"(common equity tier ?1|cet ?1).*ratio|cet ?1.*\(%\)", "pct"),
    "6": ("tier1_ratio", r"^tier ?1 (?:capital )?ratio", "pct"),
    "7": ("total_capital_ratio", r"total (?:capital|own funds) ratio", "pct"),
    # Pillar 2A: the UK template's 7a is its CET1 part, the EU template's 7a the whole and 7b the CET1 part
    "7a": ("p2r_7a", r"additional|srep|own funds requirement", "pct"),
    "7b": ("p2r_7b", r"of which|additional|srep", "pct"),
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
    ("rwa", r"^(?:total )?risk\s?-?\s?w ?eighted (?:exposure amounts?|assets)|^total (?:rweas?|rwas?)$"),
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
KIND["cet1_requirement"] = "pct"
CORE = ("cet1_capital", "rwa", "cet1_ratio", "leverage_ratio")
# metrics that go to the facts table (the rest are kept in the document record only)
PUBLISH = ("cet1_capital", "tier1_capital", "total_capital", "rwa", "cet1_ratio", "tier1_ratio",
           "total_capital_ratio", "overall_capital_requirement", "total_srep_requirement", "cet1_requirement",
           "leverage_exposure", "leverage_ratio", "lcr", "nsfr", "tier1_leverage")
# Small subsidiaries of foreign banks hold far more capital than they lend against: Bank of Baroda
# UK at a CET1 ratio of 220% and leverage of 85%, ICBC London at 81% and 47%, are genuine.
# A total SREP requirement is at least the 8% Pillar 1 minimum, and an overall capital requirement
# at least that plus the 2.5% conservation buffer; a lower figure is a CET1-basis one.
BOUNDS = {"cet1_ratio": (3, 300), "tier1_ratio": (3, 300), "total_capital_ratio": (3, 300),
          "leverage_ratio": (1.5, 95), "lcr": (60, 2500), "nsfr": (60, 1200),
          "overall_capital_requirement": (10.5, 30), "total_srep_requirement": (8, 25),
          "combined_buffer": (0, 15), "cet1_headroom": (0, 300), "cet1_requirement": (7, 25)}
# rows that are not read for their own sake: out of range, the row is left out rather than the
# document sent to review
SOFT = ("overall_capital_requirement", "total_srep_requirement", "combined_buffer", "cet1_headroom",
        "cet1_requirement", "p2r_7a", "p2r_7b")

NUM_RE = re.compile(r"^\(?[-–]?[£$€]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?$|^\(?[-–]?\d+\.\d+\)?%?$|^\(?[-–]?\d{3,}\)?%?$")
DASH_RE = re.compile(r"^(?:[-–—]+%?|n/?a|nm|n\.a\.)$", re.I)
STRONG_RE = re.compile(r"[,.%()]|\d{3}")   # a real cell value, as opposed to a row or page number
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_MONTH_AHEAD = r"(?![ \t./-]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))"
# a footnote mark glued to the year: Lloyds' "31 Mar 20222" and "Q1 20182", Leeds' "Sep-231"
_FOOTNOTE = r"(?:[1-9](?!\d))?"


def _year_group(tag: str) -> str:
    """A four-digit year may sit on the next line; a two-digit year must share the line with its month
    and must not be followed on that line by another month name ("June 31 December")."""
    return (r"(?:[\s./,'-]*(?P<y4" + tag + r">\d{4})" + _FOOTNOTE + r"|[ \t./,'-]*(?P<y2" + tag + r">\d{2}" + _MONTH_AHEAD + r")"
            + _FOOTNOTE + r")\b")


# One scanner with ordered alternatives, so "Mar-26" is read as month-year before "26 Dec" could be read as a day.
DATE_SCAN = re.compile(
    r"\b(?P<d1>\d{1,2})\s?(?:st|nd|rd|th)?[\s./-]?" + MON.replace("(", "(?P<m1>", 1) + r"\.?" + _year_group("a")
    + r"|\b(?P<d2>\d{1,2})[./](?P<m2>\d{1,2})[./](?P<y2>\d{4}|\d{2})\b"      # 31.12.25 and UBS's 30.6.26
    + r"|\b" + MON.replace("(", "(?P<m4>", 1) + r"\s+(?P<d4>\d{1,2})(?!\d)[,.]?" + _year_group("c")
    + r"|\b" + MON.replace("(", "(?P<m3>", 1) + _year_group("b")
    + r"|\b(?P<qh>[QH])(?P<n>[1-4])\s?[-']?\s?(?P<y4>\d{4}|\d{2})" + _FOOTNOTE + r"\b", re.I)
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
    # "16. 6%": the HKMA disclosure statements set a space after the decimal point in every
    # percentage. Left alone, the number ends at the point and the row's value is read from
    # whatever follows, which for a numbered template is the next row's number.
    text = re.sub(r"(\d)\.\s+(?=\d)", r"\1.", text)
    text = re.sub(r"(\d)\s+%", r"\1%", text)
    return _join_space_thousands(text)


# "2 604": Investec and the continental banks print a space where others print a comma, and the
# tokeniser then reads one amount as two values. Joined only on a page that uses no commas as
# thousands separators and does so more than once, so a stray "Table 1 234" elsewhere is left
# alone. Three whole-number ratios side by side ("150 160 155") would be joined too; the
# validator then rejects the impossible figure and the document goes to the queue.
SPACE_THOUSANDS = re.compile(r"(?<![\d.,])(\d{1,3})((?: \d{3})+)(?![\d,])")
COMMA_THOUSANDS = re.compile(r"\d,\d{3}")


def _join_space_thousands(text: str) -> str:
    if COMMA_THOUSANDS.search(text) or len(SPACE_THOUSANDS.findall(text)) < 2:
        return text
    return SPACE_THOUSANDS.sub(lambda m: m.group(1) + m.group(2).replace(" ", ","), text)


# Rows printed beside a base row on a different basis. The template asks for the base row, so
# these are never read: "fully loaded" next to the transitional figure, "pre-floor" next to the
# floored one (the Hong Kong and Basel 3.1 layouts), the pre-IFRS 9 comparatives.
VARIANT_RE = re.compile(r"fully[- ]loaded|fully[- ]phased|ecl accounting model|pre[- ]ifrs ?9|"
                        r"pre[- ]?floor|floor[- ]adjusted|excluding (?:the )?(?:ifrs ?9|ecl)|"
                        # "Total capital as if IFRS 9 transitional arrangements had not been applied"
                        r"\bas if\b|(?:had|have) not been applied|without (?:the )?(?:application of )?(?:the )?"
                        r"(?:ifrs ?9 |ecl )?transitional|no transitional", re.I)


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


def bare_year_columns(header: str, year_end: str = "12-31") -> list[date]:
    """Period ends for column headers that name a year and nothing else.

    Only a run of two or more consecutive years counts, each on its own short line: a lone number
    in a header is as likely to be a row count or a page number, and a table's own figures must
    never be mistaken for its column dates.
    """
    years = []
    for line in header.splitlines():
        t = line.strip().rstrip(".")
        if not re.fullmatch(r"(?:19|20)\d\d", t):
            continue
        y = int(t)
        if 2005 <= y <= date.today().year + 1 and (not years or y != years[-1]):
            years.append(y)
    if len(years) < 2:
        return []
    step = years[1] - years[0]
    if step not in (-1, 1) or any(b - a != step for a, b in zip(years, years[1:])):
        return []            # not a run of consecutive years, so not a column header
    ye_m, ye_d = (int(x) for x in year_end.split("-"))
    return [_month_end(y, ye_m) if ye_d >= 28 else date(y, ye_m, ye_d) for y in years]



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
        if re.fullmatch(r"(?:20\d{2}[1-9]?[\s,]*)+", t) or (pending and re.fullmatch(r"(?:\d{2}[\s,]*)+", t)):
            # "20222": the year with a footnote mark glued on, which left the day-month unpaired
            for y in re.findall(r"20\d{2}(?=[1-9]?(?:[\s,]|$))|\d{4}|\d{2}", t):
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


_CODES = r"(?:aed|aud|cad|chf|cny|rmb|eur|gbp|hkd|inr|jpy|kwd|qar|sar|sgd|usd|sek|nok|dkk)"
_UNIT = r"(?:[£$€¥]|\b" + _CODES + r")"
UNIT_PATTERNS = (
    # FAB's "All numbers in AED 000s", "USD'000", "HK$'000", "in thousands of", "(000s)"
    (r"(?:" + _UNIT + r"|\bin)\s?'?\s?000s?\b|(?<![\d,.])'000s?\b|\bthousands?\b|\(000s?\)", 0.001),
    (_UNIT + r"\s?(?:m|mn|mio|millions?)\b|\bmillions?\b|\(m\)|\bmn\b", 1.0),
    (_UNIT + r"\s?(?:bn|billions?)\b|\bbillions?\b", 1000.0))


def detect_units(text: str, anchor: int | None = None) -> tuple[str, float]:
    """(currency, scale to millions). The unit statement nearest the table wins: RBC's "(Millions of
    Canadian dollars)" header must not lose to "RWA increased by $29 billion" in the commentary, nor a
    £m column head to "£1.2bn" in the prose above it. anchor is where the table starts (row 1); a
    statement on a short line (a column head) beats one inside a sentence, and one above the anchor
    beats one below it."""
    low = text.lower()
    if anchor is None:
        anchor = 0            # no table found: the earliest statement wins
    hits = []
    for pat, sc in UNIT_PATTERNS:
        for m in re.finditer(pat, low):
            ls, le = low.rfind("\n", 0, m.start()) + 1, low.find("\n", m.end())
            line = low[ls:le if le >= 0 else len(low)].strip()
            prose = len(line) > 60
            below = m.start() > anchor
            hits.append((prose, below, abs(m.start() - anchor), sc))
    scale = min(hits)[3] if hits else 1.0
    ccy = ""
    for sym, code in CURRENCY:
        if sym.lower() in low[:anchor + 4000]:
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
            # row 13 is the exposure excluding central bank claims, so the ratio stands in only on that basis
            same_basis = not re.search(r"including claims on central banks", labels[alt], re.I)
            if "14" not in values and same_basis:
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
        pat = r"total.*risk\s?-?\s?w ?eighted|risk\s?-?\s?w ?eighted (?:exposure amount|assets)|\brweas?\b|\brwas?\b"
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
        # the EU template's 14a-14c are the leverage requirements ("Total SREP leverage ratio
        # requirements"), and the UK's 14c and 14d averages: none of them is the period-end ratio
        if metric == "leverage_ratio" and re.search(r"requirement|srep|additional own funds|of which|buffer|average|mean", low):
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
        # a line that starts in lower case continues a wrapped label: SC's row 12 "CET1 available after
        # meeting the / total SREP own funds / requirements" is not the total SREP row
        if re.match(r"[a-z]", line):
            i += 1
            continue
        # allow a wrapped label: try the line alone, then joined with the next non-value line
        cands = [line]
        if i + 1 < n and not _is_value_line(lines[i + 1]):
            nxt = _norm_text(lines[i + 1]).strip()
            if VARIANT_RE.search(nxt) and re.match(r"[a-z(]", nxt):
                i += 1
                continue         # "Total capital" / "as if IFRS 9 ... not been applied": the variant row
            cands.append(line + " " + nxt)
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
CONTENTS_LINE = re.compile(r"^\s*\S.*?[a-z)]\s+\.{0,}\s*\d{1,3}\s*$", re.I)
BARE_PAGE_NO = re.compile(r"^\s*\d{1,3}\s*$")
VALUE_TOKEN = re.compile(r"\d[\d,]*\.\d|\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*%")


def looks_like_contents(text: str) -> bool:
    """A contents page lists "KM1 Key metrics ... 12", so it carries the template's wording and
    scores like it, but the number beside each entry is a page number. Read as a table it fills
    the capital rows with them. It is told apart by shape rather than by the word "Contents",
    which appears in the running header of every page in some reports: a listing is many entries
    numbered with a small integer and almost no figures, whether the number sits at the end of the
    entry's line or on a line of its own. A real table always carries plenty of figures."""
    lines = [l for l in text.splitlines() if l.strip()]
    listed = sum(1 for l in lines if CONTENTS_LINE.match(l) or BARE_PAGE_NO.match(l))
    figures = len(VALUE_TOKEN.findall(text))
    return listed >= 5 and figures < 10



def extract(pdf_path: str, hint_date: date | None = None, max_pages: int = 250, currency_hint: str = "",
            year_end: str = "12-31", page_hint: int | None = None, published: date | None = None) -> Result:
    """published: the PDF's own creation stamp, which no period it reports can postdate."""
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
        if looks_like_contents(t):
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
    # Standard Chartered sets "31.03.2" over "3": the year's last digit falls to the next line
    cells = re.sub(r"\b(\d{1,2}\.\d{1,2}\.\d)[ \t]*\n?[ \t]*(\d)\b", r"\1\2", cells)
    res.period_dates = parse_dates(cells, year_end=year_end)
    joined, unresolved = join_split_headers(cells, year_end)
    if len(joined) > len(res.period_dates):
        res.period_dates = joined            # day-month lines and year lines printed as two blocks
    if not res.period_dates:
        standalone = [l.strip() for l in lines if len(l.strip()) <= 20 and parse_dates(l, year_end=year_end)]
        res.period_dates = parse_dates("\n".join(standalone), year_end=year_end)
    if not res.period_dates:
        # columns headed by a bare year, as an annual-only filer sets them: "2025  2024". Read
        # against the year end rather than falling through to a date in the narrative, which for
        # Handelsbanken is the board meeting that approved the dividend, three months later.
        res.period_dates = bare_year_columns(header, year_end)
        if res.period_dates:
            res.checks.append(("info", "columns headed by year alone, dated to the financial year end"))
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
    k1 = next((k for k in range(len(lines)) if (_row_start(lines, k) or ("",))[0] == "1"), None)
    if k1 is None:
        k1 = next((k for k, l in enumerate(lines) if re.search(r"common equity tier|cet ?1", l, re.I)), None)
    anchor = None
    if k1 is not None:
        pos, seen = 0, -1
        for raw_line in text.splitlines(True):
            if raw_line.strip():
                seen += 1
                if seen == k1:
                    anchor = pos
                    break
            pos += len(raw_line)
    res.currency, res.scale = detect_units(text, anchor)
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
    cet1_requirement(res, picked, labels)

    # reference date
    split_header = any("split month and year" in m for _, m in res.checks)
    if res.period_dates and not (split_header and hint_date):
        header_ref = res.period_dates[0] if descending else res.period_dates[-1]
        res.reference_date = choose_reference(header_ref, hint_date, published, res.checks)
        if res.reference_date != header_ref:
            res.history = {}        # the header misdated its first column, so its other columns are no better
    elif split_header and hint_date:
        res.reference_date = hint_date
    elif hint_date:
        res.reference_date = hint_date
        res.checks.append(("warn", "no period date found in the template header; using the expected date"))
    else:
        res.checks.append(("error", "no reference date"))
    if res.reference_date:
        res.reference_date = snap_to_period_end(res.reference_date, year_end, res.checks)
        if published and res.reference_date > published and not (hint_date and hint_date > published):
            res.checks.append(("error", f"reference date {res.reference_date} is after the document was produced ({published})"))

    validate(res)
    return res


def _p2r_cet1(vals: dict, labels: dict) -> float | None:
    """The CET1 part of Pillar 2A: the UK template's 7a ("Additional CET1 SREP requirements"), the EU
    template's 7b ("of which: to be made up of CET1 capital"). Printed as a share of 7a rather than in
    points, or larger than 7a, it is not the figure."""
    for row, metric in (("7a", "p2r_7a"), ("7b", "p2r_7b")):
        if metric in vals and re.search(r"\bcet ?1\b|common equity", labels.get(row, ""), re.I):
            p = vals[metric]
            if not 0 <= p <= 6 or (row == "7b" and "p2r_7a" in vals and p > vals["p2r_7a"] + 0.01):
                return None
            return p
    return None


def cet1_requirement(res: Result, picked: list, labels: dict) -> None:
    """The bank's own CET1 requirement: the 4.5% Pillar 1 minimum, the CET1 part of Pillar 2A and the
    combined buffer, when the template gives both rows for the same columns."""
    toks = {m: t for m, t, _ in picked}
    p2r_metric = next((m for row, m in (("7a", "p2r_7a"), ("7b", "p2r_7b"))
                       if m in toks and re.search(r"\bcet ?1\b|common equity", labels.get(row, ""), re.I)), None)
    if not p2r_metric or "combined_buffer" not in toks or len(toks[p2r_metric]) != len(toks["combined_buffer"]):
        return
    p = _p2r_cet1(res.values, labels)
    lo, hi = BOUNDS["cet1_requirement"]
    if p is not None and "combined_buffer" in res.values:
        res.values["cet1_requirement"] = round(4.5 + p + res.values["combined_buffer"], 2)
        res.derived.add("cet1_requirement")      # validate() leaves it out if it falls outside its range
    for vals in res.history.values():
        p = _p2r_cet1(vals, labels)
        if p is not None and "combined_buffer" in vals and lo <= 4.5 + p + vals["combined_buffer"] <= hi:
            vals["cet1_requirement"] = round(4.5 + p + vals["combined_buffer"], 2)


def choose_reference(header_ref: date, hint: date | None, published: date | None, checks: list) -> date:
    """The template header's date, unless the file name says otherwise and the document's own creation
    stamp sides with the file name. A KM1 header misread by a column (a footnote glued to the year, a
    day-month block paired with the wrong year) is the usual cause: NatWest's Q1 2026 dated 30 June
    2026, weeks after it was published, and Lloyds' Q1 reports dated to the year end before. The latest
    of the two dates that the document could have reported wins. With no stamp the header is kept,
    unless it is half a year or more after the period the file name gives: Standard Chartered's Q1
    2018 report cannot hold figures for December 2019, while a file name that names only a year, and
    so defaults to the year end, is often later than the period inside."""
    if not hint or abs((header_ref - hint).days) <= 45:
        return header_ref
    # a stamp three years after the file name's period is a re-saved file or a stray name (Mizuho's
    # "1q01"), and settles nothing
    if published and hint <= published and (published - hint).days <= 3 * 366:
        if header_ref > published or hint > header_ref:
            checks.append(("warn", f"header date {header_ref} disagrees with expected {hint}; "
                                   f"the document was produced {published}, so the expected date is used"))
            return hint
    elif not published and (header_ref - hint).days > 183:
        checks.append(("warn", f"header date {header_ref} is long after the period the file name gives ({hint}); "
                               "the expected date is used"))
        return hint
    checks.append(("warn", f"header date {header_ref} disagrees with expected {hint}"))
    return header_ref


def snap_to_period_end(d: date, year_end: str, checks: list) -> date:
    """A period ends on a month end, or on the year end's own day (Nationwide's 4 April). "3 Dec" read
    for "31 Dec", or a 30 December stamp, would otherwise make a second point beside the right one.
    A day mid-month is not a slip of that kind (a board date read as the period) and is left alone."""
    ye_m, ye_d = (int(x) for x in year_end.split("-"))
    end = _month_end(d.year, d.month)
    if d == end or (ye_d < 28 and d.day == ye_d) or 5 < d.day < 26:
        return d
    checks.append(("info", f"reference date {d} moved to the period end {end}"))
    return end


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
        # the same ranges as the current column: an LCR above 1000 is real for Close Brothers and Vanquis
        if any(not (BOUNDS[m][0] <= vals[m] <= BOUNDS[m][1]) for m in
               ("cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "lcr", "nsfr") if m in vals):
            continue
        for m in SOFT:
            if m in vals and m in BOUNDS and not (BOUNDS[m][0] <= vals[m] <= BOUNDS[m][1]):
                vals.pop(m)
        if {"overall_capital_requirement", "total_srep_requirement", "combined_buffer"} <= set(vals):
            if vals["overall_capital_requirement"] < vals["total_srep_requirement"] + vals["combined_buffer"] - 0.3:
                vals.pop("overall_capital_requirement")
        keep[d] = vals
    return keep


AMOUNTS = tuple(m for m, k in KIND.items() if k == "amount")
# Rough US dollars per unit, for a size test only: no bank holds more than about $4tn of RWA or
# $500bn of CET1, so a figure many times that is a table in thousands read as millions.
USD_PER = {"USD": 1, "GBP": 1.3, "EUR": 1.1, "CHF": 1.1, "JPY": 0.007, "HKD": 0.13, "CNY": 0.14, "AED": 0.27,
           "QAR": 0.27, "SAR": 0.27, "KWD": 3.3, "CAD": 0.73, "AUD": 0.65, "SGD": 0.75, "INR": 0.012,
           "SEK": 0.095, "NOK": 0.095, "DKK": 0.15}
SIZE_CEILING_USD_M = {"rwa": 8e6, "leverage_exposure": 15e6, "cet1_capital": 1e6, "tier1_capital": 1.2e6, "total_capital": 1.5e6}


def rescale(res: Result, factor: float, why: str) -> None:
    """Multiply every amount, current and prior columns, by factor (a units slip the ratios cannot show)."""
    for m in AMOUNTS:
        if m in res.values:
            res.values[m] = res.values[m] * factor
    for vals in res.history.values():
        for m in AMOUNTS:
            if m in vals:
                vals[m] = vals[m] * factor
    res.scale *= factor
    res.checks.append(("warn", why))


def check_size(res: Result) -> None:
    """Capital, RWA and exposure in thousands read as millions agree with their own ratios, so only
    their size gives them away."""
    usd = USD_PER.get(res.currency)
    if not usd:
        return
    over = [m for m, cap in SIZE_CEILING_USD_M.items() if m in res.values and res.values[m] * usd > cap]
    if over:
        rescale(res, 0.001, f"amounts far beyond any bank's size ({', '.join(over)}); read as thousands")


def validate(res: Result) -> None:
    v = res.values
    check_size(res)
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
            if m in SOFT:
                # a requirement row on another basis (Santander's 7d is Pillar 2A alone) says nothing
                # about the rest of the table, so the document keeps its standing
                res.checks.append(("info", f"{m} {v.pop(m):g} outside {lo}..{hi}, not loaded"))
            else:
                res.checks.append(("error", f"{m} {v[m]:g} outside {lo}..{hi}"))
    # an overall capital requirement below the total SREP requirement plus the combined buffer is
    # not on a total-capital basis: Standard Chartered printed its CET1 one (10.38%) in row 11a
    if "overall_capital_requirement" in v and "total_srep_requirement" in v and "combined_buffer" in v:
        floor = v["total_srep_requirement"] + v["combined_buffer"]
        if v["overall_capital_requirement"] < floor - 0.3:
            res.checks.append(("info", f"overall_capital_requirement {v.pop('overall_capital_requirement'):g} below "
                                       f"the total SREP requirement plus buffers ({floor:.2f}), not loaded"))

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
    # Tier 1 and total capital against their own ratios: a row read from the wrong line (OCR loses a
    # row's figures and the next row's take their place) fails here, and is left out
    for cap, ratio in (("tier1_capital", "tier1_ratio"), ("total_capital", "total_capital_ratio")):
        if cap in v and ratio in v and ratio not in res.derived and v.get("rwa"):
            implied = v[cap] / v["rwa"] * 100
            if abs(implied - v[ratio]) > 0.35 and abs(implied - v[ratio]) > 0.03 * v[ratio]:
                res.checks.append(("warn", f"{ratio} {v[ratio]:.2f} vs implied {implied:.2f} from capital/RWA, not loaded"))
                v.pop(cap), v.pop(ratio)
    if "tier1_capital" in v and "leverage_exposure" in v and "leverage_ratio" in v and v["leverage_exposure"]:
        implied = v["tier1_capital"] / v["leverage_exposure"] * 100
        if v["leverage_ratio"] and 800 < implied / v["leverage_ratio"] < 1250:
            v["leverage_exposure"] *= 1000
            implied /= 1000
            res.checks.append(("warn", "leverage_exposure was in billions; scaled to millions"))
        if abs(implied - v["leverage_ratio"]) > 0.6:
            # the ratio and the exposure are not on one basis, or not from one column (Metro's annual
            # KM1 gave its half-year leverage rows): neither can be trusted, so neither is loaded
            res.checks.append(("warn", f"leverage_ratio {v['leverage_ratio']:.2f} vs implied {implied:.2f}, "
                                       "so the leverage rows are not loaded"))
            v.pop("leverage_ratio"), v.pop("leverage_exposure")
    # The LCR row is the average of twelve month-end ratios and HQLA and outflows are averages of
    # their own, so the two legitimately differ by a fifth or more for a volatile buffer (Goldman
    # Sachs by 20%, Vanquis by 31%); a larger gap is a different column or a different table.
    if "hqla" in v and "net_cash_outflows" in v and "lcr" in v and v["net_cash_outflows"]:
        implied = v["hqla"] / v["net_cash_outflows"] * 100
        if abs(implied - v["lcr"]) > max(5, 0.4 * v["lcr"]):
            res.checks.append(("warn", f"lcr {v['lcr']:.1f} vs implied {implied:.1f}, so the liquidity rows are not loaded"))
            for m in ("lcr", "hqla", "net_cash_outflows"):
                v.pop(m)
        elif abs(implied - v["lcr"]) > 5:
            res.checks.append(("warn", f"lcr {v['lcr']:.1f} vs implied {implied:.1f}"))
    if "available_stable_funding" in v and "required_stable_funding" in v and "nsfr" in v and v["required_stable_funding"]:
        implied = v["available_stable_funding"] / v["required_stable_funding"] * 100
        if abs(implied - v["nsfr"]) > max(3, 0.15 * v["nsfr"]):
            res.checks.append(("warn", f"nsfr {v['nsfr']:.1f} vs implied {implied:.1f}, so the funding rows are not loaded"))
            for m in ("nsfr", "available_stable_funding", "required_stable_funding"):
                v.pop(m)
        elif abs(implied - v["nsfr"]) > 3:
            res.checks.append(("warn", f"nsfr {v['nsfr']:.1f} vs implied {implied:.1f}"))
    if "cet1_ratio" in v and "tier1_ratio" in v and v["tier1_ratio"] < v["cet1_ratio"] - 0.05:
        res.checks.append(("error", "tier1_ratio below cet1_ratio"))
    if "tier1_ratio" in v and "total_capital_ratio" in v and v["total_capital_ratio"] < v["tier1_ratio"] - 0.05:
        res.checks.append(("error", "total_capital_ratio below tier1_ratio"))
    if "cet1_capital" in v and "tier1_capital" in v and v["tier1_capital"] < v["cet1_capital"] - 0.5:
        res.checks.append(("error", "tier1_capital below cet1_capital"))
    if not res.currency:
        res.checks.append(("warn", "currency not detected"))
