"""US disclosures: Pillar 3 capital tables and the public LCR / NSFR documents. Rules only.

US holding companies do not use the KM1 template. Their Pillar 3 report carries a
capital-ratio table with Standardized and Advanced columns, states the supplementary
leverage ratio (SLR) and Tier 1 leverage ratio in prose, and publishes the LCR in a
separate quarterly document ("Table 1: Liquidity Coverage Ratio ... LCR 119%"). This
module reads both.

Every ratio and amount from one report comes from one approach column, the Standardized
one wherever the column headings say which it is: the requirement a US bank is held to
(data/reference/us-capital-requirements.json) is set on the Standardized approach, and the
lower ratio is not always the binding one (Citi's Advanced CET1 is lower, but further above
its own, smaller, requirement). Without headings the column of the lower CET1 ratio is read.

    from bankcredit.extract import us
    res = us.extract_capital("wfc-pillar-3.pdf")   -> km1.Result with cet1_ratio, tier1_ratio,
                                                      total_capital_ratio, leverage_ratio (SLR),
                                                      tier1_leverage, rwa, cet1_capital where found
    res = us.extract_lcr("wfc-lcr.pdf")            -> lcr, hqla, net_cash_outflows
"""
from __future__ import annotations

import re
from datetime import date

import fitz

from .km1 import page_texts, Result, _norm_text, parse_dates, _tokens, _is_num_tok, _num

PCT = r"(\d{1,2}\.\d{1,2})\s?%?"
RATIO_ROWS = [
    ("cet1_ratio", r"(?:common equity tier 1|cet1) (?:capital )?ratio"),
    ("tier1_ratio", r"(?<!common equity )(?<!cet1 )tier 1 (?:capital )?ratio"),
    ("total_capital_ratio", r"total (?:risk[- ]based )?capital ratio"),
]


