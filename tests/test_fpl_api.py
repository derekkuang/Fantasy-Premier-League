"""FPLClient endpoint tests — URL construction + payload parsing, no network.

A fake session records the requested URL and returns a canned JSON body, so we can
assert entry_picks hits the right path and picks_summary normalises bank/captaincy.
"""

from __future__ import annotations

from fpledge import config
from fpledge.ingest.fpl_api import FPLClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.headers = {}
        self._payload = payload
        self.requested_url = None
        self.requested_timeout = None

    def get(self, url, timeout=None):
        self.requested_url = url
        self.requested_timeout = timeout
        return _FakeResponse(self._payload)


_PICKS_PAYLOAD = {
    "picks": [
        {"element": 101, "position": 1, "multiplier": 1, "is_captain": False, "is_vice_captain": False},
        {"element": 202, "position": 2, "multiplier": 2, "is_captain": True, "is_vice_captain": False},
        {"element": 303, "position": 3, "multiplier": 1, "is_captain": False, "is_vice_captain": True},
    ],
    "entry_history": {"bank": 15, "value": 1004, "event_transfers": 1},
}


def test_entry_picks_builds_correct_url():
    session = _FakeSession(_PICKS_PAYLOAD)
    client = FPLClient(session=session)
    raw = client.entry_picks(1234567, 5)
    assert session.requested_url == f"{config.FPL_API_BASE}/entry/1234567/event/5/picks/"
    assert raw == _PICKS_PAYLOAD


def test_picks_summary_normalises_bank_and_captaincy():
    client = FPLClient(session=_FakeSession(_PICKS_PAYLOAD))
    s = client.picks_summary(1234567, 5)
    assert s["element_ids"] == [101, 202, 303]
    assert s["captain"] == 202
    assert s["vice_captain"] == 303
    assert s["bank"] == 1.5          # 15 tenths -> £1.5m
    assert s["squad_value"] == 100.4


def test_picks_summary_tolerates_missing_history():
    client = FPLClient(session=_FakeSession({"picks": []}))
    s = client.picks_summary(1, 1)
    assert s["element_ids"] == []
    assert s["captain"] is None
    assert s["bank"] == 0.0
