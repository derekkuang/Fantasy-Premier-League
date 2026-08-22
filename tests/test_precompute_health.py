"""The precompute's refusal to publish a degraded artifact.

This is the guard for the failure docs/HANDOFF.md §4 calls "the one thing that will silently rot
a deployed site", and it had been an open item since 2026-08-03. The failure is not a crash: a
dropped source season printed `warn:`, exited 0, and left the engine fitted on less history while
every projection got slightly worse and the site served it for weeks.

So these tests are about the check FIRING, not about it passing. A threshold that is wrong in the
lenient direction is worse than no threshold at all, because it converts a loud failure into a
reassuring green tick.
"""

from __future__ import annotations

import pytest

from fpledge.api.precompute import MAX_FALLBACK_FIXTURES, MIN_RECORDS, health_check


def _healthy(**over):
    meta = {
        "n_records": 555,
        "fallback_fixtures": 2,
        "source": {"requested": ["2324", "2425", "2526"],
                   "loaded": ["2023-24", "2024-25", "2025-26"],
                   "failed": [], "unmapped_teams": [], "n_matches": 1140},
    }
    meta.update(over)
    return meta


def test_a_healthy_run_reports_no_problems():
    assert health_check(_healthy()) == []


def test_a_dropped_source_season_is_a_refusal():
    """The original bug, verbatim: this used to print `warn:` and exit 0."""
    meta = _healthy(source={**_healthy()["source"],
                            "failed": [{"code": "2324", "season": "2023-24", "error": "timeout"}]})
    problems = health_check(meta)
    assert problems
    assert "2023-24" in problems[0]
    assert "less history" in problems[0]


def test_every_failed_season_is_named_not_just_counted():
    meta = _healthy(source={**_healthy()["source"], "failed": [
        {"code": "2324", "season": "2023-24", "error": "x"},
        {"code": "2425", "season": "2024-25", "error": "y"},
    ]})
    p = health_check(meta)[0]
    assert "2023-24" in p and "2024-25" in p


def test_fallback_fixtures_creeping_up_is_a_refusal():
    """§4's exact symptom: fallback_fixtures jumping 2 -> 4 while the run still exits 0."""
    assert health_check(_healthy(fallback_fixtures=4))
    assert health_check(_healthy(fallback_fixtures=MAX_FALLBACK_FIXTURES)) == []


def test_two_fallback_fixtures_is_healthy_because_promoted_sides_have_no_history():
    """The threshold must not fire on the normal state or it will be switched off."""
    assert health_check(_healthy(fallback_fixtures=2)) == []


def test_an_implausibly_small_record_count_is_a_refusal():
    assert health_check(_healthy(n_records=MIN_RECORDS - 1))
    assert health_check(_healthy(n_records=MIN_RECORDS)) == []


def test_several_problems_are_all_reported_not_just_the_first():
    """Fixing one and re-running should not reveal a new one each time."""
    meta = _healthy(n_records=10, fallback_fixtures=9,
                    source={**_healthy()["source"],
                            "failed": [{"code": "2324", "season": "2023-24", "error": "x"}]})
    assert len(health_check(meta)) == 3


def test_missing_metadata_does_not_crash_the_check():
    """An older artifact has no `source` key. The check must degrade to what it can see rather
    than raising, or a schema change becomes an outage."""
    assert health_check({}) == []
    assert health_check({"n_records": 555}) == []


# --- the source loader's report ------------------------------------------------------------ #
def test_load_seasons_report_records_a_failure_instead_of_swallowing_it(monkeypatch):
    from fpledge.ingest import footballdata

    def fake_download(code, division="E0"):
        if code == "2425":
            raise RuntimeError("connection reset")
        return "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA\nE0,16/08/2024,A,B,1,0,2,3,4\n"

    monkeypatch.setattr(footballdata, "download_season", fake_download)
    matches, report = footballdata.load_seasons_report(["2324", "2425"])
    assert len(matches) == 1                      # only the season that worked
    assert [f["code"] for f in report["failed"]] == ["2425"]
    assert report["loaded"] == ["2023-24"]
    assert report["n_matches"] == 1


