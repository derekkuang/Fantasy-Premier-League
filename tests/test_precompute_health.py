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
