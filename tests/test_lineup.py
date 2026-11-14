"""Projected XI from the minutes model.

The point of these tests is that the XI is *legal* and *derived from minutes* — those are the
two claims the feature makes. A lineup that quietly fields two keepers, or that ignores the
minutes ranking, would still look plausible in the UI.
"""

from __future__ import annotations

from fpledge.lineup import FORMATIONS, projected_xi, recent_starts


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


# --- the club's own shape, and each player's recent starts (Nov 2026) ----------------------- #
def test_the_xi_takes_the_clubs_usual_shape_not_the_most_minutes():
    """Arsenal came out 5-4-1 because five defenders each averaged 55+ minutes."""
    squad = [_p(1, "GK", 90)]
    squad += [_p(10 + i, "DEF", m) for i, m in enumerate((90, 90, 71, 69, 56, 31))]
    squad += [_p(20 + i, "MID", m) for i, m in enumerate((88, 80, 76, 58, 43, 27))]
    squad += [_p(30 + i, "FWD", m) for i, m in enumerate((62, 28))]
    assert projected_xi(squad, team_id=1)["formation"] == "5-4-1"          # the old way
    xi = projected_xi(squad, team_id=1, shape=(4, 5, 1))
    assert xi["formation"] == "4-5-1" and xi["basis"] == "recent"
    assert {r["element_id"] for r in xi["xi"]} >= {24, 13} and 14 not in {r["element_id"] for r in xi["xi"]}


def test_a_shape_with_no_forward_is_kept():
    xi = projected_xi(_squad(), team_id=1, shape=(4, 6, 0))
    assert xi["formation"] == "4-6-0"
    assert not [r for r in xi["xi"] if r["position"] == "FWD"]


def test_too_few_fit_players_for_the_usual_shape_falls_back_to_minutes():
    squad = [_p(1, "GK", 90)] + [_p(10 + i, "DEF", 90) for i in range(3)]
    squad += [_p(20 + i, "MID", 80) for i in range(5)] + [_p(30 + i, "FWD", 70) for i in range(3)]
    xi = projected_xi(squad, team_id=1, shape=(4, 5, 1))
    assert xi["basis"] == "minutes" and xi["formation"] in {f"{d}-{m}-{f}" for d, m, f in FORMATIONS}


def _live(starters_by_gw):
    return {g: {"elements": [{"id": e, "stats": {"starts": 1, "minutes": 90}} for e in ids]}
            for g, ids in starters_by_gw.items()}


def test_recent_starts_reads_the_usual_shape_and_each_players_starts():
    # team 1: keeper 1, defenders 10-14, midfielders 20-25, forwards 30-31
    elements = ([{"id": 1, "team": 1, "element_type": 1}]
                + [{"id": e, "team": 1, "element_type": 2} for e in range(10, 15)]
                + [{"id": e, "team": 1, "element_type": 3} for e in range(20, 26)]
                + [{"id": e, "team": 1, "element_type": 4} for e in (30, 31)])
    four_five_one = [1, 10, 11, 12, 13, 20, 21, 22, 23, 24, 30]
    five_four_one = [1, 10, 11, 12, 13, 14, 20, 21, 22, 23, 31]
    live = _live({1: four_five_one, 2: five_four_one, 3: four_five_one, 4: five_four_one, 5: four_five_one,
                  6: five_four_one, 7: [1]})   # gw7: a double, ignored
    fixtures = [(g, 1, 2) for g in range(1, 8)] + [(7, 3, 1)]
    shapes, starts = recent_starts(elements, live, fixtures)
    # last five single-fixture weeks are 2-6: 5-4-1 three times, 4-5-1 twice
    assert shapes[1] == (5, 4, 1)
    assert starts[10] == (5, 5) and starts[24] == (2, 5) and starts[25] == (0, 5)


def test_recent_starts_breaks_a_tie_with_the_latest_shape():
    elements = ([{"id": 1, "team": 1, "element_type": 1}]
                + [{"id": e, "team": 1, "element_type": 2} for e in range(10, 15)]
                + [{"id": e, "team": 1, "element_type": 3} for e in range(20, 26)]
                + [{"id": 30, "team": 1, "element_type": 4}])
    a = [1, 10, 11, 12, 13, 20, 21, 22, 23, 24, 30]      # 4-5-1
    b = [1, 10, 11, 12, 13, 14, 20, 21, 22, 23, 24]      # 5-5-0
    shapes, _ = recent_starts(elements, _live({1: a, 2: b, 3: a, 4: b}), [(g, 1, 2) for g in range(1, 5)])
    assert shapes[1] == (5, 5, 0)


def test_rows_carry_recent_starts():
    xi = projected_xi(_squad(), team_id=1, starts={1: (5, 5)})
    keeper = xi["xi"][0]
    assert keeper["element_id"] == 1 and keeper["starts"] == [5, 5]
    assert all(r["starts"] is None for r in xi["xi"][1:])
