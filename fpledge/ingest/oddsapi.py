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

STATUS. The FIXTURE markets (h2h + totals, `upcoming_1x2_ou`) were verified live on 2026-09-09
— see that function for what the run established. The GOALSCORER path's original note said it
was unverified; the props capture has since been running on a schedule, so treat that claim as
stale rather than current, and confirm against a capture log before relying on it either way.
Two things any first live run must check, both handled rather than assumed: the exact market key
(`list_markets` asks the API instead of trusting the constant below), and the credit accounting
in the response headers.
"""

from __future__ import annotations

import os
import time

from .. import config
from . import landing
from .httpget import get_with_retries

BASE = "https://api.the-odds-api.com/v4"
SPORT = "soccer_epl"

# The market key as documented. `list_markets()` exists because a wrong key here would return an
# empty payload rather than an error, and a capture of nothing looks exactly like a quiet week.
GOALSCORER_MARKET = "player_goal_scorer_anytime"

# Match odds + total goals — the two lines `betting.market_lambda` inverts into a pair of
# expected goals. Unlike the goalscorer market these are documented, universally offered, and
# priced on the BULK endpoint, so the whole slate costs (markets x regions) = 2 credits rather
# than 2 per fixture.
H2H_TOTALS_MARKETS = "h2h,totals"
TOTALS_LINE = 2.5

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
        import requests

        if not self.api_key:
            raise NoApiKey(
                "No ODDS_API_KEY. Get a free key at https://the-odds-api.com (500 credits/month, "
                "which covers ~10 credits per gameweek for this capture many times over)."
            )
        try:
            # attempts=2, below the module default, and the throttle runs before EVERY
            # attempt: this endpoint is metered, so each retry of a priced call can be a
            # spent credit — one bounded second chance for an unrepeatable capture, never a
            # burst against a struggling book inside the politeness window.
            resp = get_with_retries(
                self.session, f"{BASE}/{path}",
                params={"apiKey": self.api_key, **params}, timeout=self._timeout,
                attempts=2, before_attempt=self._throttle,
            )
        except requests.RequestException as exc:
            # Wrapped so the capture's per-event loop, which catches OddsApiError, keeps its
            # partial-failure behaviour. A raw Timeout used to escape that catch and crash the
            # run AFTER credits were spent, landing nothing and writing no index row — the exact
            # "credits spent, no evidence" state the index exists to prevent.
            raise OddsApiError(f"{path}: {type(exc).__name__} — request never completed") from exc
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
        if resp.status_code >= 400:
            # Same reason as the wrap above: raise_for_status() would throw requests.HTTPError,
            # which is not OddsApiError, and a mid-loop 5xx would take the whole capture down.
            raise OddsApiError(f"HTTP {resp.status_code} from {path}")
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

    def sport_odds(
        self,
        markets: str = H2H_TOTALS_MARKETS,
        regions: str = DEFAULT_REGIONS,
        sport: str = SPORT,
        odds_format: str = "decimal",
    ) -> list:
        """Every upcoming fixture's prices for `markets`, in one call.

        Costs (markets x regions) credits for the WHOLE slate — 2 on the defaults — because
        this is the bulk `/odds` endpoint, not the per-event one `event_odds` uses. That is the
        difference between 2 credits a run and 20, and it is why the fixture-level markets can
        ride on the same free tier as the goalscorer capture.
        """
        return self._get(
            f"sports/{sport}/odds", markets=markets, regions=regions, oddsFormat=odds_format,
        )

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


# --- fixture-level prices, shaped like football-data's ------------------------------------ #
def _mean(vals: list) -> float | None:
    clean = [v for v in vals if isinstance(v, (int, float))]
    return sum(clean) / len(clean) if clean else None


def _row_from_event(ev: dict, line: float = TOTALS_LINE) -> dict | None:
    """One event's average 1X2 + O/U prices, or None if any leg is missing.

    Averaged ACROSS BOOKMAKERS on purpose: football-data's `Avg*` columns — the columns this
    project has always fed to `market_lambdas` — are exactly averaged decimal odds, so the two
    sources stay directly comparable and a fallback week does not quietly change what the
    lambdas mean. (Averaging decimal odds is not averaging probabilities; matching the
    incumbent's convention matters more here than the purer alternative.)

    A partial row is dropped rather than half-used: `market_lambdas` needs 1X2 AND totals to
    separate supremacy from total goals, and one without the other determines nothing.
    """
    home, away = ev.get("home_team"), ev.get("away_team")
    if not home or not away:
        return None
    h, d, a, over, under = [], [], [], [], []
    for book in ev.get("bookmakers") or []:
        for market in book.get("markets") or []:
            key = market.get("key")
            for oc in market.get("outcomes") or []:
                name, price = oc.get("name"), oc.get("price")
                if key == "h2h":
                    if name == home:
                        h.append(price)
                    elif name == away:
                        a.append(price)
                    elif name == "Draw":
                        d.append(price)
                elif key == "totals" and oc.get("point") == line:
                    if name == "Over":
                        over.append(price)
                    elif name == "Under":
                        under.append(price)
    o_h, o_d, o_a, o_o, o_u = _mean(h), _mean(d), _mean(a), _mean(over), _mean(under)
    if None in (o_h, o_d, o_a, o_o, o_u):
        return None
    return {
        "home": home, "away": away,
        "o_h": round(o_h, 3), "o_d": round(o_d, 3), "o_a": round(o_a, 3),
        "o_over": round(o_o, 3), "o_under": round(o_u, 3),
    }


def upcoming_1x2_ou(client=None, regions: str = DEFAULT_REGIONS, line: float = TOTALS_LINE):
    """Upcoming EPL fixtures with 1X2 + O/U prices, in `footballdata.fetch_upcoming`'s shape.

    A SECOND SOURCE, not a replacement. football-data is free and needs no key, so it leads —
    but it is one unauthenticated host, and a three-day 503 across 2026-09-06..09 left a
    validated input with nothing to read. Same output shape both ways, so nothing downstream
    knows or cares which one answered.

    Raises `NoApiKey` rather than returning [] when no key is configured: an empty list here
    would be indistinguishable from a quiet week, which is the failure this whole path just
    spent four months demonstrating.

    VERIFIED LIVE 2026-09-09, against 20 upcoming fixtures and 15-21 bookmakers each:
      * `h2h` outcome names match `home_team`/`away_team` exactly — 371/371 markets carried
        precisely {home, away, "Draw"}. This is what `_row_from_event` routes on, and a
        mismatch would drop every row while looking like a quiet week, so it was the one
        assumption worth paying to check.
      * every fixture offered a 2.5 totals line (20/20). Books also quote 3.5 — 38 of 180
        outcomes — which the `point == line` filter correctly ignores.
      * the whole slate cost 2 credits, as the bulk endpoint promises.
    """
    client = client or OddsApiClient()
    payload = client.sport_odds(markets=H2H_TOTALS_MARKETS, regions=regions)
    landing.land(payload, source="the_odds_api", endpoint="h2h_totals", season=config.SEASON)
    return [row for ev in payload or [] if (row := _row_from_event(ev, line))]
