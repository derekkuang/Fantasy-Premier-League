"""Projected XI from the minutes model.

The point of these tests is that the XI is *legal* and *derived from minutes* — those are the
two claims the feature makes. A lineup that quietly fields two keepers, or that ignores the
minutes ranking, would still look plausible in the UI.
"""

from __future__ import annotations

from fpledge.lineup import FORMATIONS, projected_xi


def _p(eid, pos, mins, team=1, **over):
    r = {
        "element_id": eid, "web_name": f"P{eid}", "position": pos, "team_id": team,
        "x_minutes": mins, "xp": mins / 30.0, "price": 5.0,
        "availability": {"status": "a", "chance": None},
        "set_pieces": {"penalties": None},
    }
    r.update(over)
    return r


def _squad(team=1):
    """A full, unambiguous squad: minutes descend within each position."""
    out = [_p(1, "GK", 90, team), _p(2, "GK", 10, team)]
    eid = 10
    for pos, n in (("DEF", 7), ("MID", 8), ("FWD", 5)):
        for i in range(n):
            out.append(_p(eid, pos, 90 - i * 10, team))
            eid += 1
    return out


def test_returns_a_legal_eleven():
    xi = projected_xi(_squad(), team_id=1)
    assert len(xi["xi"]) == 11
    counts = {p: sum(1 for r in xi["xi"] if r["position"] == p) for p in ("GK", "DEF", "MID", "FWD")}
    assert counts["GK"] == 1
    assert (counts["DEF"], counts["MID"], counts["FWD"]) in FORMATIONS
    assert xi["formation"] == f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}"


def test_picks_the_highest_minutes_players_within_each_position():
    xi = projected_xi(_squad(), team_id=1)
    for pos in ("DEF", "MID", "FWD"):
        picked = [r["x_minutes"] for r in xi["xi"] if r["position"] == pos]
        assert picked == sorted(picked, reverse=True)
        bench_same_pos = [r["x_minutes"] for r in xi["bench"] if r["position"] == pos]
        if picked and bench_same_pos:
            assert min(picked) >= max(bench_same_pos)


def test_zero_minute_players_are_never_selected():
    """Availability is applied upstream, so an injured player arrives here at 0 minutes and
    must fall out on his own — this is the guard that the flag actually reaches the lineup.
    The first-choice forward is injured, so the XI must fall through to the next one."""
    squad = _squad()
    top_fwd = max((r for r in squad if r["position"] == "FWD"), key=lambda r: r["x_minutes"])
    top_fwd["x_minutes"] = 0.0
    xi = projected_xi(squad, team_id=1)
    picked = {r["element_id"] for r in xi["xi"] + xi["bench"]}
    assert top_fwd["element_id"] not in picked
    assert any(r["position"] == "FWD" for r in xi["xi"])   # a fit forward took the shirt


def test_no_legal_shape_returns_none_rather_than_an_illegal_side():
    """If a whole position is wiped out, every formation becomes unfillable. Returning None is
    the honest answer — fielding ten men, or silently inventing a 4-6-0, would be worse."""
    squad = [r for r in _squad() if r["position"] != "FWD"]
    assert projected_xi(squad, team_id=1) is None


def test_formation_maximises_expected_minutes():
    """Give the midfield far more minutes than the attack and the shape must shift toward it,
    rather than defaulting to a fixed formation."""
    squad = _squad()
    for r in squad:
        if r["position"] == "MID":
            r["x_minutes"] = 90.0
        if r["position"] == "FWD":
            r["x_minutes"] = 15.0
    xi = projected_xi(squad, team_id=1)
    n_mid = sum(1 for r in xi["xi"] if r["position"] == "MID")
    n_fwd = sum(1 for r in xi["xi"] if r["position"] == "FWD")
    assert n_mid == 5 and n_fwd == 1


def test_other_teams_players_are_ignored():
    mixed = _squad(team=1) + _squad(team=2)
    xi = projected_xi(mixed, team_id=1)
    ids = {r["element_id"] for r in xi["xi"]}
    assert len(xi["xi"]) == 11 and ids.issubset({r["element_id"] for r in mixed})


def test_returns_none_when_no_legal_eleven_exists():
    """A promoted or low-data club can have too few scored players to field a side. Returning
    None is the honest answer — inventing a short XI would be worse."""
    assert projected_xi([_p(1, "GK", 90), _p(2, "DEF", 90)], team_id=1) is None
    assert projected_xi([], team_id=1) is None


def test_returns_none_without_a_goalkeeper():
    squad = [r for r in _squad() if r["position"] != "GK"]
    assert projected_xi(squad, team_id=1) is None


def test_confidence_reflects_how_nailed_the_side_is():
    nailed = _squad()
    for r in nailed:
        r["x_minutes"] = 90.0
    assert projected_xi(nailed, team_id=1)["confidence"] == 1.0

    rotated = _squad()
    for r in rotated:
        r["x_minutes"] = 45.0
    assert projected_xi(rotated, team_id=1)["confidence"] == 0.5


def test_rows_carry_the_context_the_ui_needs():
    squad = _squad()
    squad[2]["set_pieces"] = {"penalties": 1}
    squad[2]["availability"] = {"status": "d", "chance": 75}
    xi = projected_xi(squad, team_id=1)
    row = next(r for r in xi["xi"] + xi["bench"] if r["element_id"] == squad[2]["element_id"])
    assert row["penalties"] == 1
    assert row["status"] == "d" and row["chance"] == 75
