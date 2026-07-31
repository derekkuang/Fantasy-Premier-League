"""Squad balance check — a structural health report for a 15-man FPL squad.

Beyond raw xP: where the budget sits, whether the bench can actually cover (auto-subs),
club-concentration risk, template-vs-differential profile, rotation/availability risk, and
how captain-dependent the team is. Works on any squad — the optimiser's output or a real
FPL team pulled from the API.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

TEMPLATE_EO = 40.0        # ownership% at/above which a pick is "template"
DIFFERENTIAL_EO = 10.0    # ownership% below which a pick is a "differential"
ROTATION_MINUTES = 60.0   # expected minutes below which a starter is a rotation risk
DEAD_BENCH_MINUTES = 20.0 # bench player below this won't provide auto-sub cover
BENCH_SPEND_WARN = 18.0   # £m on the bench beyond which too much budget isn't scoring


def check_balance(players: Sequence[dict], budget: float = 100.0) -> dict:
    """Analyse a squad. Each player dict needs: name, position, price, team, xp, ownership,
    x_minutes, starter (bool), captain (bool). Returns metrics + human-readable flags.
    """
    xi = [p for p in players if p["starter"]]
    bench = [p for p in players if not p["starter"]]
    captain = next((p for p in players if p.get("captain")), None)

    total_cost = round(sum(p["price"] for p in players), 1)
    xi_xp = sum(p["xp"] for p in xi)
    total_xp = xi_xp + (captain["xp"] if captain else 0.0)  # captain counted twice

    spend_by_pos = {
        pos: round(sum(p["price"] for p in players if p["position"] == pos), 1)
        for pos in ("GK", "DEF", "MID", "FWD")
    }
    bench_spend = round(sum(p["price"] for p in bench), 1)

    team_counts = Counter(p["team"] for p in players)
    top_two_clubs = sum(c for _, c in team_counts.most_common(2))

    xi_ownership = sum(p["ownership"] for p in xi) / len(xi) if xi else 0.0
    n_template = sum(1 for p in xi if p["ownership"] >= TEMPLATE_EO)
    n_differential = sum(1 for p in xi if p["ownership"] < DIFFERENTIAL_EO)

    n_rotation = sum(1 for p in xi if p["x_minutes"] < ROTATION_MINUTES)
    dead_bench = sum(1 for p in bench if p["x_minutes"] < DEAD_BENCH_MINUTES)

    top3 = sum(sorted((p["xp"] for p in xi), reverse=True)[:3])
    captain_dependence = top3 / xi_xp if xi_xp > 0 else 0.0

    flags: list[tuple[str, str]] = []
    if bench_spend > BENCH_SPEND_WARN:
        flags.append(("warn", f"£{bench_spend}m on the bench — a lot of budget not scoring"))
    if dead_bench >= 2:
        flags.append(("warn", f"{dead_bench} bench players unlikely to play — weak auto-sub cover"))
    if top_two_clubs >= 6:
        flags.append((
            "warn",
            f"{top_two_clubs}/{len(players)} players from just two clubs — concentration risk",
        ))
    if n_differential >= 5:
        flags.append(("warn", f"{n_differential} differentials in the XI — high variance"))
    if n_rotation >= 3:
        flags.append(("warn", f"{n_rotation} starters are rotation/minutes risks"))
    if n_template >= 9:
        flags.append(("info", f"very template XI ({n_template}/11 highly owned) — safe but low ceiling"))
    if captain_dependence > 0.5:
        flags.append(("info", f"{captain_dependence:.0%} of XI xP from your top 3 — captain-dependent"))
    if not any(level == "warn" for level, _ in flags):
        flags.append(("ok", "no structural warnings — squad looks balanced"))

    return {
        "n_players": len(players),
        "total_cost": total_cost,
        "budget_left": round(budget - total_cost, 1),
        "total_xp": round(total_xp, 1),
        "xi_xp": round(xi_xp, 1),
        "value_pts_per_m": round(xi_xp / total_cost, 3) if total_cost else 0.0,
        "spend_by_pos": spend_by_pos,
        "bench_spend": bench_spend,
        "max_from_club": max(team_counts.values()),
        "distinct_clubs": len(team_counts),
        "xi_avg_ownership": round(xi_ownership, 1),
        "n_template": n_template,
        "n_differential": n_differential,
        "n_rotation_risk": n_rotation,
        "dead_bench": dead_bench,
        "captain_dependence": round(captain_dependence, 2),
        "flags": flags,
    }


def format_report(r: dict) -> str:
    """Render a balance report as a compact text block."""
    icon = {"warn": "⚠", "info": "•", "ok": "✓"}
    lines = [
        "\n=== SQUAD BALANCE ===",
        f"  cost £{r['total_cost']}m (bank £{r['budget_left']}m)  |  XI xP {r['xi_xp']}  |  "
        f"value {r['value_pts_per_m']} pts/£m",
        f"  spend  GK {r['spend_by_pos']['GK']}  DEF {r['spend_by_pos']['DEF']}  "
        f"MID {r['spend_by_pos']['MID']}  FWD {r['spend_by_pos']['FWD']}  (bench £{r['bench_spend']}m)",
        f"  clubs  {r['distinct_clubs']} distinct, max {r['max_from_club']} from one  |  "
        f"XI ownership avg {r['xi_avg_ownership']}%  "
        f"({r['n_template']} template, {r['n_differential']} differential)",
        f"  risk   {r['n_rotation_risk']} rotation-risk starters, {r['dead_bench']} dead bench, "
        f"captain-dependence {r['captain_dependence']:.0%}",
        "  flags:",
    ]
    lines += [f"    {icon.get(level, '-')} {msg}" for level, msg in r["flags"]]
    return "\n".join(lines)
