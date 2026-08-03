"""Match briefings: a short written read on a fixture, generated from computed numbers only.

THE RULE THIS MODULE EXISTS TO ENFORCE: the model never produces a number. It is handed a
fact pack — every figure already computed by the engine — and may only narrate what is in it.
A fluent invented stat ("Arsenal attack 41% down the left") would be indistinguishable from a
real one to a reader, and would destroy the credibility of a product whose whole position is
that it tells you what it does and does not know.

So generation is bracketed by two mechanical checks:

  1. `verify` regexes every number out of the generated prose and requires each one to match a
     value in the fact pack, at the precision it was written to. A number that isn't in the
     pack fails the briefing, no matter how plausible it reads.
  2. `render_template` produces a deterministic briefing from the same pack. If the model is
     unavailable, errors, or fails the guard twice, the page still gets a correct briefing —
     it just gets a duller one. There is no path where a bad number reaches a reader.

Generation happens at PRECOMPUTE time (~10 fixtures a gameweek), never per request: no user
waits on it, no key reaches the browser, and the cost is a few cents a week.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

MODEL = "claude-opus-5"
MAX_ATTEMPTS = 2

# Numbers as a reader would write them: 83, 83%, 2.7, -0.3, 1,200
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?%?")

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One clause, at most 80 characters, naming the single most useful thing about this fixture for an FPL manager.",
        },
        "angles": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "One or two sentences. Every number must come verbatim from the fact pack.",
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "The fact-pack keys this sentence relies on.",
                    },
                },
                "required": ["text", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "angles"],
    "additionalProperties": False,
}

SYSTEM = """You write one-paragraph briefings on Premier League fixtures for a Fantasy Premier League tool.

You are given a FACT PACK: a JSON object of figures produced by a statistical match model. It is
the ONLY source you may use.

Absolute rules:
1. NEVER state a number that is not in the fact pack. Do not calculate, convert, combine, round
   differently, or estimate. If you want to express something the pack does not contain, describe
   it in words with no number at all.
2. NEVER assert anything the pack does not support — no injuries, transfers, tactics, formations
   beyond the one given, historical results, form, or manager quotes. You have no knowledge of
   this season beyond the pack.
3. Percentages in the pack are already whole numbers. Write them exactly as given.
4. Every angle must cite the fact-pack keys it used in `evidence`.
5. Write plainly for a reader deciding who to pick. No hype, no predictions stated as certainty.
   These are model probabilities and should read like it.

