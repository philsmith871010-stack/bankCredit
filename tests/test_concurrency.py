"""Fetching several items at once, and nothing else at once.

The daily run spent twenty-eight of its thirty-five minutes waiting: a hundred and fifty bank
websites, a news feed and a data API, each asked one question at a time. Overlapping the waiting is
most of the saving, and it is safe only under two conditions - a session is never shared between
threads, and only one thread ever writes to the store, because a write rewrites its whole table.
Both are asserted here, along with the thing that would be easy to lose in the change: an item that
fails must not take the rest of the run with it.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import pytest

from bankcredit import store
from bankcredit.adapters.base import Adapter, ThreadSession


class Counting(Adapter):
    """Records which thread did what, so the test can assert where the work happened."""
    name = "counting"

    def __init__(self, items, delay=0.05, fail_on=()):
        self.items, self.delay, self.fail_on = items, delay, set(fail_on)
        self.fetch_threads, self.other_threads, self.loaded = [], [], []
        self.live, self.most_at_once, self._lock = 0, 0, threading.Lock()

    def discover(self):
        return list(self.items)

    def fetch(self, item):
        with self._lock:
            self.live += 1
            self.most_at_once = max(self.most_at_once, self.live)
        try:
            self.fetch_threads.append(threading.current_thread().name)
            time.sleep(self.delay)
            if item in self.fail_on:
                raise RuntimeError(f"{item} is unreachable")
            return item
        finally:
            with self._lock:
                self.live -= 1

    def parse(self, item, raw):
        self.other_threads.append(threading.current_thread().name)
        return [raw]

    def load(self, records):
        self.other_threads.append(threading.current_thread().name)
        self.loaded += records
        return len(records)


@pytest.fixture(autouse=True)
def _scratch_runs(tmp_path, monkeypatch):
    """run() logs a row; keep that out of the repository's own tables."""
    monkeypatch.setattr(store, "DATA", tmp_path)


# ---- the waiting overlaps --------------------------------------------------------------------
def test_a_serial_adapter_fetches_one_at_a_time():
    a = Counting(range(6), delay=0.02)
    a.workers = 1
    a.run()
    assert a.most_at_once == 1
    assert len(set(a.fetch_threads)) == 1


def test_a_concurrent_adapter_fetches_several_at_a_time():
    a = Counting(range(12), delay=0.05)
    a.workers = 4
    started = time.monotonic()
    total, status = a.run()
    elapsed = time.monotonic() - started
    assert a.most_at_once > 1
    assert elapsed < 12 * 0.05, "twelve fetches of 50ms took as long as doing them one after another"
    assert (total, status) == (12, "ok")
    assert sorted(a.loaded) == list(range(12))


def test_the_worker_count_can_be_forced_from_the_environment(monkeypatch):
    """A way to take concurrency out of the picture when chasing a fault in a source."""
    monkeypatch.setenv("BANKCREDIT_WORKERS", "1")
    a = Counting(range(6), delay=0.01)
    a.workers = 6
    a.run()
    assert a.most_at_once == 1


# ---- and nothing else does -------------------------------------------------------------------
def test_parsing_and_loading_stay_on_one_thread():
    """A store write rewrites its whole table. Two at once would lose one of them."""
    a = Counting(range(12), delay=0.02)
    a.workers = 4
    a.run()
    assert set(a.other_threads) == {threading.current_thread().name}


def test_every_item_is_loaded_exactly_once():
    a = Counting(range(30), delay=0.005)
    a.workers = 8
    a.run()
    assert sorted(a.loaded) == list(range(30))


# ---- a failure stays local -------------------------------------------------------------------
def test_one_unreachable_source_does_not_take_the_others_with_it():
    a = Counting(range(10), delay=0.01, fail_on=[3, 7])
    a.workers = 4
    total, status = a.run()
    assert total == 8 and status == "partial"
    assert sorted(a.loaded) == [0, 1, 2, 4, 5, 6, 8, 9]


def test_the_run_row_names_what_failed(tmp_path):
    a = Counting(range(4), delay=0.01, fail_on=[2])
    a.workers = 3
    a.run()
    message = store.read("runs").iloc[-1].message
    assert "2: 2 is unreachable" in message


# ---- sessions are not shared ------------------------------------------------------------------
def test_each_thread_gets_its_own_session_carrying_the_same_headers():
    s = ThreadSession()
    s.headers["User-Agent"] = "test agent"
    seen = {}

    def grab(n):
        seen[n] = (id(s._session()), s._session().headers["User-Agent"])

    threads = [threading.Thread(target=grab, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    ids = {v[0] for v in seen.values()}
    assert len(ids) == 4, "a Session was shared between threads"
    assert {v[1] for v in seen.values()} == {"test agent"}


def test_a_setting_made_before_the_threads_start_reaches_all_of_them():
    s = ThreadSession()
    s.verify = False
    out = []
    t = threading.Thread(target=lambda: out.append(s._session().verify))
    t.start(); t.join()
    assert out == [False]


# ---- the store holds one writer ---------------------------------------------------------------
def test_concurrent_writes_do_not_lose_rows(tmp_path, monkeypatch):
    """Without the lock the last writer wins outright and most of the rows vanish."""
    monkeypatch.setattr(store, "DATA", tmp_path)

    def write(i):
        store.upsert("series", [{"series_id": f"s{i}", "date": "2026-01-01", "value": i,
                                 "unit": "bp", "label": "t", "source": "test"}])

    threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(store.read("series")) == 20
