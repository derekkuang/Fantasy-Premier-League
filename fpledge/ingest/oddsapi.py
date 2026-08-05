"""The Odds API — anytime-goalscorer prices, the one market no historical table contains.

WHY THIS MARKET. §19 measured perfect team news at +0.168 against +0.012 for the best modelling
change available, and §21 measured our xG-fitted engine as already matching the betting market's
view of a FIXTURE. So a market feed is not worth having for its opinion on Arsenal vs Chelsea —
we have that. It is worth having for the two things it uniquely carries:

  * the PLAYER-LEVEL split. An anytime-goalscorer price is a market-clearing P(this player
    scores), which is precisely `goal_share x team_lambda`, the largest term in an attacker's
    projection and the one our model estimates from historical rates.
  * TEAM NEWS, priced in by construction. A player the market expects to be benched is priced
    long. That is a share of the +0.168 without buying a lineup feed and without its accuracy
    ceiling.

COST. Current odds through the event endpoint cost (markets x regions) per event, so one market
in one region across ten Premier League fixtures is ~10 credits per gameweek — against a free
tier of 500 a month. Historical odds cost 10x that, which is what makes forward capture the free
option and back-fill the paid one.

STATUS: THE LIVE PATH IS UNVERIFIED. Written without an API key, so every offline behaviour is
tested and no real request has been made. Two things the first live run must check, both handled
rather than assumed: the exact market key (`list_markets` asks the API instead of trusting the
constant below), and the credit accounting in the response headers.
"""

from __future__ import annotations

import os
import time

from .. import config

BASE = "https://api.the-odds-api.com/v4"
SPORT = "soccer_epl"

# The market key as documented. `list_markets()` exists because a wrong key here would return an
# empty payload rather than an error, and a capture of nothing looks exactly like a quiet week.
GOALSCORER_MARKET = "player_goal_scorer_anytime"
DEFAULT_REGIONS = "uk"
MIN_INTERVAL_S = 0.5


class OddsApiError(RuntimeError):
    pass


class NoApiKey(OddsApiError):
    """Raised rather than returning empty, so a missing key can never look like a quiet week."""


class OddsApiClient:
    """Thin client. Counts credits, because the free tier is the whole point."""

    def __init__(self, api_key: str | None = None, session=None, min_interval: float | None = None):
        import requests

        self.api_key = api_key or os.environ.get("ODDS_API_KEY") or ""
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.HTTP_USER_AGENT})
        self._timeout = config.HTTP_TIMEOUT
        self._min_interval = MIN_INTERVAL_S if min_interval is None else min_interval
        self._last = 0.0
        self.credits_used: int | None = None
        self.credits_remaining: int | None = None

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last
        if dt < self._min_interval:
            time.sleep(self._min_interval - dt)
        self._last = time.monotonic()

    def _get(self, path: str, **params):
        if not self.api_key:
            raise NoApiKey(
                "No ODDS_API_KEY. Get a free key at https://the-odds-api.com (500 credits/month, "
                "which covers ~10 credits per gameweek for this capture many times over)."
            )
        self._throttle()
        resp = self.session.get(
            f"{BASE}/{path}", params={"apiKey": self.api_key, **params}, timeout=self._timeout
        )
        # Header names are lowercase-insensitive through requests' CaseInsensitiveDict.
        used = resp.headers.get("x-requests-used")
        left = resp.headers.get("x-requests-remaining")
        self.credits_used = int(used) if used and used.isdigit() else self.credits_used
        self.credits_remaining = int(left) if left and left.isdigit() else self.credits_remaining
        if resp.status_code == 401:
            raise OddsApiError("401 — the API key was rejected.")
        if resp.status_code == 429:
            raise OddsApiError(
                f"429 — out of credits (remaining={self.credits_remaining}). "
                "The capture did NOT run; this week is lost unless it is re-run in time."
            )
        resp.raise_for_status()
        return resp.json()

    def events(self, sport: str = SPORT) -> list[dict]:
        """Upcoming fixtures with their event ids. Costs no credits."""
        return self._get(f"sports/{sport}/events")

    def list_markets(self, event_id: str, regions: str = DEFAULT_REGIONS, sport: str = SPORT):
        """Which market keys the books actually offer for this event.

        Worth calling once on the first live run: a market key that does not exist returns an
        empty bookmaker list rather than an error, which is indistinguishable from "no book has
        priced this yet" and would silently capture nothing all season.
        """
        return self._get(f"sports/{sport}/events/{event_id}/markets", regions=regions)

    def event_odds(
        self,
        event_id: str,
        markets: str = GOALSCORER_MARKET,
        regions: str = DEFAULT_REGIONS,
        sport: str = SPORT,
        odds_format: str = "decimal",
    ) -> dict:
        """One event's prices for `markets`. Costs (markets x regions) credits."""
        return self._get(
            f"sports/{sport}/events/{event_id}/odds",
            markets=markets, regions=regions, oddsFormat=odds_format,
        )


def goalscorer_prices(event_payload: dict) -> list[dict]:
    """Flatten one event's payload into [{player, price, bookmaker, ...}].

    Prices are left as decimal odds and NOT converted to probabilities here. Converting means
    de-vigging, the overround on a goalscorer market runs to 20-40% across a dozen-plus
    outcomes, and `betting.odds` already owns that decision. A capture script's job is to record
    what the market said, exactly, so the modelling choice stays re-doable later.
    """
    out = []
    for book in event_payload.get("bookmakers", []) or []:
        for market in book.get("markets", []) or []:
            for oc in market.get("outcomes", []) or []:
                out.append({
                    "event_id": event_payload.get("id"),
                    "commence_time": event_payload.get("commence_time"),
                    "home_team": event_payload.get("home_team"),
                    "away_team": event_payload.get("away_team"),
                    "bookmaker": book.get("key"),
                    "market": market.get("key"),
                    "last_update": market.get("last_update") or book.get("last_update"),
                    "player": oc.get("description") or oc.get("name"),
                    "price": oc.get("price"),
                })
    return out
