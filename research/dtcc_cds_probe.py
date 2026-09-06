"""Probe: single-name bank CDS trade prices from DTCC's public swap-data dissemination.

Under US post-trade transparency rules DTCC publishes every reported credit derivative
trade (security-based swaps to the SEC, index swaps to the CFTC) in daily cumulative
zip files on a public S3 bucket, no registration:
  https://kgc0418-tdw-data-0.s3.amazonaws.com/sec/eod/SEC_CUMULATIVE_CREDITS_YYYY_MM_DD.zip
  https://kgc0418-tdw-data-0.s3.amazonaws.com/cftc/eod/CFTC_CUMULATIVE_CREDITS_YYYY_MM_DD.zip
Files exist from about June 2024. Each row has reference entity (name and RED code),
seniority (UPI FISN ends Sr/Sub), maturity, fixed coupon, upfront payment (UFRO) and
notional (capped, shown with a trailing +). Trade direction is not disclosed, so the
spread is inferred assuming the protection seller pays the upfront (true for
investment-grade banks trading below the 100bp coupon); block trades with capped
notional distort the upfront ratio, so use a median across trades.

Usage: python research/dtcc_cds_probe.py [business_days=20]
"""
import collections
import csv
import datetime as dt
import io
import re
import statistics
import sys
import zipfile

import requests

BASE = "https://kgc0418-tdw-data-0.s3.amazonaws.com/sec/eod/SEC_CUMULATIVE_CREDITS_{:%Y_%m_%d}.zip"
BANKS = re.compile(r"BARCLAYS|HSBC|LLOYDS|NATWEST|DEUTSCHE BANK|SANTANDER|BNP|SOCIETE GENERALE|UBS|CREDIT AGRICOLE|\bING\b|UNICREDIT|INTESA|JPMORGAN|CITIGROUP|BANK OF AMERICA|GOLDMAN|MORGAN STANLEY|WELLS FARGO|STANDARD CHARTERED|COMMERZBANK|NORDEA|DANSKE|RABOBANK|ABN AMRO|BILBAO|CAIXA|MITSUBISHI|MIZUHO|SUMITOMO|ROYAL BANK OF CANADA|TORONTO|NOVA SCOTIA|MONTREAL|COMMONWEALTH BANK|WESTPAC|AUSTRALIA AND NEW|NATIONAL AUSTRALIA|MACQUARIE|SWEDBANK|HANDELSBANKEN|SKANDINAVISKA|ERSTE|KBC|DNB|STATE STREET|MELLON|CAPITAL ONE|PNC|TRUIST|MEDIOBANCA|BANCO BPM|SABADELL|AIB|BANK OF IRELAND", re.I)


def load(days: int):
    rows = []
    d = dt.date.today()
    got = 0
    while got < days:
        d -= dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        r = requests.get(BASE.format(d), timeout=60)
        if r.status_code != 200:
            continue
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for n in z.namelist():
            if n.endswith(".csv"):
                rows += list(csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8", errors="ignore")))
        got += 1
    return rows


def implied_spread_bp(r):
    """coupon minus upfront per unit notional over a rough risky annuity."""
    notional = float((r["Notional amount-Leg 1"] or "0").replace(",", "").replace("+", ""))
    upfront = float(r["Other payment amount"] or 0)
    coupon = float(r["Fixed rate-Leg 1"] or 0) * 1e4
    exp = dt.date.fromisoformat(r["Expiration Date"])
    ex = dt.date.fromisoformat(r["Execution Timestamp"][:10])
    t = (exp - ex).days / 365.25
    annuity = (1 - 1.03 ** (-t)) / 0.03 * 0.97
    return coupon - (upfront / notional) * 1e4 / annuity, t


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rows = load(days)
    trades = [r for r in rows if r.get("Action type") == "NEWT" and r.get("Event type") == "TRAD"
              and r.get("Other payment type") == "UFRO" and BANKS.search(r.get("Underlying Asset Name") or "")]
    print(f"{len(rows)} rows over {days} business days; {len(trades)} bank single-name trades with upfront")
    by = collections.defaultdict(list)
    for r in trades:
        try:
            s, t = implied_spread_bp(r)
        except Exception:
            continue
        if 4 <= t <= 6 and s > 0:
            name = re.sub(r"[;,.]", " ", r["Underlying Asset Name"].upper()).split()[0:3]
            by[(" ".join(name), r["UPI FISN"][-3:].strip())].append(s)
    print(f"\n{'reference entity':34s} {'tier':4s} {'n':>3s} {'median 5y bp':>13s} {'range':>14s}")
    for (name, tier), vals in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"{name:34s} {tier:4s} {len(vals):3d} {statistics.median(vals):13.0f} {min(vals):6.0f}-{max(vals):<6.0f}")


if __name__ == "__main__":
    main()
