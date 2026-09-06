"""Fill blank `lei` cells in data/entities.csv from the GLEIF API.

Idempotent: rows that already have an LEI are never touched, other columns and
row order are preserved, and the CSV is rewritten with the same dialect
(CRLF, minimal quoting). Run from anywhere:

    python research/resolve_leis.py            # resolve + write
    python research/resolve_leis.py --dry-run  # resolve, print table, no write

Matching policy (no guessing):
  * candidates come from GLEIF filtered to the entity's country
    (entity.legalAddress.country), searched by legal name, then fulltext;
  * a candidate "matches" only if its legal name (or, as a fallback, one of
    its registered other names) equals the CSV name after normalisation
    (case, diacritics incl. German ue/oe/ae, punctuation, legal-form suffix
    spelling, leading/trailing "the");
  * among matches we prefer registration ISSUED, entity status ACTIVE,
    category GENERAL; if more than one equally-good match remains the row
    is left blank and reported as ambiguous;
  * SEARCH_ALIASES holds the GLEIF spelling for names the CSV stores
    without diacritics or as a group name. An alias is still subject to the
    same exact-after-normalisation rule against the alias text.
"""
import csv
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "entities.csv"
API = "https://api.gleif.org/api/v1/lei-records"
PAGE_SIZE = 50
SLEEP = 1.1  # GLEIF public API is rate limited to ~60 requests/minute

# id -> alternative search strings / names accepted as the legal name.
# Only for CSV names that are ASCII-folded or are group labels; every alias is
# a real legal name as registered with GLEIF, not a fuzzy hint.
SEARCH_ALIASES = {
    "helaba": ["Landesbank Hessen-Thüringen Girozentrale"],
    "lbbw": ["Landesbank Baden-Württemberg"],
    "rabobank": ["Coöperatieve Rabobank U.A."],
    "credit-agricole": ["Crédit Agricole S.A.", "Crédit Agricole"],
    "societe-generale": ["Société Générale"],
    "credit-mutuel": [
        "Confédération Nationale du Crédit Mutuel",
        "Confédération Nationale Crédit Mutuel",
    ],
    # "Groupe BPCE" is the group brand; the central body / issuer is BPCE (S.A.).
    "bpce": ["BPCE", "BPCE S.A."],
    "op-financial-group": ["OP Osuuskunta"],
    "hsbc-hong-kong": ["The Hongkong and Shanghai Banking Corporation Limited"],
    # GLEIF registers the full statutory name incl. seat.
    "dz-bank": ["DZ BANK AG Deutsche Zentral-Genossenschaftsbank, Frankfurt am Main"],
    "unicredit": ["UniCredit, Società per Azioni"],
    # Trading name vs registered name (same mutual, one GLEIF record each).
    "leek-bs": ["Leek United Building Society"],
    "family-bs": ["National Counties Building Society"],
    # Former names still used in the CSV; the entities were renamed.
    "qib-uk": ["QIB (UK) plc"],
    "icbc-london": ["ICBC (London) plc"],
    "al-rajhi-bank": ["Al Rajhi Bank"],
}

LEGAL_FORM_TOKENS = {
    "plc", "ltd", "limited", "sa", "nv", "ag", "spa", "ua", "as", "asa", "abp",
    "ab", "inc", "pjsc", "qpsc", "se", "co", "corp", "corporation", "company",
    "publ", "sanv", "girozentrale", "gmbh",
}
TOKEN_CANON = {
    "ltd": "limited",
    "corp": "corporation",
    "incorporated": "inc",
    "aktiengesellschaft": "ag",
}
# multi-word legal forms spelled out in full -> abbreviation (applied after
# diacritics/punctuation are stripped, so "Société Anonyme" is "societe anonyme")
PHRASE_CANON = [
    ("public limited company", "plc"),
    ("sociedad anonima", "sa"),
    ("societe anonyme", "sa"),
    ("societa per azioni", "spa"),
    ("naamloze vennootschap", "nv"),
]
GERMAN = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})


