"""API tests — TestClient over a temp serving store, FPL client stubbed (no network).

Covers the read endpoints and, crucially, the /team personalisation path: the
element_id/web_name -> id/name adapter, an owned player with no prediction (unscored),
best-XI projection, a suggested transfer, and the balance check.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fpledge.api import main as api_main
from fpledge.api import store
from fpledge.api.main import app, get_fpl_client

GW = 1


def _rec(eid, pos, team_id, team_name, price, xp, own, xmin, low_cov=False):
    return {
        "code": eid, "element_id": eid, "web_name": f"P{eid}", "position": pos,
        "team_id": team_id, "team_name": team_name, "price": price, "x_minutes": xmin,
        "xp": xp, "ownership": own, "eo": own, "diff_value": xp * (1 - own / 100.0),
        "captain_score": xp, "low_cov": low_cov,
    }


def _synthetic_payload():
    """A 14-player scored squad (2GK/5DEF/5MID/2FWD) + unowned upgrade + a low-cov diff."""
    recs = []
    # GK
    recs += [_rec(1, "GK", 10, "Club A", 4.5, 3.0, 20, 90),
             _rec(2, "GK", 11, "Club B", 4.0, 2.5, 5, 90)]
    # DEF
    recs += [_rec(i, "DEF", 12 + i, f"Club D{i}", 4.5 + i * 0.1, 3.5 + i * 0.1, 15 + i, 88)
             for i in range(3, 8)]
    # MID (id 12 is the weakest -> should be the one transferred out)
    recs += [_rec(8, "MID", 20, "Club M8", 8.0, 8.0, 40, 90),
             _rec(9, "MID", 21, "Club M9", 7.0, 6.0, 30, 90),
             _rec(10, "MID", 22, "Club M10", 6.5, 5.5, 25, 90),
             _rec(11, "MID", 23, "Club M11", 6.0, 5.0, 20, 90),
             _rec(12, "MID", 24, "Club M12", 5.0, 2.0, 8, 90)]
    # FWD
    recs += [_rec(13, "FWD", 25, "Club F13", 9.0, 6.5, 35, 90),
             _rec(14, "FWD", 26, "Club F14", 7.5, 5.0, 22, 90)]
    # Unowned upgrade at MID (affordable within bank) -> should be the suggested transfer IN.
    recs += [_rec(20, "MID", 27, "Club M20", 6.5, 7.5, 12, 90)]
    # Low-owned, high-xP, reliable -> should surface in /differentials.
    recs += [_rec(21, "FWD", 28, "Club F21", 6.0, 5.8, 6, 90)]

    fpl_teams = {str(r["team_id"]): r["team_name"] for r in recs}
    ticker = {
        "10": [{"gw": 1, "opp_id": 11, "opp": "Club B", "home": True,
                "lam_for": 1.8, "lam_against": 0.9, "attack_fdr": 2, "defence_fdr": 1},
               {"gw": 2, "opp_id": 12, "opp": "Club D3", "home": False,
                "lam_for": 1.2, "lam_against": 1.5, "attack_fdr": 4, "defence_fdr": 4}],
    }
    return {
        "meta": {"gw": GW, "horizon": 5, "model_ver": "test-0.0", "run_ts": "2026-07-28T00:00:00Z",
                 "n_records": len(recs), "fallback_fixtures": 0},
        "fpl_teams": fpl_teams,
        "records": recs,
        "fixture_ticker": ticker,
    }


class _FakeClient:
    def __init__(self, summary):
        self._summary = summary

    def picks_summary(self, entry_id, gw):  # noqa: ANN001
        return self._summary


class _FakeHTTPError(Exception):
    """Mimics requests.HTTPError: carries a .response with a status_code."""

    def __init__(self, status):  # noqa: ANN001
        super().__init__(f"HTTP {status}")
        self.response = type("R", (), {"status_code": status})()


class _FailingClient:
    """A private/nonexistent entry -> the FPL API returns 404."""

    def picks_summary(self, entry_id, gw):  # noqa: ANN001
        raise _FakeHTTPError(404)


class _OutageClient:
    """A network error / FPL outage -> no HTTP response at all."""

    def picks_summary(self, entry_id, gw):  # noqa: ANN001
        raise RuntimeError("connection reset")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    store.write_gw(GW, _synthetic_payload())
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()
    api_main._picks_cache.clear()  # isolate the short-TTL picks cache between tests


def test_health_lists_precomputed_gw(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "available_gws": [GW]}


def test_predictions_sorted_and_projected(client):
    r = client.get(f"/predictions/{GW}")
    assert r.status_code == 200
    body = r.json()
    xps = [p["xp"] for p in body["predictions"]]
    assert xps == sorted(xps, reverse=True)          # ranked by xP
    top = body["predictions"][0]
    assert set(top) == {"element_id", "web_name", "position", "team", "price",
                        "xp", "ownership", "diff_value", "x_minutes", "low_coverage",
                        "xp_next3", "fixtures"}
    assert top["element_id"] == 8 and top["xp"] == 8.0


def test_predictions_missing_gw_is_404(client):
    assert client.get("/predictions/99").status_code == 404


def test_fixtures_ticker_grid(client):
    r = client.get(f"/fixtures/{GW}")
    assert r.status_code == 200
    teams = r.json()["teams"]
    club_a = next(t for t in teams if t["team_id"] == 10)
    assert club_a["team_name"] == "Club A"
    assert [f["gw"] for f in club_a["fixtures"]] == [1, 2]
    # horizon=1 slices to just GW1
    r2 = client.get(f"/fixtures/{GW}?horizon=1")
    club_a2 = next(t for t in r2.json()["teams"] if t["team_id"] == 10)
    assert [f["gw"] for f in club_a2["fixtures"]] == [1]


def test_differentials_respects_filters(client):
    r = client.get(f"/differentials/{GW}?max_ownership=15&min_xp=3.5")
    assert r.status_code == 200
    diffs = r.json()["differentials"]
    assert all(d["ownership"] <= 15 and d["xp"] >= 3.5 for d in diffs)
    assert 21 in [d["element_id"] for d in diffs]     # the low-owned high-xP FWD


def test_team_personalisation_end_to_end(client):
    owned = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    summary = {"element_ids": owned + [999], "captain": 8, "vice_captain": 13,
               "bank": 5.0, "squad_value": 100.0}
    app.dependency_overrides[get_fpl_client] = lambda: _FakeClient(summary)

    r = client.get(f"/team/1234567?gw={GW}&free_transfers=1")
    assert r.status_code == 200
    body = r.json()

    assert body["unscored_elements"] == [999]         # owned but no prediction
    assert body["projected_points"] is not None
    assert body["captain"]["element_id"] == 8         # highest-xP starter
    # every squad row came through the element_id/web_name adapter
    assert all("element_id" in p and "web_name" in p for p in body["squad"])
    assert {p["element_id"] for p in body["squad"]} == set(owned)
    # best transfer swaps the weak MID (12) for the affordable upgrade (20)
    bt = body["best_transfer"]
    assert bt is not None and bt["out"]["element_id"] == 12 and bt["in"]["element_id"] == 20
    assert bt["net_gain"] > 0
    assert body["balance"]["n_players"] == 14


def test_team_picks_cached_across_requests(client):
    owned = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    summary = {"element_ids": owned, "captain": 8, "vice_captain": 13, "bank": 5.0, "squad_value": 100.0}
    calls = {"n": 0}

    class _Counting:
        def picks_summary(self, entry_id, gw):  # noqa: ANN001
            calls["n"] += 1
            return summary

    app.dependency_overrides[get_fpl_client] = lambda: _Counting()
    assert client.get(f"/team/1234567?gw={GW}").status_code == 200
    assert client.get(f"/team/1234567?gw={GW}").status_code == 200
    assert calls["n"] == 1  # second request is served from the picks cache, not the FPL API


def test_team_demo_needs_no_client(client):
    # /team/0 is the sample team: it must build from precomputed records without ever
    # touching the FPL API, so even a failing client returns a full dashboard.
    app.dependency_overrides[get_fpl_client] = lambda: _FailingClient()
    r = client.get(f"/team/0?gw={GW}")
    assert r.status_code == 200
    body = r.json()
    assert body["projected_points"] is not None
    assert len(body["squad"]) == 15          # 2 GK + 5 DEF + 5 MID + 3 FWD
    assert body["bank"] == 0.0


def test_team_unfetchable_entry_is_404_with_helpful_message(client):
    app.dependency_overrides[get_fpl_client] = lambda: _FailingClient()
    r = client.get(f"/team/999999?gw={GW}")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "sample team" in detail            # points the user at the working demo
    assert "deadline" in detail               # explains the preseason cause


def test_team_api_outage_is_502(client):
    app.dependency_overrides[get_fpl_client] = lambda: _OutageClient()
    r = client.get(f"/team/999999?gw={GW}")
    assert r.status_code == 502              # a network failure is not blamed on the id
