"""Thin client for the official (unauthenticated) Fantasy Premier League API.

Endpoints used:
    bootstrap-static/      players, teams, events, prices, ownership, status
    fixtures/              fixtures (optionally by event/gameweek)
    element-summary/{id}/  per-player match-by-match history
    event/{gw}/live/       live/provisional points + bonus during a gameweek
    entry/{id}/            a manager's team (for your own squad)
    entry/{id}/event/{gw}/picks/  a manager's 15 picks + bank for a gameweek

`requests` is a declared dependency; imported lazily so the stdlib-only core and
its tests don't require it.
"""

from __future__ import annotations

import time

from .. import config


class FPLClient:
    """Polite, retrying-free client. Add retries/backoff before going to prod."""

    def __init__(self, session=None, min_interval: float | None = None):  # noqa: ANN001
        import requests  # noqa: PLC0415

        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.HTTP_USER_AGENT})
        self._last_call = 0.0
        self._min_interval = (
            config.FPL_API_MIN_INTERVAL_S if min_interval is None else min_interval
        )

    def _get(self, path: str):
        url = f"{config.FPL_API_BASE}/{path}"
        resp = self.session.get(url, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last_call
        if dt < self._min_interval:
            time.sleep(self._min_interval - dt)
        self._last_call = time.monotonic()

    # --- endpoints ------------------------------------------------------- #
    def bootstrap_static(self) -> dict:
        return self._get("bootstrap-static/")

    def fixtures(self, event: int | None = None) -> list:
        return self._get("fixtures/" if event is None else f"fixtures/?event={event}")

    def element_summary(self, element_id: int) -> dict:
        self._throttle()  # ~700 players; be gentle
        return self._get(f"element-summary/{element_id}/")

    def event_live(self, gameweek: int) -> dict:
        return self._get(f"event/{gameweek}/live/")

    def entry(self, entry_id: int) -> dict:
        return self._get(f"entry/{entry_id}/")

    def entry_picks(self, entry_id: int, gw: int) -> dict:
        """A manager's team for a gameweek: `picks` (15 elements + captaincy/multiplier)
        and `entry_history` (bank, squad value, transfers). Raises for HTTP errors
        (404 for a private/nonexistent entry or a gameweek the manager hasn't entered).
        """
        self._throttle()  # rate-limit outbound calls so a busy server can't get IP-blocked
        return self._get(f"entry/{entry_id}/event/{gw}/picks/")

    def picks_summary(self, entry_id: int, gw: int) -> dict:
        """Normalised view of `entry_picks`: the 15 element ids, the captain/vice element
        ids, and the bank in £m (the API reports bank in tenths). A thin convenience so
        callers don't re-parse the raw payload shape.
        """
        raw = self.entry_picks(entry_id, gw)
        picks = raw.get("picks", [])
        hist = raw.get("entry_history") or {}
        cap = next((p["element"] for p in picks if p.get("is_captain")), None)
        vice = next((p["element"] for p in picks if p.get("is_vice_captain")), None)
        return {
            "element_ids": [p["element"] for p in picks],
            "captain": cap,
            "vice_captain": vice,
            "bank": (hist.get("bank") or 0) / 10.0,   # tenths of £m -> £m
            "squad_value": (hist.get("value") or 0) / 10.0,
        }
