"""Probe: search the FCA National Storage Mechanism (NSM) for Pillar 3 filings.

The NSM web app (data.fca.org.uk) is backed by an undocumented JSON search API.
Request shape mirrors the app's own: headline is a plain string, company_lei is a
list [name, lei], dates are ISO with trailing Z. Download links live under
https://data.fca.org.uk/artefacts/.

Usage: python research/fca_nsm_probe.py ["Pillar 3"] [from YYYY-MM-DD]
"""
import json
import sys

import requests

API = "https://api.data.fca.org.uk/search?index=nsm-search"
ARTEFACTS = "https://data.fca.org.uk/artefacts/"
HEADERS = {"Content-Type": "application/json", "Origin": "https://data.fca.org.uk",
           "Referer": "https://data.fca.org.uk/",
           "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/128 Safari/537.36"}


def search(headline: str, date_from: str, date_to: str = "2030-01-01", size: int = 300):
    body = {"from": 0, "size": size, "sortorder": "desc",
            "criteriaObj": {"criteria": [{"name": "headline", "value": headline}],
                            "dateCriteria": [{"name": "publication_date",
                                              "value": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"}}]}}
    r = requests.post(API, headers=HEADERS, json=body, timeout=90)
    r.raise_for_status()
    return [h["_source"] for h in r.json()["hits"]["hits"]]


def main():
    headline = sys.argv[1] if len(sys.argv) > 1 else "Pillar 3"
    date_from = sys.argv[2] if len(sys.argv) > 2 else "2025-01-01"
    hits = search(headline, date_from)
    print(f"{len(hits)} hits for headline '{headline}' since {date_from}")
    for s in sorted(hits, key=lambda s: s["publication_date"], reverse=True):
        print(f"{s['publication_date'][:10]}  {s['company'].strip(';'):45s} {s['headline'].strip()[:50]:50s} "
              f"{s['source']:14s} {ARTEFACTS}{s['download_link']}")


if __name__ == "__main__":
    main()
