"""filings.xbrl.org closed the connection on about two thirds of the filers in both runs on
1 November 2026, and each was lost until the next run because every request was tried once."""
from __future__ import annotations

import pytest
import requests

from bankcredit.adapters import esef


class Resp:
    def __init__(self, status):
        self.status_code = status


class Session:
    """Answers from a script: an exception to raise or a status to return, in turn."""
    def __init__(self, *script):
        self.script, self.calls = list(script), 0

    def get(self, url, timeout):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return Resp(step)


def test_a_dropped_connection_is_tried_again_and_the_answer_kept():
    s, waited = Session(requests.ConnectionError("aborted"), requests.ConnectionError("aborted"), 200), []
    r = esef.get(s, "u", 60, sleep=waited.append)
    assert r.status_code == 200 and s.calls == 3
    assert waited == list(esef.WAITS[:2])


def test_a_busy_or_failing_server_is_tried_again():
    s = Session(503, 429, 200)
    assert esef.get(s, "u", 60, sleep=lambda _: None).status_code == 200 and s.calls == 3


def test_an_answer_is_not_retried():
    s = Session(404)
    assert esef.get(s, "u", 60, sleep=lambda _: None).status_code == 404 and s.calls == 1


def test_after_the_last_attempt_the_failure_is_reported():
    s = Session(*[requests.ConnectionError("aborted")] * (len(esef.WAITS) + 1))
    with pytest.raises(requests.ConnectionError):
        esef.get(s, "u", 60, sleep=lambda _: None)
    assert s.calls == len(esef.WAITS) + 1
    s = Session(*[502] * (len(esef.WAITS) + 1))
    assert esef.get(s, "u", 60, sleep=lambda _: None).status_code == 502


def test_a_register_that_is_down_stops_costing_the_whole_wait(monkeypatch):
    """After GIVE_UP_AFTER requests fail with their retries, the rest are tried once each."""
    monkeypatch.setattr(esef.time, "sleep", lambda _: None)
    a = esef.EsefAdapter.__new__(esef.EsefAdapter)
    a.session = Session(*[requests.ConnectionError("down")] * 100)
    for _ in range(esef.GIVE_UP_AFTER):
        with pytest.raises(requests.ConnectionError):
            a._get("u", 60)
    assert a.session.calls == esef.GIVE_UP_AFTER * (len(esef.WAITS) + 1)
    before = a.session.calls
    with pytest.raises(requests.ConnectionError):
        a._get("u", 60)
    assert a.session.calls == before + 1, "one attempt once the register looks down"
