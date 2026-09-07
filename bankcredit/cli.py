"""Command line entry point.

  python -m bankcredit.cli run fdic eba esma yahoo   # run adapters
  python -m bankcredit.cli build                     # export JSON and build the site
  python -m bankcredit.cli list                      # list adapters
  python -m bankcredit.cli extract file.pdf          # try the KM1 extractor on one PDF (no load)
  python -m bankcredit.cli pdf <entity> file.pdf [url]  # extract one PDF and load or queue it
  python -m bankcredit.cli review list|ingest        # review queue for failed extractions
  python -m bankcredit.cli learn                     # what the reviewer's answers taught the extractor
  python -m bankcredit.cli browser [entity ...]      # bot-blocked sites: plain request, then headless Chromium
  python -m bankcredit.cli reprocess [entity]        # re-extract cached PDFs after an extractor change
"""
from __future__ import annotations

import importlib
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ADAPTER_MODULES = ["fdic", "eba", "esma", "yahoo", "pillar3", "events", "fred", "dtcc", "ice", "bonds", "edgar"]


def _load_adapters():
    from .adapters import REGISTRY
    for m in ADAPTER_MODULES:
        try:
            importlib.import_module(f"bankcredit.adapters.{m}")
        except ModuleNotFoundError:
            pass
    return REGISTRY


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        for n, c in _load_adapters().items():
            print(f"{n:10s} {c.cadence:10s} {','.join(c.regions) or 'all'}")
        return 0
    if cmd == "run":
        reg = _load_adapters()
        names = args or list(reg)
        rc = 0
        for n in names:
            if n not in reg:
                print(f"unknown adapter {n}"); rc = 1; continue
            total, status = reg[n]().run()
            print(f"{n}: {status}, {total} rows")
            rc = rc or (status == "failed")
        return rc
    if cmd == "extract":
        from .extract import km1
        res = km1.extract(args[0])
        print(f"pages {res.pages} template {res.template!r} date {res.reference_date} {res.currency} conf {res.confidence}")
        for k, v in res.values.items():
            print(f"  {k:28s} {v:,.2f}")
        for sev, msg in res.checks:
            print(f"  [{sev}] {msg}")
        return 0 if res.ok else 1
    if cmd == "pdf":
        from .adapters.pillar3 import Pillar3Adapter
        if len(args) < 2:
            print("usage: pdf <entity> <file.pdf> [source-url]"); return 1
        status, res = Pillar3Adapter().process_file(args[0], args[1], args[2] if len(args) > 2 else "")
        print(f"{args[0]}: {status} (confidence {res.confidence}, date {res.reference_date}, page {res.page})")
        for sev, msg in res.checks:
            print(f"  [{sev}] {msg}")
        return 0 if status in ("loaded", "unverified") else 1
    if cmd == "prune-news":
        from .adapters.events import prune_news
        print(f"dropped {prune_news()} rows")
        return 0
    if cmd == "reprocess":
        from .adapters.pillar3 import Pillar3Adapter
        print(Pillar3Adapter().reprocess(args[0] if args else None))
        return 0
    if cmd == "browser":
        from .adapters.browser import collect
        res = collect(args or None)
        for k, v in res.items():
            print(f"  {k:34s} {v}")
        blocked = [k for k, v in res.items() if v.startswith("blocked")]
        print(f"{len(res)} sites tried; {len(blocked)} still need the Chrome extension: {', '.join(blocked) or 'none'}")
        return 0
    if cmd == "learn":
        from .learn import summary
        import json as _json
        print(_json.dumps(summary(), indent=1))
        return 0
    if cmd == "review":
        from . import review
        sub = args[0] if args else "list"
        if sub == "ingest":
            print(f"ingested {review.ingest()} facts")
            return 0
        items = review.load()
        print(f"{len(items)} open items")
        for it in items:
            print(f"  {it['id']}  {it['entity_id']:28s} {it.get('reference_date') or '?':10s} p.{it.get('page') or '-':<4} {it['reason'][:90]}")
        return 0
    if cmd == "build":
        from .site.build import build
        from .export import export_json
        export_json()
        build()
        return 0
    print(f"unknown command {cmd}"); return 1


if __name__ == "__main__":
    sys.exit(main())
