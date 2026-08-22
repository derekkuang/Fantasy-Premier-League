"""The shared retrying GET every ingest client sits on.

The captures collect data that cannot be re-fetched later, so the transport layer gets the
same paranoia as the storage layer: transient failures (timeouts, resets, 5xx) are retried;
meaningful statuses (404, 401, 429) come back immediately because retrying them turns a clear
answer into a slow one — or, on a metered API, a paid one.
"""

from __future__ import annotations

import pytest
import requests

from fpledge.ingest import httpget
from fpledge.ingest.httpget import get_with_retries


class _Resp:
    def __init__(self, status):
        self.status_code = status


class _Session:
    """Serves a script of responses/exceptions, one per attempt, and records the calls."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def get(self, url, timeout=None, **kwargs):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return _Resp(step)


def test_a_transient_5xx_is_retried_and_the_recovery_returned():
    s = _Session(503, 200)
    assert get_with_retries(s, "http://x", timeout=1).status_code == 200
    assert s.calls == 2


def test_a_transport_failure_is_retried_and_the_recovery_returned():
    s = _Session(requests.ConnectTimeout("slow"), 200)
    assert get_with_retries(s, "http://x", timeout=1).status_code == 200
    assert s.calls == 2


def test_the_final_5xx_is_returned_for_the_caller_to_classify():
    """After the last attempt a 5xx comes BACK rather than raising: each client owns its
    status handling and its own domain error type."""
    s = _Session(500, 500, 500)
    assert get_with_retries(s, "http://x", timeout=1, attempts=3).status_code == 500
    assert s.calls == 3


def test_transport_failure_on_every_attempt_raises_the_original_exception():
    """The caller wraps this into its domain error; the original type must survive to be named."""
    s = _Session(requests.ReadTimeout("a"), requests.ReadTimeout("b"), requests.ReadTimeout("c"))
    with pytest.raises(requests.ReadTimeout, match="c"):
        get_with_retries(s, "http://x", timeout=1, attempts=3)
    assert s.calls == 3


@pytest.mark.parametrize("status", [404, 401, 429])
def test_a_meaningful_status_is_never_retried(status):
    """404 is an answer, 401 is an answer, and 429 on a metered API means every retry is a
    request the quota cannot spare. One call, straight back to the caller."""
    s = _Session(status)
    assert get_with_retries(s, "http://x", timeout=1).status_code == status
    assert s.calls == 1


def test_backoff_grows_between_attempts(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(httpget, "_sleep", slept.append)
    s = _Session(500, 500, 200)
    get_with_retries(s, "http://x", timeout=1, attempts=3, backoff_s=1.0)
    assert len(slept) == 2, "no sleep before the first attempt, one before each retry"
    assert slept[1] > slept[0], "the second wait must be longer than the first"


def test_a_single_attempt_never_sleeps(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(httpget, "_sleep", slept.append)
    s = _Session(200)
    get_with_retries(s, "http://x", timeout=1)
    assert slept == []


def test_before_attempt_runs_before_every_attempt_not_just_the_first():
    """The hook is the clients' politeness throttle. A retry that skips it sends extra
    requests inside the very interval the throttle promised to respect, at the moment the
    host just said it was struggling — retry amplification wearing a resilience costume."""
    calls: list[str] = []
    s = _Session(503, 503, 200)
    get_with_retries(s, "http://x", timeout=1, attempts=3,
                     before_attempt=lambda: calls.append("throttle"))
    assert calls == ["throttle"] * 3


@pytest.mark.parametrize("exc_name", ["SSLError", "TooManyRedirects", "MissingSchema"])
def test_a_deterministic_transport_failure_is_never_retried(exc_name):
    """A bad certificate, a redirect loop, a malformed URL — answers, not weather. Retrying
    them costs seconds per club per run forever and returns the identical exception. SSLError
    is the trap: requests makes it a ConnectionError subclass, so a naive isinstance check
    would retry it with the genuinely transient resets."""
    exc = getattr(requests.exceptions, exc_name)("permanent")
    s = _Session(exc, 200)
    with pytest.raises(type(exc)):
        get_with_retries(s, "http://x", timeout=1)
    assert s.calls == 1, f"{exc_name} must fail on the first attempt, not be retried"
