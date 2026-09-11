"""Adapter interface. Each source implements discover/fetch/parse/validate/load.

Run everything with `python -m bankcredit.cli run <name>`; the CLI logs a run row
so the Status page can show freshness and failures.
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class ThreadSession:
    """A requests Session per thread, behind one object the adapter can hold.

    A Session is not safe to share across threads, and the fetch phase now runs several at once.
    Headers live on this object rather than on any one session, so an adapter that sets a user
    agent in its __init__ - as the news and FRED adapters do, to look like a browser - still has it
    applied to every worker's session as that worker makes one.
    """

    _OWN = ("headers", "_local", "_extra")

    def __init__(self, headers: dict | None = None):
        object.__setattr__(self, "headers", dict(headers or {}))
        object.__setattr__(self, "_local", threading.local())
        object.__setattr__(self, "_extra", {})

    def _session(self) -> requests.Session:
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update(self.headers)
            for k, v in self._extra.items():
                setattr(s, k, v)
            self._local.s = s
        return s

    def __getattr__(self, name):                 # get, post, cookies, mount, everything else
        return getattr(self._session(), name)

    def __setattr__(self, name, value):
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:                                    # remembered, so later threads are configured too
            self._extra[name] = value
            setattr(self._session(), name, value)


class Adapter:
    name = "base"
    cadence = "daily"          # daily | weekly | quarterly
    regions: tuple[str, ...] = ()   # empty means all
    # How many items to fetch at once. One by default: an adapter opts in only where its items are
    # independent requests and the source can take them, and says in a comment why that is true.
    # Nothing else is made concurrent - see run().
    workers = 1

    def __init__(self):
        self.session = ThreadSession()
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

    def _fetched(self, items: list):
        """Yield (item, raw, error) for every item, fetching several at a time where the adapter
        allows it.

        Only the fetch is concurrent, and deliberately so: parse, validate and load stay on the
        calling thread. A store write rewrites its whole table, so the work worth overlapping is
        the waiting - a hundred and fifty bank sites answering at their own pace - not the handful
        of seconds spent reading what came back. Results are taken in the order they arrive, so one
        slow site holds nothing else up.
        """
        n = max(1, int(os.environ.get("BANKCREDIT_WORKERS") or self.workers))
        if n == 1 or len(items) < 2:
            for item in items:
                try:
                    yield item, self.fetch(item), None
                except Exception as exc:                        # noqa: BLE001 - reported per item
                    yield item, None, exc
            return
        with ThreadPoolExecutor(max_workers=min(n, len(items)), thread_name_prefix=self.name) as pool:
            pending = {pool.submit(self.fetch, item): item for item in items}
            for future in as_completed(pending):
                item = pending[future]
                try:
                    yield item, future.result(), None
                except Exception as exc:                        # noqa: BLE001 - reported per item
                    yield item, None, exc

    def skip(self) -> str | None:
        """Why this adapter cannot run today, or None if it can.

        A source that needs a credential nobody has configured is not a failure. Reported as one it
        prints a red line every morning, and a red line that is always there is the one nobody
        reads - which is how a real failure goes unnoticed.
        """
        return None

    def run(self) -> tuple[int, str]:
        started = datetime.utcnow()
        why = self.skip()
        if why:
            log.info("%s skipped: %s", self.name, why)
            store.log_run(self.name, "skipped", 0, why, started)
            return 0, "skipped"
        total, errors = 0, []
        for item, raw, failure in self._fetched(list(self.discover())):
            name = getattr(item, "id", item)
            if failure is None and raw is not None:
                try:
                    recs = self.validate(self.parse(item, raw))
                    total += self.load(recs)
                except Exception as exc:  # keep going, report at the end
                    failure = exc
            if failure is not None:
                errors.append(f"{name}: {failure}")
                log.warning("%s failed on %s: %s", self.name, name, failure)
        status = "ok" if not errors else ("partial" if total else "failed")
        store.log_run(self.name, status, total, "; ".join(errors)[:500], started)
        return total, status
