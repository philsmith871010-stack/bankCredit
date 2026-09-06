"""Adapter interface. Each source implements discover/fetch/parse/validate/load.

Run everything with `python -m bankcredit.cli run <name>`; the CLI logs a run row
so the Status page can show freshness and failures.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Iterable

import requests

from .. import store
from ..entities import load as load_entities
from ..models import Entity

log = logging.getLogger("bankcredit")
REGISTRY: dict[str, type["Adapter"]] = {}
UA = "PWLBtoday Counterparty research bot (philsmith871010@gmail.com)"


def register(cls):
    REGISTRY[cls.name] = cls
    return cls


class Adapter:
    name = "base"
    cadence = "daily"          # daily | weekly | quarterly
    regions: tuple[str, ...] = ()   # empty means all

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        only = {x for x in os.environ.get("BANKCREDIT_ONLY", "").split(",") if x}
        self.entities: list[Entity] = [e for e in load_entities() if e.active and (not self.regions or e.region in self.regions)
                                       and (not only or e.id in only)]

    # ---- pipeline steps; override what applies ----
    def discover(self) -> Iterable:
        """Yield work items (entities, documents, dates)."""
        return self.entities

    def fetch(self, item):
        raise NotImplementedError

    def parse(self, item, raw) -> list:
        raise NotImplementedError

    def validate(self, records: list) -> list:
        return records

    def load(self, records: list) -> int:
        raise NotImplementedError

    def run(self) -> tuple[int, str]:
        started = datetime.utcnow()
        total, errors = 0, []
        for item in self.discover():
            try:
                raw = self.fetch(item)
                if raw is None:
                    continue
                recs = self.validate(self.parse(item, raw))
                total += self.load(recs)
            except Exception as exc:  # keep going, report at the end
                errors.append(f"{getattr(item, 'id', item)}: {exc}")
                log.warning("%s failed on %s: %s", self.name, getattr(item, "id", item), exc)
        status = "ok" if not errors else ("partial" if total else "failed")
        store.log_run(self.name, status, total, "; ".join(errors)[:500], started)
        return total, status
