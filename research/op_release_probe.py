"""Can a results release be read straight off GlobeNewswire?

OP Corporate Bank stopped filing to the FCA National Storage Mechanism after October 2025,
so the nsm_release adapter's figures for it age out in mid-2027. The releases themselves are
still published, on GlobeNewswire. This probe answers three questions, in order, and prints
what it finds so the answer is evidence rather than assumption:

  1. is globenewswire.com reachable at all from here (it is blocked from the cloud sandbox)
  2. is there a listing that yields the release URLs without rendering JavaScript
  3. does the adapter's existing key_figures() parser read the table in one of those releases

Run it on the Mac:  .venv/bin/python research/op_release_probe.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from bankcredit.adapters.nsm_release import key_figures, period_end

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
# a release we know exists, to separate "host unreachable" from "listing not scrapeable"
KNOWN = ("https://www.globenewswire.com/news-release/2026/02/11/3235943/0/en/"
         "OP-Corporate-Bank-plc-s-Financial-Statements-Bulletin-1-January-31-December-2025.html")
LISTINGS = [
    "https://www.globenewswire.com/en/search/organization/OP%2520Corporate%2520Bank%2520plc",
    "https://www.globenewswire.com/search/organization/OP%2520Corporate%2520Bank%2520plc",
    "https://www.globenewswire.com/RssFeed/organization/qYaEIQg9uzt3EDRvNGZ0Rw%3D%3D/feedTitle/GlobeNewswire-OP-Corporate-Bank-plc",
]
RELEASE_RE = re.compile(r"https://www\.globenewswire\.com/news-release/[^\s\"'<>]+?OP-Corporate-Bank[^\s\"'<>]*\.html", re.I)


def get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=UA, timeout=60)
    except Exception as exc:
        print(f"    unreachable: {type(exc).__name__}: {str(exc)[:120]}")
        return None
    print(f"    HTTP {r.status_code}, {len(r.content):,} bytes")
    return r if r.status_code == 200 else None


def main() -> int:
    print("1. is the host reachable?")
    known = get(KNOWN)
    if known is None:
        print("\n   Blocked or unreachable from this machine. Nothing below can be tested;")
        print("   the Finnish OAM would be the alternative to look at.")
        return 1

    print("\n2. does the parser read the table in that release?")
    figures = key_figures(known.text)
    if figures:
        for metric, value in sorted(figures.items()):
            print(f"    {metric:20s} {value}")
        title = re.search(r"<title[^>]*>(.*?)</title>", known.text, re.S | re.I)
        headline = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else ""
        print(f"    headline           {headline[:100]}")
        print(f"    period end         {period_end(headline)}")
    else:
        print("    nothing matched. The table markup differs from the NSM copy;")
        print("    print a few rows to see how before extending the adapter:")
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", known.text, re.S | re.I)[:8]
        for row in rows:
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
            print("      " + " | ".join(cells)[:140])

    print("\n3. is there a listing that yields release URLs without JavaScript?")
    for url in LISTINGS:
        print(f"  {url}")
        r = get(url)
        if r is None:
            continue
        found = sorted(set(RELEASE_RE.findall(r.text)))
        print(f"    {len(found)} OP Corporate Bank release links")
        for u in found[:8]:
            print(f"      {u}")
        if found:
            print("\n   Use this listing as the GlobeNewswire backend's entry point.")
            return 0

    print("\n   No listing worked without JavaScript. Options: drive it with the browser")
    print("   collector, or read the Finnish OAM instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