If the pack is thin, write less. A short, correct briefing is the goal; padding it with
unsupported claims is the one unacceptable outcome."""


# --- the fact pack ------------------------------------------------------------------- #
def _pct(p: float | None) -> int | None:
    return None if p is None else round(p * 100)


def fact_pack(match: dict, assets: list[dict] | None = None, top_assets: int = 5) -> dict:
    """Every figure the briefing may use, display-ready.

    Probabilities are pre-converted to whole percentages so the model never has to do
    arithmetic — the single largest source of plausible-but-wrong numbers.
    """
    top = match.get("scorelines") or []
    lineups = match.get("lineups") or {}
    pack: dict[str, Any] = {
        "gameweek": match["gw"],
        "home_team": match["home"],
        "away_team": match["away"],
        "source": match["source"],
        "home_win_pct": _pct(match["result"]["home_win"]),
        "draw_pct": _pct(match["result"]["draw"]),
        "away_win_pct": _pct(match["result"]["away_win"]),
        "home_expected_goals": match["lam_home"],
        "away_expected_goals": match["lam_away"],
        "both_teams_to_score_pct": _pct(match["btts"]),
        "over_2_5_goals_pct": _pct(match["over_2_5"]),
        "home_clean_sheet_pct": _pct(match["clean_sheet"]["home"]),
        "away_clean_sheet_pct": _pct(match["clean_sheet"]["away"]),
        "most_likely_score": f"{match['most_likely_score'][0]}-{match['most_likely_score'][1]}",
        "most_likely_score_pct": _pct(top[0]["p"]) if top else None,
    }
    for side in ("home", "away"):
        xi = lineups.get(side)
        if xi:
            pack[f"{side}_projected_formation"] = xi["formation"]
    if assets:
        pack["top_players_by_expected_points"] = [
            {
                "name": a["web_name"],
                "team": a["team"],
                "position": a["position"],
                "expected_points": a["xp"],
                "price": a["price"],
                "owned_by_pct": round(a["ownership"]),
            }
            for a in assets[:top_assets]
        ]
    return {k: v for k, v in pack.items() if v is not None}


# --- the numeric guard --------------------------------------------------------------- #
def _walk_numbers(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        return
    if isinstance(obj, str):
        # numbers inside pack strings are grounded too ("2-0", "4-5-1")
        for tok in _NUMBER.findall(obj):
            try:
                out.add(float(tok.rstrip("%").replace(",", "")))
            except ValueError:
                continue
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, out)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_numbers(v, out)


def allowed_numbers(pack: dict) -> set[float]:
    """Every numeric value the briefing is permitted to contain."""
    out: set[float] = set()
    _walk_numbers(pack, out)
    return out


def unsupported_numbers(text: str, pack: dict) -> list[str]:
    """Numbers in `text` that no fact-pack value can account for.

    Tolerance follows the precision the number was written to: "83" matches anything rounding
    to 83, "2.7" only something within 0.05. That accepts honest rounding while still catching
    a fabricated figure.
    """
    allowed = allowed_numbers(pack)
    bad: list[str] = []
    for tok in _NUMBER.findall(text):
        raw = tok.rstrip("%").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        tol = 0.5 if decimals == 0 else 0.5 * (10 ** -decimals)
        if not any(abs(val - a) <= tol for a in allowed):
            bad.append(tok)
    return bad


def verify(brief: dict, pack: dict) -> list[str]:
    """Return the reasons a briefing is unusable; empty means it passed.

    Each angle is checked against ONLY the facts it cites, not the whole pack. That closes the
    gap a pack-wide check leaves open: a fixture where the clean-sheet chance happens to be 41%
    would otherwise let "they attack 41% down the left" through, because 41 exists *somewhere*.
    Scoping to the cited keys means a sentence can only use the numbers it claims to be about.

    The residual limit, stated rather than hidden: this proves a number is grounded, not that
    the sentence around it is a fair reading of that number. Nothing mechanical can check that.
    """
    problems: list[str] = []
    if not brief.get("angles"):
        problems.append("no angles produced")

    # The headline summarises the fixture and cites nothing, so it is checked pack-wide.
    bad = unsupported_numbers(brief.get("headline", ""), pack)
    if bad:
        problems.append(f"headline uses numbers not in the fact pack: {', '.join(bad)}")

    for i, a in enumerate(brief.get("angles", [])):
        evidence = a.get("evidence", [])
        unknown = [k for k in evidence if k not in pack]
        if unknown:
            problems.append(f"angle {i + 1} cited unknown fact keys: {', '.join(unknown)}")
        cited = {k: pack[k] for k in evidence if k in pack}
        bad = unsupported_numbers(a.get("text", ""), cited)
        if bad:
            problems.append(
                f"angle {i + 1} uses numbers absent from the facts it cites "
                f"({', '.join(evidence) or 'none'}): {', '.join(bad)}"
            )
    return problems


# --- the deterministic fallback ------------------------------------------------------- #
def render_template(pack: dict) -> dict:
    """A correct briefing with no model involved — the floor the page never drops below."""
    home, away = pack["home_team"], pack["away_team"]
    favourite, fav_pct = (
        (home, pack["home_win_pct"]) if pack["home_win_pct"] >= pack["away_win_pct"]
        else (away, pack["away_win_pct"])
    )
    angles = [{
        "text": (
            f"The model makes {favourite} {fav_pct}% to win, with the draw at "
            f"{pack['draw_pct']}%. Most likely score {pack['most_likely_score']} "
            f"at {pack['most_likely_score_pct']}%."
        ),
        "evidence": ["home_win_pct", "away_win_pct", "draw_pct",
                     "most_likely_score", "most_likely_score_pct"],
    }, {
        "text": (
            f"Clean sheet chances are {pack['home_clean_sheet_pct']}% for {home} and "
            f"{pack['away_clean_sheet_pct']}% for {away}; both teams to score sits at "
            f"{pack['both_teams_to_score_pct']}%."
        ),
        "evidence": ["home_clean_sheet_pct", "away_clean_sheet_pct", "both_teams_to_score_pct"],
    }]
    best = (pack.get("top_players_by_expected_points") or [None])[0]
    if best:
        angles.append({
            "text": (
                f"{best['name']} is the highest-projected asset in the fixture at "
                f"{best['expected_points']} expected points."
            ),
            "evidence": ["top_players_by_expected_points"],
        })
    return {
        "headline": f"{home} {pack['home_win_pct']}% · draw {pack['draw_pct']}% · {away} {pack['away_win_pct']}%",
        "angles": angles,
        "generated_by": "template",
    }


# --- generation ----------------------------------------------------------------------- #
def _client():
    """The Anthropic client, or None when narration isn't available.

    Optional by design: no key, or no `anthropic` installed, simply means every briefing comes
    from the template. The precompute must never fail because of this layer.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic()


def narrate(pack: dict, client=None) -> dict:
    """A verified briefing for one fixture. Falls back to the template on any failure."""
    client = client or _client()
    if client is None:
        return render_template(pack)

    last: list[str] = []
    for attempt in range(MAX_ATTEMPTS):
        note = ""
        if last:
            note = (
                "\n\nYour previous attempt was rejected for: " + "; ".join(last) +
                "\nUse ONLY numbers that appear in the fact pack, written exactly as they appear."
            )
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM,
                output_config={
                    "format": {"type": "json_schema", "schema": BRIEF_SCHEMA},
                    "effort": "low",
                },
                messages=[{
                    "role": "user",
                    "content": f"FACT PACK:\n{json.dumps(pack, indent=2)}{note}",
                }],
            )
            text = next(b.text for b in resp.content if b.type == "text")
            brief = json.loads(text)
        except Exception:  # noqa: BLE001 — any API/parse failure falls through to the template
            break

        last = verify(brief, pack)
        if not last:
            brief["generated_by"] = MODEL
            brief["attempts"] = attempt + 1
            return brief

    out = render_template(pack)
    if last:
        # keep why the model's copy was refused — this is the audit trail for the guard
        out["rejected"] = last
    return out


def brief_matches(matches: list[dict], assets_by_match: dict[str, list[dict]] | None = None,
                  client=None) -> int:
    """Attach a `brief` to every match in the CURRENT gameweek. Returns how many were written.

    Only the current gameweek: a written read on a fixture eight weeks out would be narrating
    a projection nobody should act on yet, at ten times the cost.
    """
    if not matches:
        return 0
    client = client or _client()
    gw = min(m["gw"] for m in matches)
    n = 0
    for m in matches:
        if m["gw"] != gw:
            continue
        pack = fact_pack(m, (assets_by_match or {}).get(m["match_id"]))
        m["brief"] = narrate(pack, client=client)
        m["brief"]["fact_pack"] = pack   # shown beside the prose: every number, checkable
        n += 1
    return n
