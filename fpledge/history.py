"""Each player's season so far: what we published before every deadline, and what he scored.

The player sheet shows this side by side. The rule that makes it worth showing: a projection
here is the one users actually saw, read from that gameweek's stored artifact, and never
recalculated with today's model. Recalculating would make the past look better than it was.

A gameweek appears once FPL has finalised it (its event-live is landed). Its projection counts
only when the stored artifact was published in that gameweek's own window, after the previous
deadline and before its own. Anything else (no artifact, a later rerun, last season's file still
sitting under the same name) is shown as "not projected", never as a zero. So is a player who
was not in that week's artifact.

The opponent comes from what actually happened (FPL's fixture for that week), not from the
artifact: until 14 November 2026 the artifact's player list was July's, so 30 players were
projected for a club they had left. When that happened, `as_club` names the club we projected
him for, so the sheet can say so instead of showing a wrong fixture as if it were right.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

# Gameweek 1 has no previous deadline to bound it, so its artifact must be at most this old.
_FIRST_WINDOW = timedelta(days=120)


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def published_in_window(artifact: Mapping, gw: int, deadlines: Mapping[int, str]) -> bool:
    """True when the artifact for `gw` was written after the previous deadline and before its own."""
    run = _ts((artifact.get("meta") or {}).get("run_ts"))
    due = _ts(deadlines.get(gw))
    if run is None or due is None or run >= due:
        return False
    before = _ts(deadlines.get(gw - 1))
    return run > before if before is not None else run > due - _FIRST_WINDOW


def player_history(published: Mapping[int, Mapping], live_by_gw: Mapping[int, Mapping],
                   deadlines: Mapping[int, str], fixture_teams: Mapping[int, tuple[int, int]],
                   club_of: Mapping[int, int], team_names: Mapping[int, str]) -> dict[int, list[dict]]:
    """{element_id: [{"gw", "xp", "pts", "mins", "vs", "as_club"}, ...]}, oldest gameweek first.

    `published` maps a gameweek to its stored serving artifact, `live_by_gw` to FPL's finalised
    event-live, and `deadlines` to FPL's deadline_time. `fixture_teams` is {fixture_id: (home,
    away)}, `club_of` each element's club today, `team_names` {team_id: name}.

    `xp` is None when we did not project the player that week. `vs` lists the opponents he
    actually faced ([] in a blank week, or when his club that week can't be told: he has moved
    since, and is on neither side). `as_club` is None unless we projected him for another club.
    """
    out: dict[int, list[dict]] = {}
    for gw in sorted(live_by_gw):
        artifact = published.get(gw)
        ours: dict = {}
        if artifact is not None and published_in_window(artifact, gw, deadlines):
            ours = {r["element_id"]: r for r in artifact.get("records", [])}
        for el in live_by_gw[gw].get("elements", []):
            stats = el.get("stats") or {}
            club = club_of.get(el["id"])
            vs = []
            for item in el.get("explain") or []:
                home, away = fixture_teams.get(item.get("fixture"), (None, None))
                if club is not None and club == home:
                    vs.append({"opp": team_names.get(away, ""), "home": True})
                elif club is not None and club == away:
                    vs.append({"opp": team_names.get(home, ""), "home": False})
            rec = ours.get(el["id"])
            projected_for = rec.get("team_id") if rec is not None else None
            out.setdefault(el["id"], []).append({
                "gw": gw,
                "xp": round(float(rec["xp"]), 2) if rec is not None else None,
                "pts": int(stats.get("total_points") or 0),
                "mins": int(stats.get("minutes") or 0),
                "vs": vs,
                "as_club": (team_names.get(projected_for)
                            if vs and projected_for is not None and projected_for != club else None),
            })
    return out


# --- the site's own record, week by week (the model page) ------------------------------------ #
MIN_FPL_SHARE = 0.8   # FPL's forecast must cover this share of the scored players to be compared


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1     # ties share their average rank
        i = j + 1
    return out


def spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation without numpy, so the precompute's import path stays light."""
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    return cov / (va * vb) ** 0.5 if va and vb else None


def _score(pred: list[float], actual: list[int]) -> dict:
    rho = spearman(pred, actual)
    mae = sum(abs(p - a) for p, a in zip(pred, actual, strict=True)) / len(pred)
    return {"rho": None if rho is None else round(rho, 4), "mae": round(mae, 3)}


def live_record(published: Mapping[int, Mapping], live_by_gw: Mapping[int, Mapping],
                deadlines: Mapping[int, str], fpl_forecasts: Mapping | None = None) -> dict:
    """How what we published ranked the players who then played, gameweek by gameweek.

    Scored on players we projected who got minutes, the same rule as every accuracy figure on
    the site. Where this site captured FPL's own forecast before the deadline for at least
    MIN_FPL_SHARE of those players, both are scored on exactly the players FPL covered;
    otherwise FPL is None and ours stands alone. A gameweek with no artifact published inside
    its own window is left out, never estimated.
    """
    fpl_forecasts = fpl_forecasts or {}
    weeks = []
    for gw in sorted(live_by_gw):
        artifact = published.get(gw)
        if artifact is None or not published_in_window(artifact, gw, deadlines):
            continue
        ours = {r["element_id"]: float(r["xp"]) for r in artifact.get("records", [])}
        played = [(el["id"], int(el["stats"].get("total_points") or 0))
                  for el in live_by_gw[gw].get("elements", [])
                  if el["id"] in ours and int((el.get("stats") or {}).get("minutes") or 0) > 0]
        if len(played) < 10:
            continue
        covered = [(i, pts) for i, pts in played if (gw, i) in fpl_forecasts]
        if len(covered) >= MIN_FPL_SHARE * len(played):
            rows = covered
            fpl = _score([float(fpl_forecasts[(gw, i)]) for i, _ in rows], [p for _, p in rows])
        else:
            rows, fpl = played, None
        weeks.append({"gw": gw, "n": len(rows),
                      "ours": _score([ours[i] for i, _ in rows], [p for _, p in rows]),
                      "fpl": fpl})
    both = [w for w in weeks if w["fpl"] and w["fpl"]["rho"] is not None and w["ours"]["rho"] is not None]
    summary = None
    if both:
        summary = {
            "gws_compared": len(both),
            "ours_rho": round(sum(w["ours"]["rho"] for w in both) / len(both), 4),
            "fpl_rho": round(sum(w["fpl"]["rho"] for w in both) / len(both), 4),
            "ours_ahead": sum(w["ours"]["rho"] > w["fpl"]["rho"] for w in both),
        }
    return {"gws": weeks, "summary": summary}
