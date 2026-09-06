"""Probe: current issuer-level bank ratings from the ESMA European Rating Platform.

Public Solr endpoint behind registers.esma.europa.eu. Coverage is global because
Moody's, S&P, Fitch, DBRS, KBRA, Scope and JCR endorse their ratings into the EU.
parent docs = current state of each rating; child docs = action history.
ratedObjectCode ISR = issuer-level, INT = instrument-level.

Usage: python research/esma_ratings_probe.py "Nationwide Building Society" ["Barclays Bank PLC" ...]
"""
import sys

import requests

SOLR = "https://registers.esma.europa.eu/solr/esma_registers_radar/select"
FIELDS = "craName,ratingValueLabel,timeHorizonDescr,issuerRatingName,ratingStatusLabel,lastActionTypeLabel,racValidityDatetimeStr,issuerLeiCode"


def issuer_ratings(name: str):
    params = {"q": f'issuerName:"{name}"', "fq": ["type_s:parent", "ratedObjectCode:ISR", "-ratingStatusLabel:Withdrawal"],
              "rows": 200, "sort": "racValidityDatetime desc", "fl": FIELDS, "wt": "json"}
    r = requests.get(SOLR, params=params, timeout=120)
    r.raise_for_status()
    return r.json()["response"]["docs"]


def main():
    names = sys.argv[1:] or ["Nationwide Building Society", "Barclays Bank PLC", "Starling Bank Limited"]
    for name in names:
        docs = issuer_ratings(name)
        print(f"\n{name}: {len(docs)} live issuer-level records")
        seen = set()
        for d in docs:
            key = (d["craName"], d.get("timeHorizonDescr"), d.get("issuerRatingName"))
            if key in seen:
                continue
            seen.add(key)
            print(f"  {d['craName'][:34]:34s} {d.get('timeHorizonDescr','')[:10]:10s} {str(d.get('issuerRatingName',''))[:36]:36s} "
                  f"{d.get('ratingValueLabel',''):8s} {d.get('racValidityDatetimeStr','')}  {d.get('ratingStatusLabel','') or ''}")


if __name__ == "__main__":
    main()
