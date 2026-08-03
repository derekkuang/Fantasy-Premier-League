"""Match briefings, and above all the numeric guard.

The guard is the only thing standing between a fluent language model and a fabricated
statistic on a page whose entire selling point is honesty. So most of these tests are attempts
to smuggle a wrong number past it.
"""

from __future__ import annotations

from fpledge.brief import (
    MODEL,
    brief_matches,
    fact_pack,
    narrate,
    render_template,
    unsupported_numbers,
    verify,
)

MATCH = {
    "match_id": "1-1-2", "gw": 1,
    "home_id": 1, "home": "Alpha", "away_id": 2, "away": "Beta",
    "source": "model", "lam_home": 2.1, "lam_away": 0.9,
    "result": {"home_win": 0.6321, "draw": 0.2144, "away_win": 0.1535},
    "btts": 0.4512, "over_2_5": 0.5893, "under_2_5": 0.4107,
    "clean_sheet": {"home": 0.4066, "away": 0.1225},
    "most_likely_score": [2, 0],
    "scorelines": [{"home": 2, "away": 0, "p": 0.1288}],
    "scorelines_p": 0.71,
    "fdr": {"home": {"attack": 1, "defence": 1}, "away": {"attack": 5, "defence": 5}},
    "lineups": {"home": {"formation": "4-3-3", "xi": [], "bench": [], "confidence": 0.8},
                "away": None},
}
ASSETS = [
    {"web_name": "Striker", "team": "Alpha", "position": "FWD",
     "xp": 6.42, "price": 9.5, "ownership": 31.2},
]


def _pack():
    return fact_pack(MATCH, ASSETS)


# --- the fact pack --------------------------------------------------------------------- #
def test_probabilities_arrive_as_whole_percentages():
    """Pre-converting removes the model's need to do arithmetic — the largest single source of
    plausible-but-wrong numbers."""
    p = _pack()
    assert p["home_win_pct"] == 63
    assert p["draw_pct"] == 21
    assert p["away_win_pct"] == 15
    assert p["both_teams_to_score_pct"] == 45


def test_pack_omits_missing_values_rather_than_carrying_nulls():
    thin = dict(MATCH, lineups={})
    p = fact_pack(thin, assets=None)
    assert "home_projected_formation" not in p
    assert "top_players_by_expected_points" not in p
    assert None not in p.values()


# --- the guard ------------------------------------------------------------------------- #
def test_accepts_numbers_taken_straight_from_the_pack():
    p = _pack()
    assert unsupported_numbers("Alpha are 63% to win; the draw is 21%.", p) == []


def test_rejects_a_fabricated_statistic():
    """The headline failure mode: a real-sounding number that was never computed."""
    p = _pack()
    assert unsupported_numbers("Alpha attack 77% down the left.", p) == ["77%"]


def test_rejects_a_number_that_is_merely_close():
    """65 is not 63. Rounding tolerance must not become a licence to drift."""
    p = _pack()
    assert unsupported_numbers("Alpha are 65% to win.", p) == ["65%"]


def test_rejects_arithmetic_the_model_did_itself():
    """63 + 21 = 84 is correct arithmetic and still forbidden — the pack has no 84, so nothing
    verified it. Every displayed number must trace to a computed one."""
    p = _pack()
    assert unsupported_numbers("Alpha avoid defeat 84% of the time.", p) == ["84%"]


def test_tolerance_follows_the_precision_written():
    """Honest rounding of a pack value passes; inventing precision the pack never had does not.
    The pack says 2.1, so "2.14" is a claim to a third significant figure we cannot support."""
    p = _pack()
    assert unsupported_numbers("Expected goals of 2.1.", p) == []
    assert unsupported_numbers("Expected goals of 2.14.", p) == ["2.14"]
    assert unsupported_numbers("Expected goals of 2.3.", p) == ["2.3"]


def test_numbers_inside_pack_strings_are_grounded():
    """"2-0" and "4-3-3" are pack values; their digits must not be flagged as inventions."""
    p = _pack()
    assert unsupported_numbers("The likeliest score is 2-0 and Alpha line up 4-3-3.", p) == []


def test_nested_pack_values_are_grounded():
    p = _pack()
    assert unsupported_numbers("Striker projects 6.42 points at 9.5m.", p) == []


def test_a_number_cannot_be_borrowed_from_an_uncited_fact():
    """41 is a real pack value — the clean-sheet chance. Citing only `home_win_pct` and then
    writing 41 means the sentence is using a figure it is not about. Pack-wide checking would
    wave this through; evidence-scoped checking catches it."""
    p = _pack()
    assert p["home_clean_sheet_pct"] == 41
    borrowed = {"headline": "", "angles": [
        {"text": "Alpha attack 41% down the left.", "evidence": ["home_win_pct"]},
    ]}
    assert verify(borrowed, p)
    honest = {"headline": "", "angles": [
        {"text": "Alpha keep a clean sheet 41% of the time.", "evidence": ["home_clean_sheet_pct"]},
    ]}
    assert verify(honest, p) == []


