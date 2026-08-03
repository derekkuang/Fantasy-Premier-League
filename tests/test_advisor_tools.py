"""The advisor's tool layer.

These need no API key and cost nothing: the tools are the whole trust boundary, so they are
worth testing far harder than the loop that calls them. The model can only be as correct as
its tools — if `simulate_transfers` says an illegal move is fine, the agent will confidently
recommend something the game rejects.
"""

from __future__ import annotations

import pytest

from fpledge.advisor.tools import MAX_SEARCH_RESULTS, TOOL_SCHEMAS, AdvisorTools


def _rec(eid, pos, team_id, team, price, xp, own=10.0, xmin=90.0, low_cov=False, **over):
    r = {
        "element_id": eid, "web_name": f"P{eid}", "position": pos, "team_id": team_id,
        "team_name": team, "price": price, "xp": xp, "ownership": own, "x_minutes": xmin,
        "low_cov": low_cov,
        "availability": {"status": "a", "label": "available", "chance": None},
        "set_pieces": {"penalties": None},
    }
    r.update(over)
    return r


def _records():
    """A legal 15 (2/5/5/3) across many clubs, plus buyable alternatives."""
    recs = [_rec(1, "GK", 1, "Alpha", 4.5, 3.0), _rec(2, "GK", 2, "Beta", 4.0, 2.5)]
    recs += [_rec(10 + i, "DEF", 3 + i, f"Club{i}", 5.0, 4.0 - i * 0.1) for i in range(5)]
    recs += [_rec(20 + i, "MID", 8 + i, f"Mid{i}", 7.0, 5.5 - i * 0.2) for i in range(5)]
    recs += [_rec(30 + i, "FWD", 13 + i, f"Fwd{i}", 8.0, 6.0 - i * 0.3) for i in range(3)]
    # buyable
    recs += [
        _rec(100, "MID", 18, "Rich", 9.0, 8.0, own=45.0),          # premium upgrade
        _rec(101, "MID", 19, "Cheap", 4.5, 3.0, own=2.0),          # budget enabler
        _rec(102, "DEF", 3, "Club0", 4.5, 3.8),                    # same club as DEF 10
        _rec(103, "FWD", 20, "Punt", 5.5, 4.5, own=1.5,
             set_pieces={"penalties": 1}),
        _rec(104, "MID", 21, "Hurt", 7.0, 0.0,
             availability={"status": "i", "label": "injured", "chance": 0}),
        _rec(105, "MID", 22, "Promoted", 6.0, 5.0, low_cov=True),  # excluded from the pool
    ]
    return recs


OWNED = [1, 2, 10, 11, 12, 13, 14, 20, 21, 22, 23, 24, 30, 31, 32]


def _tools(bank=2.0, free_transfers=1):
    ticker = {"8": [{"gw": 1, "opp": "Beta", "home": True, "attack_fdr": 2, "defence_fdr": 3},
                    {"gw": 2, "opp": "Alpha", "home": False, "attack_fdr": 4, "defence_fdr": 4}]}
    return AdvisorTools(_records(), OWNED, bank=bank, free_transfers=free_transfers, ticker=ticker)


# --- get_squad -------------------------------------------------------------------------- #
def test_get_squad_reports_the_fifteen_and_the_xi():
    s = _tools().get_squad()
    assert len(s["players"]) == 15
    assert sum(1 for p in s["players"] if p["starting"]) == 11
    assert s["bank"] == 2.0 and s["free_transfers"] == 1
    assert s["captain"] and s["projected_points"] > 0


def test_squad_rows_stay_small():
    """Every field here is re-billed on each later turn of the conversation, so the row is
    deliberately minimal — a regression that starts dumping whole records would quietly
    multiply the cost of every conversation."""
    row = _tools().get_squad()["players"][0]
    assert set(row) <= {"id", "name", "pos", "team", "price", "xp", "owned_by",
                        "starting", "flag", "chance_to_play", "penalties"}


def test_availability_is_only_surfaced_when_it_is_news():
    """An "available" flag on all 15 is pure token waste; a flag on the one doubtful player
    is the thing that changes the advice."""
    fit = _tools().get_squad()["players"]
    assert all("flag" not in p for p in fit)
    t = _tools()
    hurt = t.search_players(position="MID", exclude_owned=True, limit=MAX_SEARCH_RESULTS)
    flagged = [p for p in hurt["players"] if p.get("flag")]
    assert flagged and flagged[0]["flag"] == "injured"


# --- search_players --------------------------------------------------------------------- #
def test_search_filters_and_ranks_by_expected_points():
    r = _tools().search_players(position="MID", max_price=9.5)
    xps = [p["xp"] for p in r["players"]]
    assert xps == sorted(xps, reverse=True)
    assert all(p["pos"] == "MID" and p["price"] <= 9.5 for p in r["players"])


def test_search_excludes_owned_by_default():
    r = _tools().search_players(position="MID")
    assert all(p["id"] not in OWNED for p in r["players"])


def test_search_excludes_low_coverage_clubs():
    """Promoted/low-data clubs have untrustworthy projections and must never be recommended."""
    r = _tools().search_players(position="MID", limit=MAX_SEARCH_RESULTS)
    assert 105 not in [p["id"] for p in r["players"]]


def test_search_result_count_is_capped():
    r = _tools().search_players(limit=999)
    assert r["showing"] <= MAX_SEARCH_RESULTS
    assert r["matches"] >= r["showing"]     # the model is told how many it did NOT see


