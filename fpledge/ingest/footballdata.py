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


def season_label(code: str) -> str:
    """'2425' -> '2024-25'."""
    return f"20{code[:2]}-{code[2:]}"


def download_season(code: str, division: str = "E0") -> str:
    """Download one season's CSV text and land it immutably; return the text."""
    import requests  # noqa: PLC0415

    url = f"{FD_BASE}/{code}/{division}.csv"
    resp = requests.get(url, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    landing.land(resp.text, source="football_data", endpoint=division, season=code)
    return resp.text


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
            }
        )
    return matches


def fetch_upcoming(division: str = "E0") -> list[dict]:
    """Upcoming fixtures with pre-match 1X2 + O/U 2.5 odds (football-data's fixtures.csv).

    Returns [] out of season / before books post lines (the file only holds the next ~week).
    Each match: {home, away, o_h, o_d, o_a, o_over, o_under}. Used to derive market-implied
    lambdas for the near gameweek(s); the engine is the fallback for fixtures without odds.
    """
    import requests  # noqa: PLC0415

    resp = requests.get(FD_FIXTURES_URL, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    landing.land(resp.text, source="football_data", endpoint="fixtures", season=config.SEASON)
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(resp.text)):
        if row.get("Div") != division or not row.get("HomeTeam"):
            continue
        oh, od, oa = _closing_odds(row)   # falls through to pre-match Avg/PS/B365 for upcoming
        oo, uu = _ou_odds(row)
        if None in (oh, od, oa, oo, uu):
            continue
        out.append({
            "home": row["HomeTeam"].strip(), "away": row["AwayTeam"].strip(),
            "o_h": oh, "o_d": od, "o_a": oa, "o_over": oo, "o_under": uu,
        })
    return out


def load_seasons(codes: list[str], division: str = "E0") -> list[dict]:
    """Download + parse several seasons, resiliently (skip any that fail)."""
    out: list[dict] = []
    for code in codes:
        try:
            text = download_season(code, division)
        except Exception as e:  # noqa: BLE001
            print(f"  warn: could not fetch season {code}: {e}")
            continue
        got = parse_csv(text, season_label(code))
        print(f"  {season_label(code)}: {len(got)} matches")
        out.extend(got)
    return out