def test_verify_rejects_invented_evidence_keys():
    """A citation to a key that doesn't exist means the sentence was not actually grounded."""
    p = _pack()
    bad = {"headline": "x", "angles": [{"text": "Alpha are 63% to win.",
                                        "evidence": ["home_win_pct", "possession_pct"]}]}
    problems = verify(bad, p)
    assert any("possession_pct" in msg for msg in problems)


def test_verify_rejects_an_empty_briefing():
    assert verify({"headline": "x", "angles": []}, _pack())


def test_verify_passes_a_clean_briefing():
    p = _pack()
    good = {"headline": "Alpha 63% to win", "angles": [
        {"text": "Alpha are 63% to win with the draw at 21%.",
         "evidence": ["home_win_pct", "draw_pct"]},
        {"text": "A clean sheet lands 41% of the time for Alpha.",
         "evidence": ["home_clean_sheet_pct"]},
    ]}
    assert verify(good, p) == []


# --- the template floor ----------------------------------------------------------------- #
def test_template_briefing_passes_its_own_guard():
    """The fallback must satisfy the same check it exists to backstop. If the deterministic
    renderer can't pass, the guard is miscalibrated."""
    p = _pack()
    assert verify(render_template(p), p) == []


def test_template_survives_a_pack_with_no_players():
    p = fact_pack(MATCH, assets=None)
    out = render_template(p)
    assert verify(out, p) == []
    assert len(out["angles"]) >= 2


# --- generation, with the model stubbed ------------------------------------------------- #
class _Resp:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class _Client:
    """Returns a scripted response per call, so retry behaviour is observable."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        return _Resp(self.texts[min(self.calls - 1, len(self.texts) - 1)])


def test_a_clean_model_briefing_is_used():
    p = _pack()
    client = _Client('{"headline": "Alpha 63% to win", "angles": '
                     '[{"text": "Alpha are 63% to win.", "evidence": ["home_win_pct"]}, '
                     '{"text": "Draw at 21%.", "evidence": ["draw_pct"]}]}')
    out = narrate(p, client=client)
    assert out["generated_by"] == MODEL
    assert out["attempts"] == 1


def test_a_hallucinated_number_is_retried_then_falls_back():
    p = _pack()
    bad = ('{"headline": "h", "angles": [{"text": "Alpha attack 77% down the left.", '
           '"evidence": ["home_win_pct"]}]}')
    client = _Client(bad, bad)
    out = narrate(p, client=client)
    assert client.calls == 2                     # retried once with the rejection reason
    assert out["generated_by"] == "template"     # then refused to publish it
    assert any("77%" in r for r in out["rejected"])


def test_a_second_attempt_can_succeed():
    p = _pack()
    bad = '{"headline": "h", "angles": [{"text": "Alpha win 77%.", "evidence": ["home_win_pct"]}]}'
    good = ('{"headline": "h", "angles": [{"text": "Alpha win 63%.", '
            '"evidence": ["home_win_pct"]}, {"text": "Draw 21%.", "evidence": ["draw_pct"]}]}')
    out = narrate(p, client=_Client(bad, good))
    assert out["generated_by"] == MODEL and out["attempts"] == 2


def test_an_api_failure_falls_back_silently():
    class _Broken:
        messages = property(lambda self: self)

        def create(self, **kw):
            raise RuntimeError("network down")

    out = narrate(_pack(), client=_Broken())
    assert out["generated_by"] == "template"


def test_no_client_means_template_not_an_error():
    """No API key must degrade to the template, never break the precompute."""
    out = narrate(_pack(), client=None)
    assert out["generated_by"] in ("template", MODEL)


# --- batch wiring ------------------------------------------------------------------------ #
def test_only_the_current_gameweek_is_briefed():
    """Narrating eight gameweeks out would cost ten times as much to describe projections
    nobody should act on yet."""
    later = dict(MATCH, match_id="3-1-2", gw=3)
    matches = [dict(MATCH), later]
    n = brief_matches(matches, {"1-1-2": ASSETS}, client=_Client("{bad json"))
    assert n == 1
    assert "brief" in matches[0] and "brief" not in matches[1]


def test_the_fact_pack_ships_beside_the_prose():
    """Every number in the briefing has to be checkable by the reader, not just by us."""
    matches = [dict(MATCH)]
    brief_matches(matches, {"1-1-2": ASSETS}, client=_Client("{bad json"))
    pack = matches[0]["brief"]["fact_pack"]
    assert pack["home_win_pct"] == 63
    assert unsupported_numbers(matches[0]["brief"]["angles"][0]["text"], pack) == []


def test_brief_matches_handles_no_matches():
    assert brief_matches([], {}, client=None) == 0