def test_search_by_ownership_finds_differentials():
    r = _tools().search_players(max_ownership=3.0)
    assert r["players"] and all(p["owned_by"] <= 3.0 for p in r["players"])


# --- simulate_transfers ----------------------------------------------------------------- #
def test_a_legal_upgrade_reports_the_gain():
    t = _tools(bank=2.0)
    out = t.simulate_transfers([{"out_id": 24, "in_id": 100}])   # weakest MID -> premium
    assert out["legal"] is True
    assert out["cost"] == 2.0 and out["bank_after"] == 0.0
    assert out["hits_taken"] == 0 and out["points_penalty"] == 0
    assert out["net_gain"] > 0


def test_a_move_over_budget_is_refused_with_the_reason():
    """The refusal has to say WHY, so the model can correct itself instead of guessing."""
    out = _tools(bank=0.5).simulate_transfers([{"out_id": 24, "in_id": 100}])
    assert out["legal"] is False
    assert any("bank" in p for p in out["problems"])


def test_the_three_per_club_rule_is_enforced():
    """The rule an LLM most reliably forgets. It is checked here, not described in the prompt."""
    recs = _records()
    for eid in (11, 12):                       # move two owned DEFs to Club0
        next(r for r in recs if r["element_id"] == eid)["team_id"] = 3
        next(r for r in recs if r["element_id"] == eid)["team_name"] = "Club0"
    t = AdvisorTools(recs, OWNED, bank=5.0, free_transfers=1)
    out = t.simulate_transfers([{"out_id": 24, "in_id": 102}])   # 102 is also Club0 -> 4th
    assert out["legal"] is False
    assert any("per club" in p for p in out["problems"])


def test_position_quota_is_enforced():
    """Swapping a MID for a FWD leaves 4 MID / 4 FWD — not a legal FPL squad."""
    out = _tools(bank=5.0).simulate_transfers([{"out_id": 24, "in_id": 103}])
    assert out["legal"] is False
    assert any("must have exactly" in p for p in out["problems"])


def test_a_second_transfer_costs_a_hit():
    t = _tools(bank=6.0, free_transfers=1)
    two = t.simulate_transfers([{"out_id": 24, "in_id": 100}, {"out_id": 23, "in_id": 101}])
    assert two["legal"] is True
    assert two["hits_taken"] == 1 and two["points_penalty"] == 4.0
    assert two["net_gain"] == pytest.approx(two["gain_before_hit"] - 4.0, abs=0.01)


def test_free_transfers_absorb_the_hit():
    t = _tools(bank=6.0, free_transfers=2)
    two = t.simulate_transfers([{"out_id": 24, "in_id": 100}, {"out_id": 23, "in_id": 101}])
    assert two["hits_taken"] == 0 and two["net_gain"] == two["gain_before_hit"]


def test_a_multi_move_plan_can_fund_an_upgrade():
    """The case a single-transfer ranking cannot express: sell a mid to afford the premium.
    With only £0.5m banked the upgrade alone is unaffordable, but paired with a downgrade it
    goes through — one decision, not two independent ones."""
    t = _tools(bank=0.5)
    assert t.simulate_transfers([{"out_id": 24, "in_id": 100}])["legal"] is False
    plan = t.simulate_transfers(
        [{"out_id": 24, "in_id": 100}, {"out_id": 23, "in_id": 101}])
    assert plan["legal"] is True and plan["bank_after"] >= 0


def test_selling_a_player_you_do_not_own_is_refused():
    out = _tools().simulate_transfers([{"out_id": 999, "in_id": 100}])
    assert out["legal"] is False and "not in the squad" in out["problems"][0]


def test_buying_a_player_you_already_own_is_refused():
    out = _tools().simulate_transfers([{"out_id": 24, "in_id": 20}])
    assert out["legal"] is False
    assert any("already owned" in p for p in out["problems"])


def test_buying_from_a_low_coverage_club_is_refused():
    out = _tools(bank=9.0).simulate_transfers([{"out_id": 24, "in_id": 105}])
    assert out["legal"] is False
    assert any("no projection" in p for p in out["problems"])


def test_empty_move_list_is_refused():
    assert _tools().simulate_transfers([])["legal"] is False


# --- fixture_run / squad_health ---------------------------------------------------------- #
def test_fixture_run_returns_the_difficulty_ratings():
    r = _tools().fixture_run("Mid0", horizon=2)
    assert len(r["fixtures"]) == 2
    assert r["fixtures"][0]["attack_difficulty"] == 2


def test_unknown_club_reports_an_error_rather_than_empty():
    """Silence would let the model assume the club simply has no fixtures."""
    assert "error" in _tools().fixture_run("Nowhere FC")


def test_squad_health_returns_flags():
    h = _tools().squad_health()
    assert "flags" in h and "bench_spend" in h


# --- schemas ------------------------------------------------------------------------------ #
def test_every_schema_is_strict_and_closed():
    """Loose schemas let the model invent argument names that silently do nothing."""
    for s in TOOL_SCHEMAS:
        assert s["strict"] is True
        assert s["input_schema"]["additionalProperties"] is False
        assert s["description"]


def test_every_schema_maps_to_a_real_method():
    t = _tools()
    for s in TOOL_SCHEMAS:
        assert callable(getattr(t, s["name"], None)), f"no method for tool {s['name']}"


def test_required_arguments_are_real_properties():
    for s in TOOL_SCHEMAS:
        props = s["input_schema"]["properties"]
        assert all(r in props for r in s["input_schema"]["required"])