def strip_diacritics(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _tokens(s):
    s = s.replace("&", " and ")
    s = strip_diacritics(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = f" {' '.join(s.split())} "
    for phrase, abbr in PHRASE_CANON:
        s = s.replace(f" {phrase} ", f" {abbr} ")
    toks = s.split()
    # glue runs of single letters: "s a" -> "sa", "p l c" -> "plc", "u a" -> "ua"
    out, run = [], []
    for t in toks + [None]:
        if t is not None and len(t) == 1:
            run.append(t)
            continue
        if run:
            out.append("".join(run))
            run = []
        if t is not None:
            out.append(TOKEN_CANON.get(t, t))
    if out and out[0] == "the":
        out = out[1:]
    if out and out[-1] == "the":
        out = out[:-1]
    return out


def norm_full(s):
    return " ".join(_tokens(s))


def norm_core(s):
    toks = [t for t in _tokens(s) if t not in LEGAL_FORM_TOKENS]
    return " ".join(toks)


def name_forms(s):
    """Set of normalised forms for a GLEIF name: plain and German-transliterated."""
    forms = set()
    for variant in (s, s.translate(GERMAN)):
        forms.add(("full", norm_full(variant)))
        forms.add(("core", norm_core(variant)))
    return forms


def match_level(target_names, gleif_name):
    """Return 'exact', 'core' or None for a GLEIF name vs any accepted target."""
    forms = name_forms(gleif_name)
    for t in target_names:
        if ("full", norm_full(t)) in forms:
            return "exact"
    for t in target_names:
        if ("core", norm_core(t)) in forms:
            return "core"
    return None


class Gleif:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/vnd.api+json"
        self.s.mount("https://", HTTPAdapter(max_retries=Retry(
            total=5, backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504])))
        self.calls = 0

    def search(self, params):
        params = dict(params, **{"page[size]": PAGE_SIZE})
        last = None
        for attempt in range(5):
            try:
                r = self.s.get(API, params=params, timeout=40)
                r.raise_for_status()
                self.calls += 1
                time.sleep(SLEEP)
                return r.json().get("data", [])
            except requests.RequestException as e:  # proxy resets etc.
                last = e
                time.sleep(2 * (attempt + 1))
        raise SystemExit(f"GLEIF request failed repeatedly: {params} ({last})")

    def by_legal_name(self, name, country):
        return self.search({"filter[entity.legalName]": name,
                            "filter[entity.legalAddress.country]": country})

    def by_fulltext(self, text, country):
        return self.search({"filter[fulltext]": text,
                            "filter[entity.legalAddress.country]": country})


def record_view(rec):
    a = rec["attributes"]
    e = a["entity"]
    return {
        "lei": rec["id"],
        "legal_name": e["legalName"]["name"],
        "other_names": [o["name"] for o in (e.get("otherNames") or [])
                        + (e.get("transliteratedOtherNames") or [])],
        "country": (e.get("legalAddress") or {}).get("country"),
        "status": e.get("status"),
        "category": e.get("category"),
        "reg_status": a["registration"]["status"],
    }


def acceptable(v):
    """Records we are willing to pick at all: live entity, current LEI.

    DUPLICATE / ANNULLED / RETIRED / MERGED registrations and non-ACTIVE
    entities are never chosen, even if the name matches perfectly.
    """
    return v["status"] == "ACTIVE" and v["reg_status"] in ("ISSUED", "LAPSED")


def rank(v):
    """Lower is better."""
    return (
        0 if v["reg_status"] == "ISSUED" else 1 if v["reg_status"] == "LAPSED" else 2,
        0 if v["status"] == "ACTIVE" else 1,
        0 if v["category"] == "GENERAL" else 1,
    )


def search_terms(row):
    name = row["name"]
    terms = [name]
    core = norm_core(name)
    if core and core != norm_full(name):
        terms.append(core)  # e.g. "Credit Agricole" without the "S.A."
    for alias in SEARCH_ALIASES.get(row["id"], []):
        terms.append(alias)
        acore = norm_core(alias)
        if acore and acore != norm_full(alias):
            terms.append(acore)
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def resolve(api, row):
    """Return (lei, matched_name, confidence, alternatives, candidates_seen)."""
    country = row["country"]
    targets = [row["name"]] + SEARCH_ALIASES.get(row["id"], [])
    seen = {}
    best = None  # (level_rank, rank, view, via)

    def consider(views):
        nonlocal best
        matches = []
        for v in views:
            if v["country"] != country:
                continue
            seen[v["lei"]] = v
            lvl = match_level(targets, v["legal_name"])
            via = "legal"
            if lvl is None:
                for on in v["other_names"]:
                    lvl = match_level(targets, on)
                    if lvl:
                        via = f"other_name:{on}"
                        break
            if lvl and acceptable(v):
                matches.append((0 if lvl == "exact" else 1, rank(v), v, via))
        return matches

    all_matches = []
    for term in search_terms(row):
        all_matches += consider([record_view(r) for r in api.by_legal_name(term, country)])
        if all_matches:
            break
    if not all_matches:
        for term in search_terms(row):
            all_matches += consider([record_view(r) for r in api.by_fulltext(term, country)])
            if all_matches:
                break

    if not all_matches:
        return None, None, "none", [], list(seen.values())

    # de-duplicate by LEI, keep best entry per LEI
    per_lei = {}
    for m in all_matches:
        k = m[2]["lei"]
        if k not in per_lei or m[:2] < per_lei[k][:2]:
            per_lei[k] = m
    ordered = sorted(per_lei.values(), key=lambda m: m[:2])
    top = ordered[0]
    ties = [m for m in ordered if m[:2] == top[:2]]
    alternatives = [m[2] for m in ordered[1:]]
    if len(ties) > 1:
        return None, None, "ambiguous", [m[2] for m in ties], list(seen.values())

    v = top[2]
    good = v["reg_status"] == "ISSUED" and v["status"] == "ACTIVE" and v["category"] == "GENERAL"
    if top[3].startswith("other_name:"):
        conf = "other_name" if good else "other_name_weak"
    elif top[0] == 0:
        conf = "exact" if good else "exact_weak"
    else:
        conf = "core" if good else "core_weak"
    if v["legal_name"] and norm_full(v["legal_name"]) != norm_full(row["name"]):
        conf += "(alias)" if row["id"] in SEARCH_ALIASES else ""
    return v["lei"], v["legal_name"], conf, alternatives, list(seen.values())


def main(argv):
    dry = "--dry-run" in argv
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    todo = [r for r in rows if not r["lei"].strip()]
    print(f"{len(rows)} rows, {len(todo)} without LEI\n")
    api = Gleif()
    results = []
    for row in todo:
        lei, mname, conf, alts, seen = resolve(api, row)
        results.append((row, lei, mname, conf, alts, seen))
        if lei and not dry:
            row["lei"] = lei

    w = max(len(r["id"]) for r in todo) if todo else 2
    n = max(len(r["name"]) for r in todo) if todo else 4
    print(f"{'id':<{w}}  {'name':<{n}}  {'lei':<20}  {'matched legal name':<55}  confidence")
    print("-" * (w + n + 20 + 55 + 14))
    for row, lei, mname, conf, alts, seen in results:
        print(f"{row['id']:<{w}}  {row['name']:<{n}}  {lei or '':<20}  {(mname or '')[:55]:<55}  {conf}")

    resolved = [x for x in results if x[1]]
    print(f"\nresolved {len(resolved)} / {len(todo)}   (GLEIF calls: {api.calls})")

    flagged = [x for x in results if x[1] and (x[3] != "exact" or x[4])]
    if flagged:
        print("\nChoices worth a second look (non-exact, alias, weak, or with alternatives):")
        for row, lei, mname, conf, alts, seen in flagged:
            print(f"  {row['id']}: {lei}  {mname}  [{conf}]")
            for a in alts:
                print(f"      alt: {a['lei']}  {a['legal_name']}  "
                      f"{a['status']}/{a['category']}/{a['reg_status']}")

    blank = [x for x in results if not x[1]]
    if blank:
        print("\nLeft blank:")
        for row, lei, mname, conf, alts, seen in blank:
            print(f"  {row['id']} ({row['name']}, {row['country']}): {conf}")
            pool = alts if conf == "ambiguous" else seen
            for a in sorted(pool, key=rank)[:6]:
                print(f"      cand: {a['lei']}  {a['legal_name']}  "
                      f"{a['status']}/{a['category']}/{a['reg_status']}")

    if dry:
        print("\n--dry-run: CSV not written")
        return
    if resolved:
        with open(CSV_PATH, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=fields, lineterminator="\r\n")
            wr.writeheader()
            wr.writerows(rows)
        print(f"\nwrote {CSV_PATH}")
    else:
        print("\nnothing to write")


if __name__ == "__main__":
    main(sys.argv[1:])
