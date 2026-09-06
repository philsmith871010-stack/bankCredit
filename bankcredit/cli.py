"""Command line entry point.

  python -m bankcredit.cli run fdic eba esma yahoo   # run adapters
  python -m bankcredit.cli build                     # export JSON and build the site
  python -m bankcredit.cli list                      # list adapters
"""
from __future__ import annotations

import importlib
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ADAPTER_MODULES = ["fdic", "eba", "esma", "yahoo", "dtcc", "ice"]


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
    if cmd == "build":
        from .site.build import build
        from .export import export_json
        export_json()
        build()
        return 0
    print(f"unknown command {cmd}"); return 1


if __name__ == "__main__":
    sys.exit(main())
