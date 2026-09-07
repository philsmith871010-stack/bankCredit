"""US disclosures: Pillar 3 capital tables and the public LCR / NSFR documents. Rules only.

US holding companies do not use the KM1 template. Their Pillar 3 report carries a
capital-ratio table with Standardized and Advanced columns (the binding ratio is the
lower), states the supplementary leverage ratio (SLR) and Tier 1 leverage ratio in
prose, and publishes the LCR in a separate quarterly document ("Table 1: Liquidity
Coverage Ratio ... LCR 119%"). This module reads both.

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


def _pick(vals: list[float], required_mode: bool, single: bool = False) -> float | None:
    """Binding value from a row. Tables that list required ratios beside actual ones (Citi) carry the
    actual figures in the second half of the row; otherwise the columns are approaches (Wells)."""
    if not vals:
        return None
    if required_mode and len(vals) >= 2:
        actual = vals[len(vals) // 2:]
        return actual[-1] if single else min(actual[:2])
    return vals[0] if single else min(vals[:2])
AMOUNT_ROWS = [
    ("cet1_capital", r"^common equity tier 1 capital$"),
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
        out = {}
        for lab, vs in vals.items():
            vs = [v for v in vs if v is not None and 2 < v < 60]
            if vs:
                out[lab] = min(vs[:2]) if lab not in ("tier1_leverage", "leverage_ratio") else vs[0]
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
    block, page = _capital_block(lines)
    if block:
        res.values.update(block); res.page = page
    required_pages = {p for p, l in lines if re.search(r"\brequired\b", l, re.I)}
    for metric, pat in RATIO_ROWS:
        if metric in res.values:
            continue
        for i, (p, l) in enumerate(lines):
            low = l.lower()
            if re.search(pat, low) and not re.search(r"minimum|requirement|well[- ]capitalized|buffer|excess", low):
                if _under_requirement_heading(lines, i):
                    continue
                vals = [v for v in _nums_after(lines, i, decimals=True) if 3 < v < 60]
                v = _pick(vals, p in required_pages)
                if v is not None:
                    res.values[metric] = v
                    res.page = res.page or p + 1
                    break
    text = "\n".join(l for _, l in lines)
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
            if re.search(r"^supplementary leverage ratio", l.lower()):
                vals = [v for v in _nums_after(lines, i, decimals=True) if 2 < v < 30]
                v = _pick(vals, p in required_pages, single=True)
                if v is not None:
                    res.values["leverage_ratio"] = v; break
    if "tier1_leverage" not in res.values:
        for i, (p, l) in enumerate(lines):
            if re.search(r"^(?:tier 1 )?leverage ratio(?:\(\d\))?$", l.lower().strip()):
                vals = [v for v in _nums_after(lines, i, decimals=True) if 2 < v < 30]
                v = _pick(vals, p in required_pages, single=True)
                if v is not None:
                    res.values["tier1_leverage"] = v; break
    for metric, pat in AMOUNT_ROWS:
        for i, (p, l) in enumerate(lines):
            if re.search(pat, l.lower().rstrip(":")):
                vals = [v for v in _nums_after(lines, i) if v > 1000]
                if vals:
                    res.values[metric] = vals[0]; break
    res.reference_date = _period(texts) or hint_date
    if not res.reference_date:
        res.checks.append(("error", "no reference date"))
    if "cet1_ratio" not in res.values:
        res.checks.append(("error", "no CET1 ratio found"))
    if "leverage_ratio" not in res.values:
        res.checks.append(("warn", "SLR not found"))
    if "cet1_capital" in res.values and "rwa" in res.values and "cet1_ratio" in res.values:
        implied = res.values["cet1_capital"] / res.values["rwa"] * 100
        if abs(implied - res.values["cet1_ratio"]) > 0.6:
            res.checks.append(("warn", f"cet1_ratio {res.values['cet1_ratio']:.2f} vs implied {implied:.2f}; capital and RWA may be on different approaches"))
            res.values.pop("cet1_capital", None); res.values.pop("rwa", None)
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
