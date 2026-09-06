"""Probe: ICE Clear Credit end-of-day settlement prices for cleared 5-year CDS.

Open JSON, no login:
  https://www.ice.com/api/cds-settlement-prices/icc-single-names
  https://www.ice.com/api/cds-settlement-prices/icc-indexes
Only the current day is served (no history parameter), so snapshot daily.
Instrument name encodes ticker.tier.currency.docclause.coupon.maturity, e.g.
BACR.SUBLT2.EUR.MM14.100.2031-06-20. Price is clean price in percent of par;
a rough par spread is coupon minus (price-100)/annuity. ICE terms of use restrict
redistribution: fine for internal scoring inputs, not for public re-display.

Usage: python research/ice_cds_probe.py
"""
import re

import requests

BANKS = re.compile(r"BARCLAYS|HSBC|LLOYDS|NATWEST|DEUTSCHE|SANTANDER|BNP|SOC|UBS|AGRICOLE|ING |UNICREDIT|INTESA|JPM|CITI|BANK OF AMER|GOLDMAN|MORGAN|WELLS|STANDARD CHART|COMMERZ|NORDEA|DANSKE|RABO|MEDIOBANCA|SWEDBANK|HANDELSB|MACQUARIE|WESTPAC|NATL AUST|AUST & NEW|COMWLTH BK|PNC|BK OF SCOTLAND|CAPITAL ONE", re.I)


def rough_spread_bp(price: float, coupon_bp: float, years: float = 4.8) -> float:
    annuity = (1 - 1.03 ** (-years)) / 0.03 * 0.97
    return coupon_bp - (price - 100) * 100 / annuity


def main():
    rows = requests.get("https://www.ice.com/api/cds-settlement-prices/icc-single-names", timeout=60, headers={"User-Agent": "Mozilla/5.0"}).json()
    banks = [r for r in rows if BANKS.search(r["name"] + " " + r["instrumentName"])]
    print(f"{len(rows)} instruments, {len(banks)} bank rows, clearing date {rows[0]['clearingDate']}")
    print(f"{'name':28s} {'tier':7s} {'cpn':>4s} {'price':>9s} {'~spread bp':>10s}")
    for r in sorted(banks, key=lambda r: (r["name"], r["instrumentName"])):
        parts = r["instrumentName"].split(".")
        tier, coupon = parts[1], float(parts[4])
        if coupon != 100 or "14" not in parts[3]:
            continue  # standard 100bp coupon, 2014 definitions only
        print(f"{r['name'][:28]:28s} {tier:7s} {coupon:4.0f} {float(r['eodPrice']):9.4f} {rough_spread_bp(float(r['eodPrice']), coupon):10.0f}")


if __name__ == "__main__":
    main()