def _actual(vals: list[float], required_mode: bool) -> list[float]:
    """Tables that list required ratios beside actual ones (Citi) carry the actual figures in the
    second half of the row; otherwise the columns are approaches (Wells)."""
    return vals[len(vals) // 2:] if required_mode and len(vals) >= 2 else vals


def _pick(vals: list[float], required_mode: bool, single: bool = False, col: int | None = None) -> float | None:
    """The value in approach column col of a row; the lower of the two when col is not known."""
    if not vals:
        return None
    vals = _actual(vals, required_mode)
    if single:
        return vals[-1] if required_mode else vals[0]
    pair = vals[:2]
    return pair[col] if col is not None and col < len(pair) else min(pair)


def _lower_col(vals: list[float], required_mode: bool) -> int | None:
    pair = _actual(vals, required_mode)[:2]
    return pair.index(min(pair)) if len(pair) == 2 else None


def _std_col(lines, i, back: int = 40) -> int | None:
    """Which of row i's two approach columns is the Standardized one, from the column headings above it
    on the same page (Wells and Citi head Advanced then Standardized, Bank of America the reverse).
    None when the headings do not name both approaches."""
    seen = []
    for j in range(i - 1, max(-1, i - back), -1):
        if lines[j][0] != lines[i][0]:
            break
        s = lines[j][1].strip()
        if len(s) > 40 or re.search(r"\d+\.\d", s):     # prose, or a row of figures: not a heading
            continue
        m = re.search(r"\b(standardi[sz]ed|advanced)\b", s, re.I)
        if m:
            seen.append(m.group(1)[0].lower())
            if len(seen) == 2:
                break
    if len(seen) == 2 and seen[0] != seen[1]:
        return 1 if seen[0] == "s" else 0          # the nearest heading is the right-hand column
    return None


def _period_cols(lines, i, back: int = 25) -> bool:
    """True when the columns above row i are periods, not approaches: Goldman's Table 2 heads
    'June 2026 | December 2025', so its second column is last quarter, never a required ratio."""
    years = set()
    for j in range(i - 1, max(-1, i - back), -1):
        if lines[j][0] != lines[i][0]:
            break
        m = re.fullmatch(r"(?:[a-z]+\s+)?(?:\d{1,2},?\s+)?(20\d{2})", lines[j][1].strip().lower())
        if m:
            years.add(m.group(1))
    return len(years) >= 2


def _advanced_only(lines, i, back: int = 30) -> bool:
    """True when the text above a single-column ratio row says the table is on the Advanced approach
    (JPMorgan's 'present the Advanced risk-based ... capital metrics', Goldman's Table 2)."""
    above = " ".join(l for p, l in lines[max(0, i - back):i] if p == lines[i][0])
    return bool(re.search(r"\badvanced\b", above, re.I)) and not re.search(r"standardi[sz]ed", above, re.I)


STD_PROSE = re.compile(r"standardi[sz]ed\s+(?:capital\s+)?ratios\s+were\s+" + PCT + r"\s+for\s+cet1\s+capital,?\s+"
                       + PCT + r"\s+for\s+tier\s+1\s+capital,?\s+and\s+" + PCT + r"\s+for\s+total\s+capital", re.I)
AMOUNT_ROWS = [
    ("cet1_capital", r"^(?:common equity tier 1|cet1) capital$"),
    ("tier1_capital", r"^tier 1 capital$"),
    ("rwa", r"^(?:total )?risk[- ]weighted assets$"),
]


def _lines(texts, pages):
    out = []
    for p in pages:
        if p < len(texts):
            out += [(p, l.strip()) for l in _norm_text(texts[p]).splitlines() if l.strip()]
    return out


def _period(texts, max_pages=4) -> date | None:
    text = "\n".join(_norm_text(t) for t in texts[:max_pages])
    m = re.search(r"(?:as of|as at|quarter ended|period ended|at)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})", text, re.I)
    if m:
        d = parse_dates(m.group(1), explicit_only=True)
        if d:
            return d[0]
    ds = [d for d in parse_dates(text, explicit_only=True) if d <= date.today() and d.day >= 28]
    return max(ds) if ds else None


REQ_HEADING = re.compile(r"minimum|requirement|buffer|well[- ]capitalized", re.I)


def _under_requirement_heading(lines, i, back: int = 14) -> bool:
    """True when the nearest heading above line i says the block lists minimums or requirements
    rather than actual ratios (Goldman's Table 1: minimum, total requirement, then the actual block)."""
    for j in range(i - 1, max(-1, i - back), -1):
        l = lines[j][1].strip()
        if not l or lines[j][0] != lines[i][0]:
            continue
        if not re.search(r"\d+\.\d|\d\s?%", l) and len(l) < 90:   # a heading: short, no ratio figures (a date is fine)
            return bool(REQ_HEADING.search(l)) and not re.search(r"actual|ratios? as of|reported", l, re.I)
    return False


def _nums_after(lines, i, limit=6, decimals=False) -> list[float]:
    """Numeric tokens on the label line after the label, then on following value-only lines.
    decimals=True keeps only tokens with a decimal point (percentages), which drops footnote marks."""
    def ok(t):
        t = t.rstrip("*").rstrip("%")
        return _is_num_tok(t) and re.search(r"\d", t) and (not decimals or "." in t)
    vals = []
    for t in _tokens(lines[i][1]):
        if ok(t):
            v = _num(t.rstrip("*"))
            if v is not None:
                vals.append(v)
    j = i + 1
    while j < len(lines) and len(vals) < limit:
        toks = [t for t in _tokens(lines[j][1]) if t not in ("*", "$", "%")]
        if not toks and lines[j][1].strip() == "$":
            j += 1; continue                  # Citi sets the currency sign on a line of its own
        if toks and all(_is_num_tok(t.rstrip("*").rstrip("%")) or re.fullmatch(r"\d", t) for t in toks):
            vals += [v for v in (_num(t.rstrip("*")) for t in toks if ok(t)) if v is not None]
            j += 1
        else:
            break
    return vals


BLOCK_LABELS = [
    ("cet1_ratio", r"^common equity tier 1(?: capital)?(?: ratio)?"),
    ("tier1_ratio", r"^tier 1 capital(?: ratio)?$|^tier 1(?: ratio)?$"),
    ("total_capital_ratio", r"^total capital(?: ratio)?"),
    ("tier1_leverage", r"^tier 1 leverage"),
    ("leverage_ratio", r"^supplementary leverage"),
]
SINGLE = {"leverage_ratio"}       # shown once, not per approach


def _capital_block(lines) -> tuple[dict, int | None]:
    """Parse a 'Capital Ratios' block: labels with values on following lines (row-major, Northern Trust)
    or all labels then all values by column (column-major, Bank of America). Binding ratio = lowest column."""
    for start, (p, l) in enumerate(lines):
        if not re.fullmatch(r"capital ratios?", l.lower().strip(": ")):
            continue
        items = []
        for _, t in lines[start + 1:start + 30]:
            low = re.sub(r"\s*\([a-z0-9]\)$", "", t.lower().strip())
            lab = next((m for m, pat in BLOCK_LABELS if re.search(pat, low)), None)
            if lab:
                items.append(("label", lab)); continue
            toks = [x for x in _tokens(t) if x not in ("%", "$")]
            if toks and all(_is_num_tok(x.rstrip("%")) or x.upper() in ("N/A", "NA", "-") for x in toks):
                for x in toks:
                    items.append(("num", _num(x) if x.upper() not in ("N/A", "NA", "-") else None))
                continue
            break
        labels = [v for k, v in items if k == "label"]
        if len(labels) < 3:
            continue
        vals: dict[str, list] = {lab: [] for lab in labels}
        first_num = next((i for i, (k, _) in enumerate(items) if k == "num"), None)
        last_label = max(i for i, (k, _) in enumerate(items) if k == "label")
        if first_num is not None and first_num > last_label:
            nums = [v for k, v in items if k == "num"]                      # column-major
            multi = [lab for lab in labels if lab not in SINGLE]
            single = [lab for lab in labels if lab in SINGLE]
            n = len(multi)
            cols = []
            while len(nums) >= n and len(cols) < 2:
                cols.append(nums[:n]); nums = nums[n:]
            for lab in multi:
                vals[lab] = [c[multi.index(lab)] for c in cols]
            if single and nums:
                vals[single[0]] = [nums[-1]]
        else:
            cur = None
            for k, v in items:
                if k == "label":
                    cur = v
                elif cur:
                    vals[cur].append(v)
        # one approach column for every ratio: Standardized by the headings, else the lower CET1
        col = _std_col(lines, start)
        cet = vals.get("cet1_ratio", [])[:2]
        if col is None and len(cet) == 2 and None not in cet:
            col = cet.index(min(cet))
        out = {}
        for lab, vs in vals.items():
            ok = [v for v in vs if v is not None and 2 < v < 60]
            if not ok:
                continue
            if lab in ("tier1_leverage", "leverage_ratio"):
                out[lab] = ok[0]
                continue
            v = vs[col] if col is not None and col < len(vs) else None
            out[lab] = v if v is not None and 2 < v < 60 else min(ok[:2])
        if "cet1_ratio" in out:
            return out, p + 1
    return {}, None


MATRIX_COLS = {"rwa": "rwa", "cet1": "cet1_ratio", "tier 1": "tier1_ratio", "total capital": "total_capital_ratio"}


def _entity_matrix(lines) -> tuple[dict, int | None]:
    """BNY's 'Basel III RWA and risk-based capital ratios' table: a row per legal entity, the columns
    RWA, CET1, Tier 1 and Total Capital each split SA | AA. The first row after 'BHC:' is the group's."""
    for i, (p, l) in enumerate(lines):
        if not re.search(r"rwa and risk-based capital ratios", l, re.I):
            continue
        cols, tags, j = [], [], i + 1
        while j < min(len(lines), i + 40):
            s = lines[j][1].strip().lower()
            if s in MATRIX_COLS:
                cols.append(MATRIX_COLS[s])
            elif s in ("sa", "aa"):
                tags.append(s)
            elif s.startswith("bhc"):
                break
            j += 1
        if len(cols) < 2 or len(tags) != 2 * len(cols):
            continue
        j += 1
        if j < len(lines) and not re.search(r"\d", lines[j][1]):
            j += 1                                     # the holding company's name
        nums: list[float] = []
        while j < len(lines) and len(nums) < len(tags) and not re.search(r"[a-z]", lines[j][1], re.I):
            nums += [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", lines[j][1])]
            j += 1
        if len(nums) != len(tags):
            continue
        out = {}
        for k, metric in enumerate(cols):
            v = nums[2 * k + tags[2 * k:2 * k + 2].index("sa")]
            if (metric == "rwa" and v > 1000) or (metric != "rwa" and 2 < v < 60):
                out[metric] = v
        if "cet1_ratio" in out:
            return out, p + 1
    return {}, None


def extract_capital(pdf_path: str, hint_date: date | None = None) -> Result:
    res = Result()
    doc = fitz.open(pdf_path)
    res.currency, res.template = "USD", "US Pillar 3"
    texts, ocr = page_texts(doc, 20)
    if ocr:
        res.checks.append(("warn", "text recovered by OCR from an image-only document"))
    pages = list(range(len(texts)))
    lines = _lines(texts, pages)
    text = "\n".join(l for _, l in lines)
    # Goldman's tables are on the Advanced approach; the binding Standardized ratios are stated in prose
    m = STD_PROSE.search(text)
    std_prose = bool(m)
    if m:
        res.values.update(cet1_ratio=float(m.group(1)), tier1_ratio=float(m.group(2)), total_capital_ratio=float(m.group(3)))
        res.checks.append(("info", "Standardized ratios from the report's own statement; its tables are Advanced"))
    block, page = _entity_matrix(lines)
    if not block:
        block, page = _capital_block(lines)
    for k, v in block.items():
        res.values.setdefault(k, v)
    res.page = page
    required_pages = {p for p, l in lines if re.search(r"\brequired\b", l, re.I)}
    col = None          # the approach column the CET1 row was read from; every other row follows it
    for metric, pat in RATIO_ROWS:
        if metric in res.values:
            continue
        for i, (p, l) in enumerate(lines):
            low = l.lower()
            if re.search(pat, low) and not re.search(r"minimum|requirement|well[- ]capitalized|buffer|excess", low):
                if _under_requirement_heading(lines, i):
                    continue
                vals = [v for v in _nums_after(lines, i, decimals=True) if 3 < v < 60]
                if not vals:
                    continue
                req = p in required_pages and not _period_cols(lines, i)
                if metric == "cet1_ratio":
                    col = _std_col(lines, i)
                    if col is None:
                        col = _lower_col(vals, req)
                        if col is None and _advanced_only(lines, i):
                            res.checks.append(("warn", "ratios are on the Advanced approach only; the binding Standardized ones are not in this table"))
                v = _pick(vals, req, col=col)
                if v is not None:
                    res.values[metric] = v
                    res.page = res.page or p + 1
                    break
    if "leverage_ratio" not in res.values:
        for m in re.finditer(r"(?:SLR|supplementary leverage ratio)[^.]{0,120}?(?:were|was|of)\s+" + PCT + r"(?:\s+and\s+" + PCT + r")?", text, re.I):
            if re.search(r"minimum|requirement|at least|buffer", m.group(0), re.I):
                continue                      # a requirement, not the ratio
            res.values["leverage_ratio"] = float(m.group(1))
            if m.group(2) and "tier 1 leverage" in m.group(0).lower():
                res.values["tier1_leverage"] = float(m.group(2))
            break
    if "leverage_ratio" not in res.values:
        for i, (p, l) in enumerate(lines):
            if re.search(r"^supplementary leverage ratio", l.lower()) and not _under_requirement_heading(lines, i):
                vals = [v for v in _nums_after(lines, i, decimals=True) if 2 < v < 30]
                v = _pick(vals, p in required_pages and not _period_cols(lines, i), single=True)
                if v is not None:
                    res.values["leverage_ratio"] = v; break
    if "tier1_leverage" not in res.values:
        for i, (p, l) in enumerate(lines):
            if re.search(r"^(?:tier 1 )?leverage ratio(?:\(\d\))?$", l.lower().strip()) and not _under_requirement_heading(lines, i):
                vals = [v for v in _nums_after(lines, i, decimals=True) if 2 < v < 30]
                v = _pick(vals, p in required_pages and not _period_cols(lines, i), single=True)
                if v is not None:
                    res.values["tier1_leverage"] = v; break
    for metric, pat in AMOUNT_ROWS:
        if metric in res.values or (std_prose and metric == "rwa"):
            continue                          # Goldman's RWAs are its Advanced ones
        found = []
        for i, (p, l) in enumerate(lines):
            if re.search(pat, re.sub(r"\s*\(\d\)$", "", l.lower().rstrip(":").strip())):    # "Risk Weighted Assets(3)"
                vals = [v for v in _nums_after(lines, i) if v > 1000]
                if vals:
                    found.append((i, p, vals))
        # the row on the page the ratios came from, else the first; under approach headings its
        # Standardized figure (Wells, Citi). Two bare columns are as likely this quarter and the last.
        on_page = [f for f in found if res.page and f[1] + 1 == res.page]
        if found:
            i, p, vals = (on_page or found)[0]
            c = _std_col(lines, i) if len(vals) == 2 else None
            res.values[metric] = vals[c] if c is not None else vals[0]
    res.reference_date = _period(texts) or hint_date
    if not res.reference_date:
        res.checks.append(("error", "no reference date"))
    if "cet1_ratio" not in res.values:
        res.checks.append(("error", "no CET1 ratio found"))
    if "leverage_ratio" not in res.values:
        res.checks.append(("warn", "SLR not found"))
    for cap, ratio in (("cet1_capital", "cet1_ratio"), ("tier1_capital", "tier1_ratio")):
        if cap in res.values and "rwa" in res.values and ratio in res.values:
            implied = res.values[cap] / res.values["rwa"] * 100
            if abs(implied - res.values[ratio]) > 0.6:
                res.checks.append(("warn", f"{ratio} {res.values[ratio]:.2f} vs implied {implied:.2f}; capital and RWA may be on different approaches"))
                res.values.pop(cap, None); res.values.pop("rwa", None)
    _grade(res)
    return res


def _grade(res: Result) -> None:
    errors = sum(1 for s, _ in res.checks if s == "error")
    warns = sum(1 for s, _ in res.checks if s == "warn")
    res.fixed_confidence = 0.0 if errors else max(0.5, round(0.92 - 0.08 * warns, 2))


def extract_lcr(pdf_path: str, hint_date: date | None = None) -> Result:
    res = Result()
    doc = fitz.open(pdf_path)
    res.currency, res.template = "USD", "US LCR"
    texts, ocr = page_texts(doc, 12)
    if ocr:
        res.checks.append(("warn", "text recovered by OCR from an image-only document"))
    lines = _lines(texts, range(len(texts)))
    for i, (p, l) in enumerate(lines):
        low = l.lower().rstrip(":")
        if re.fullmatch(r"(?:average )?(?:u\.?s\.? )?(?:lcr|liquidity coverage ratio)(?: \(%\))?\s*\d*", low) or re.match(r"^(?:lcr|liquidity coverage ratio)\s+\d{2,3}\s?%", low):
            vals = [v for v in _nums_after(lines, i) if 50 < v < 1000]
            if vals:
                res.values["lcr"] = vals[0]; res.page = p + 1; break
    if "lcr" not in res.values:
        for m in re.finditer(r"(?:average[^.]{0,40}?\blcr\b|\blcr\b|liquidity coverage ratio)[^.]{0,80}?(?:was|of|is|at|averaged)\s+(?:approximately\s+)?(\d{2,3}(?:\.\d)?)\s?(?:%|percent)", "\n".join(l for _, l in lines), re.I):
            if re.search(r"cap|inflow|minimum|requirement|at least|floor", m.group(0), re.I):
                continue                      # "caps cash inflows at 75%", "minimum LCR of 100%"
            v = float(m.group(1))
            if 90 <= v < 1000:
                res.values["lcr"] = v
                break
    for metric, pat in [("hqla", r"^total (?:eligible )?hqla"), ("net_cash_outflows", r"^(?:total |projected )?(?:total )?net cash outflows?")]:
        for i, (p, l) in enumerate(lines):
            if re.search(pat, l.lower()):
                vals = [v for v in _nums_after(lines, i) if v > 1000]
                if vals:
                    res.values[metric] = vals[0]; break
    res.reference_date = _period(texts) or hint_date
    if "lcr" not in res.values:
        res.checks.append(("error", "no LCR found"))
    if not res.reference_date:
        res.checks.append(("error", "no reference date"))
    if "hqla" in res.values and "net_cash_outflows" in res.values and "lcr" in res.values:
        implied = res.values["hqla"] / res.values["net_cash_outflows"] * 100
        if abs(implied - res.values["lcr"]) > 4:
            res.checks.append(("warn", f"lcr {res.values['lcr']:.0f} vs implied {implied:.0f}"))
    _grade(res)
    return res
