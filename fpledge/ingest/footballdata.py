"""Historical EPL results + closing odds from Football-Data.co.uk.

Direct CSV download (no scraping fragility) — the reliable source for the match-engine
backtest AND the honest betting benchmark, because it ships **closing** 1X2 odds
(Pinnacle 'PSC*', market-average 'AvgC*'). Closing-line value is the true test of a
betting model; final-scoreline accuracy is not.

Season codes are Football-Data's 4-digit form: '2425' == 2024/25.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from .. import config
from . import landing
from .httpget import get_with_retries

FD_BASE = "https://www.football-data.co.uk/mmz4281"
FD_FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"  # upcoming, with pre-match odds

# Preference order for 1X2 odds: Pinnacle-closing, market-avg-closing, Bet365-closing, then
# pre-match (market-avg / Pinnacle / Bet365) — the last three cover the upcoming fixtures file.
_ODDS_TRIPLES = [
    ("PSCH", "PSCD", "PSCA"),
    ("AvgCH", "AvgCD", "AvgCA"),
    ("B365CH", "B365CD", "B365CA"),
    ("AvgH", "AvgD", "AvgA"),
    ("PSH", "PSD", "PSA"),
    ("B365H", "B365D", "B365A"),
]

# Over/Under 2.5 goals, same closing-first-then-pre-match preference.
_OU_PAIRS = [
    ("PC>2.5", "PC<2.5"),
    ("AvgC>2.5", "AvgC<2.5"),
    ("B365C>2.5", "B365C<2.5"),
    ("Avg>2.5", "Avg<2.5"),
    ("P>2.5", "P<2.5"),
    ("B365>2.5", "B365<2.5"),
]


def _ou_odds(row: dict):
    for over, under in _OU_PAIRS:
        try:
            return float(row[over]), float(row[under])
        except (KeyError, ValueError, TypeError):
            continue
    return None, None


def _parse_date(s: str):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _closing_odds(row: dict):
    for h, d, a in _ODDS_TRIPLES:
        try:
            return float(row[h]), float(row[d]), float(row[a])
        except (KeyError, ValueError, TypeError):
            continue
    return None, None, None


def _decode(resp) -> str:
    """Decode a Football-Data CSV response, byte-order mark and all.

    These files begin with a UTF-8 BOM and are served as `text/csv` with NO charset, so
    `requests` falls back to ISO-8859-1 (the HTTP default for `text/*`) and `resp.text` hands
    back the BOM as the mojibake `\xef\xbb\xbf` glued to the first header field. `csv.DictReader`
    then names that column `\xef\xbb\xbfDiv` and every `row["Div"]` lookup misses.

    Only the FIRST column is affected, which is why this went unseen for four months:
    `parse_csv` reads HomeTeam/FTHG and never touches it, while `fetch_upcoming` filters on
    `Div` — so the historical fit was fine and the market-lambda path was dead. `utf-8-sig`
    decodes correctly AND strips the mark, which is the whole fix.
    """
    try:
        return resp.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Some older season files carry stray Windows-1252 bytes. Losing a season to one bad
        # character is worse than replacing it; the BOM still goes.
        return resp.content.decode("cp1252", errors="replace").lstrip("\ufeff")


def season_label(code: str) -> str:
    """'2425' -> '2024-25'."""
    return f"20{code[:2]}-{code[2:]}"


def download_season(code: str, division: str = "E0") -> str:
    """Download one season's CSV text and land it immutably; return the text."""
    import requests

    url = f"{FD_BASE}/{code}/{division}.csv"
    resp = get_with_retries(requests.Session(), url, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    text = _decode(resp)
    landing.land(text, source="football_data", endpoint=division, season=code)
    return text


def cached_season(code: str, division: str = "E0"):
    """The newest LANDED CSV for a season, as (text, ingest_ts) — or None if never landed.

    `download_season` lands every fetch, so after any successful run the raw zone holds a
    usable copy of each season. This is the read side of that bargain: when football-data.co.uk
    is down, the fit falls back to results as of the last successful fetch instead of the
    precompute publishing nothing. A 2026-09-06 outage proved the need — three 503s, zero
    training matches, no artifact, while yesterday's CSVs sat landed and unread.
    """
    parts = landing.list_partitions("football_data", division, season=code)
    if not parts:
        return None
    loc = parts[-1]
    as_of = loc.split("ingest_ts=")[-1].split("/")[0]
    return landing.read_json(loc), as_of


def parse_csv(text: str, label: str) -> list[dict]:
    """Parse Football-Data CSV text into match dicts."""
    matches: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("HomeTeam") or not row.get("FTHG"):
            continue
        d = _parse_date(row.get("Date", ""))
        if d is None:
            continue
        try:
            hg, ag = int(row["FTHG"]), int(row["FTAG"])
        except (ValueError, KeyError):
            continue
        ch, cd, ca = _closing_odds(row)
        oo, uu = _ou_odds(row)
        matches.append(
            {
                "season": label,
                "date": d.isoformat(),
                "date_ord": d.toordinal(),
                "home": row["HomeTeam"].strip(),
                "away": row["AwayTeam"].strip(),
                "home_goals": hg,
                "away_goals": ag,
                "close_h": ch,
                "close_d": cd,
                "close_a": ca,
                # Closing over/under 2.5. `fetch_upcoming` has always carried these for the
                # live market-lambda path; parse_csv did not, which is why the market-lambda
                # option in `eval.fpl_backtest.validate_xp(fixture_lambdas=)` shipped to
                # production without ever being scored against the engine's own lambdas.
                # `market_lambdas` needs 1X2 AND O/U to separate total goals from supremacy.
                "close_over25": oo,
                "close_under25": uu,
            }
        )
    return matches


def fetch_upcoming(division: str = "E0") -> list[dict]:
    """Upcoming fixtures with pre-match 1X2 + O/U 2.5 odds (football-data's fixtures.csv).

    Returns [] out of season / before books post lines (the file only holds the next ~week).
    Each match: {home, away, o_h, o_d, o_a, o_over, o_under}. Used to derive market-implied
    lambdas for the near gameweek(s); the engine is the fallback for fixtures without odds.
    """
    import requests

    resp = get_with_retries(requests.Session(), FD_FIXTURES_URL, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    text = _decode(resp)
    landing.land(text, source="football_data", endpoint="fixtures", season=config.SEASON)
    rows = list(csv.DictReader(io.StringIO(text)))
    n_in_division = 0
    out: list[dict] = []
    for row in rows:
        if row.get("Div") != division or not row.get("HomeTeam"):
            continue
        n_in_division += 1
        oh, od, oa = _closing_odds(row)   # falls through to pre-match Avg/PS/B365 for upcoming
        oo, uu = _ou_odds(row)
        if None in (oh, od, oa, oo, uu):
            continue
        out.append({
            "home": row["HomeTeam"].strip(), "away": row["AwayTeam"].strip(),
            "o_h": oh, "o_d": od, "o_a": oa, "o_over": oo, "o_under": uu,
        })

    # THE GUARD THIS FUNCTION EXISTS TO CARRY. Returning [] is legitimate — out of season,
    # or before the books post. Parsing a file that HAS fixtures and finding none in our own
    # division is not: this file is pan-European and always carries E0 in season. The two
    # states were indistinguishable, and that is exactly how a BOM-renamed `Div` column went
    # unnoticed for four months while every precompute silently used the engine where a
    # betting line was sitting in the file. A blind parse must not look like a quiet week.
    if rows and n_in_division == 0:
        raise ValueError(
            f"fixtures.csv parsed {len(rows)} rows but none in division {division!r} — "
            f"first columns seen: {list(rows[0])[:4]}. That is a parse failure, not an "
            "empty fixture list."
        )
    return out


def load_seasons_report(codes: list[str], division: str = "E0") -> tuple[list[dict], dict]:
    """Download + parse several seasons. Returns (matches, report).

    THE REPORT IS THE POINT. A dropped season used to print `warn:` and vanish — the caller got
    a shorter list with no way to tell it was short, the engine fitted on less history, and
    `fallback_fixtures` crept up while the run still exited 0. That is the single failure mode
    most likely to rot a scheduled deployment, because every symptom is a number getting quietly
    worse rather than anything breaking.

    Callers that cannot tolerate a partial fit should check `report["failed"]` and stop.

    A season whose LIVE fetch fails is not immediately a failure: every successful fetch is
    landed, so the newest landed copy stands in — loudly, under `report["stale"]` with the
    timestamp of the data actually used — and only a season with no landed history at all
    reaches `failed`. The distinction is deliberate: a third-party outage costs freshness
    (results since the last fetch are missing from the fit, the same lag football-data's own
    publishing cadence already imposes routinely), while refusing to publish over it costs
    the site a whole day — which is what happened before the fallback existed.
    """
    out: list[dict] = []
    per_season, failed, stale = {}, [], []
    for code in codes:
        label = season_label(code)
        try:
            text = download_season(code, division)
        except Exception as e:  # noqa: BLE001
            cached = cached_season(code, division)
            if cached is None:
                print(f"  warn: could not fetch season {code}: {e}")
                failed.append({"code": code, "season": label, "error": str(e)})
                continue
            text, as_of = cached
            print(f"  warn: live fetch of season {code} failed ({e}); using the copy landed "
                  f"{as_of} — results since then are missing from this fit")
            stale.append({"code": code, "season": label, "as_of": as_of, "error": str(e)})
        got = parse_csv(text, label)
        print(f"  {label}: {len(got)} matches")
        per_season[label] = len(got)
        out.extend(got)
    return out, {
        "requested": list(codes),
        "loaded": sorted(per_season),
        "failed": failed,
        "stale": stale,
        "matches_per_season": per_season,
        "n_matches": len(out),
    }


def load_seasons(codes: list[str], division: str = "E0") -> list[dict]:
    """Download + parse several seasons, resiliently (skip any that fail).

    Kept for callers that genuinely do not care. Anything scheduled should use
    `load_seasons_report` and inspect `failed` — see its docstring.
    """
    return load_seasons_report(codes, division)[0]