def test_the_legacy_loader_still_returns_just_matches(monkeypatch):
    from fpledge.ingest import footballdata

    monkeypatch.setattr(footballdata, "download_season", lambda c, d="E0":
                        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA\n"
                        "E0,16/08/2024,A,B,1,0,2,3,4\n")
    assert isinstance(footballdata.load_seasons(["2324"]), list)


def test_promoted_clubs_do_not_trip_the_unmapped_check():
    """THE FALSE POSITIVE THIS CHECK SHIPPED WITH, caught on its first live run. Exactly three
    clubs are promoted each season, and a promoted club has no top-flight history, so it cannot
    be mapped and correctly falls back to the promoted-side prior. Firing here would make the
    healthy state look degraded every August — and a check that cries wolf gets switched off,
    which is worse than not having written it."""
    for n in (1, 2, 3):
        meta = _healthy(source={**_healthy()["source"],
                                "unmapped_teams": [f"Promoted {i}" for i in range(n)]})
        assert health_check(meta) == [], f"{n} unmapped teams should be normal"


def test_more_unmapped_than_promoted_clubs_is_a_refusal():
    """Four-plus means the name mapping broke, not that four clubs came up."""
    meta = _healthy(source={**_healthy()["source"],
                            "unmapped_teams": ["A", "B", "C", "D"]})
    p = health_check(meta)
    assert p and "mapping has probably broken" in p[0]


# --- the publish gate: nothing degraded reaches the serving store ---------------------------- #
# These exist because the ORDER inverted. run() used to write the artifact and let the caller
# health-check afterwards — right, back when "written" meant a local file a human inspects;
# silently wrong from the moment store.write_gw began publishing to the S3 the live API serves.
from fpledge.api import store
from fpledge.api.precompute import build_payload, next_gameweek, publish_gate, run


def _payload(n=500, xp=4.0, gw=1, clubs=20):
    return {
        "meta": {"gw": gw, "horizon": 8, "model_ver": "t", "run_ts": "t", "n_records": n,
                 "fallback_fixtures": 2, "source": {"loaded": ["a"], "requested": ["a"],
                                                    "failed": [], "unmapped_teams": []}},
        "records": [{"element_id": i, "xp": xp, "team_id": i % clubs} for i in range(n)],
    }


@pytest.fixture(autouse=True)
def _serving_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path / "serving"))
    monkeypatch.delenv("FPLEDGE_SERVING_URI", raising=False)
    store.invalidate()
    yield
    store.invalidate()


def test_a_degraded_artifact_never_reaches_the_store(monkeypatch):
    """THE ORDERING BUG. With the old write-then-check shape this test fails: the artifact is
    in the store by the time anyone sees the problems, and on S3 that means served to users."""
    bad = _payload(n=50)   # far under MIN_RECORDS
    monkeypatch.setattr("fpledge.api.precompute.build_payload",
                        lambda gw, horizon=8, run_ts=None, narrate=True: bad)
    res = run(1)
    assert res["published"] is False and res["problems"]
    assert store.read_gw(1) is None, "the degraded artifact was published"


def test_a_healthy_artifact_publishes_and_reports_no_problems(monkeypatch):
    monkeypatch.setattr("fpledge.api.precompute.build_payload",
                        lambda gw, horizon=8, run_ts=None, narrate=True: _payload())
    res = run(1)
    assert res["published"] is True and res["problems"] == []
    assert store.read_gw(1) is not None


def test_allow_degraded_publishes_but_still_reports(monkeypatch):
    bad = _payload(n=50)
    monkeypatch.setattr("fpledge.api.precompute.build_payload",
                        lambda gw, horizon=8, run_ts=None, narrate=True: bad)
    res = run(1, allow_degraded=True)
    assert res["published"] is True
    assert res["problems"], "override must not hide the problems it overrode"


def test_a_degenerate_fit_is_blocked_even_when_inputs_look_healthy():
    """publish_gate exists for what health_check cannot see: every input fine, output garbage."""
    zeroed = _payload(xp=0.0)
    assert any("non-zero" in p for p in publish_gate(zeroed, None))


def test_losing_half_the_players_within_covered_clubs_is_blocked():
    """Same 20 clubs, under half the players each — a degenerate fit, not a small week."""
    assert any("players per club fell" in p
               for p in publish_gate(_payload(n=200), _payload(n=550)))


def test_a_blank_heavy_gameweek_is_not_mistaken_for_a_degenerate_fit():
    """THE FALSE POSITIVE THE RAW-COUNT CHECK WOULD SHIP: a cup-rescheduled week can carry
    half the clubs and therefore half the records while every covered club is fully priced.
    Refusing to publish it would freeze the site on the PREVIOUS week's artifact for exactly
    the gameweek rescheduling makes projections most wanted — staleness enforced by the guard
    against rot. Density (players per club) separates the two: blanks lose whole clubs,
    degenerate fits lose players inside clubs."""
    blank_week = _payload(n=220, clubs=8)      # 8 clubs, ~27 players each
    full_week = _payload(n=550, clubs=20)      # 20 clubs, ~27 players each
    assert publish_gate(blank_week, full_week) == []


def test_a_collapsed_mean_projection_is_blocked():
    assert any("collapsed" in p for p in publish_gate(_payload(xp=0.5), _payload(xp=4.0)))


def test_a_normal_week_to_week_change_is_not_blocked():
    """The gate must trip on 'grossly wrong', never on 'different' — a gate that cries wolf
    gets --allow-degraded added to the cron line, and then it guards nothing."""
    assert publish_gate(_payload(n=540, xp=3.4), _payload(n=555, xp=4.1)) == []


def test_first_publish_with_no_live_artifact_only_runs_absolute_checks():
    assert publish_gate(_payload(), None) == []


def test_publish_gate_reads_the_shape_build_payload_actually_writes(monkeypatch):
    """THE KEY-MISMATCH BUG. The gate read `predictions`; build_payload writes `records`. Every
    check saw an empty list, silently skipped, and the gate published anything health_check let
    through — a no-op guard shaped exactly like a working one. The hand-rolled `_payload` helper
    above encoded the same wrong key, so the suite stayed green. This test is the contract: the
    gate must catch a degenerate artifact that came from build_payload ITSELF, so the two can
    never diverge on shape again."""
    out = {
        "records": [{"element_id": i, "xp": 0.0, "team_id": 1, "web_name": f"p{i}",
                     "team_name": "A", "position": "MID", "price": 5.0, "ownership": 1.0}
                    for i in range(500)],
        "matches": [], "fallback": [], "fpl_teams": {1: "A"},
        "fixture_ticker": {}, "source_report": {},
    }
    monkeypatch.setattr("fpledge.api.precompute.assemble_for_serving",
                        lambda gw, horizon=8: out)
    payload = build_payload(1, narrate=False)
    assert any("non-zero" in p for p in publish_gate(payload, None)), (
        "an all-zero artifact built by build_payload passed the gate — the gate is reading "
        "a key build_payload does not write"
    )


# --- auto gameweek: a scheduler must never pass a literal number ----------------------------- #
def test_next_gameweek_prefers_fpls_own_flag(monkeypatch):
    boot = {"events": [{"id": 1, "is_next": False}, {"id": 2, "is_next": True}]}
    monkeypatch.setattr("fpledge.storage.load.latest_raw", lambda s, e: boot)
    assert next_gameweek() == 2


def test_next_gameweek_falls_back_to_the_earliest_future_deadline(monkeypatch):
    boot = {"events": [
        {"id": 1, "deadline_time": "2020-01-01T00:00:00Z"},
        {"id": 2, "deadline_time": "2099-01-01T00:00:00Z"},
        {"id": 3, "deadline_time": "2099-02-01T00:00:00Z"},
    ]}
    monkeypatch.setattr("fpledge.storage.load.latest_raw", lambda s, e: boot)
    assert next_gameweek() == 2


def test_a_stale_bootstrap_raises_rather_than_precomputing_the_past(monkeypatch):
    boot = {"events": [{"id": 38, "deadline_time": "2020-01-01T00:00:00Z"}]}
    monkeypatch.setattr("fpledge.storage.load.latest_raw", lambda s, e: boot)
    with pytest.raises(RuntimeError, match="stale"):
        next_gameweek()
