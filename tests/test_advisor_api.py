"""The advisor endpoint — and above all, its refusal to pretend.

This is the only route that costs money per call. Everything else on the site is a read from a
precomputed file, so the failure mode of a bad deploy is a stale number; here it is a bill, or
worse, a feature that looks like it works and silently doesn't. So the tests that matter are
the ones about what happens when it ISN'T configured.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fpledge.api import main as api_main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FPLEDGE_ADVISOR_STUB", raising=False)
    api_main._advisor_hits.clear()   # the limiter is process-global; don't leak between tests
    return TestClient(api_main.app)


def _payload() -> dict:
    """A minimal serving artifact: 15 players spread across a legal squad shape."""
    records = []
    for i in range(1, 16):
        pos = "GK" if i <= 2 else "DEF" if i <= 7 else "MID" if i <= 12 else "FWD"
        records.append({
            "element_id": i, "web_name": f"P{i}", "position": pos,
            "team_id": (i % 4) + 1, "team_name": f"Club{(i % 4) + 1}",
            "price": 5.0, "xp": 4.0 + i * 0.1, "ownership": 10.0, "x_minutes": 80.0,
            "low_cov": False, "diff_value": 1.0, "captain_score": 1.0,
        })
    return {
        "meta": {"gw": 1, "model_ver": "t", "run_ts": "t", "n_records": len(records)},
        "fpl_teams": {}, "records": records, "fixture_ticker": {}, "matches": [],
    }


def _write(tmp_path, payload) -> None:
    (tmp_path / "gw1.json").write_text(json.dumps(payload))


# --- switched off -------------------------------------------------------------------- #
def test_status_reports_unavailable_with_a_reason(client):
    """The UI asks before anyone types, so the answer has to say WHY, not just no."""
    body = client.get("/advise").json()
    assert body["available"] is False
    assert body["stub"] is False
    assert "ANTHROPIC_API_KEY" in body["reason"]


def test_posting_without_a_client_is_a_503_not_a_canned_answer(client, tmp_path):
    """The one thing this endpoint must never do is answer anyway. A plausible reply with no
    model behind it is worse than an error — it can't be told apart from the real feature."""
    _write(tmp_path, _payload())
    res = client.post("/advise", json={"gw": 1, "owned": list(range(1, 16)), "message": "hi"})
    assert res.status_code == 503
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


# --- input guards -------------------------------------------------------------------- #
def test_stub_mode_is_flagged_all_the_way_out(monkeypatch, tmp_path):
    """A scripted reply must arrive labelled, or the preview becomes a lie by omission."""
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("FPLEDGE_ADVISOR_STUB", "1")
    api_main._advisor_hits.clear()
    _write(tmp_path, _payload())
    c = TestClient(api_main.app)

    assert c.get("/advise").json() == {
        "available": True, "stub": True, "model": api_main._ADVISOR_MODEL, "reason": None,
    }
    body = c.post("/advise", json={
        "gw": 1, "owned": list(range(1, 16)), "bank": 0.0, "message": "review my squad",
    }).json()
    assert body["stub"] is True
    assert "stub" in body["reply"].lower()
    # the tools really ran — that is the whole point of the stub over a hardcoded string
    assert [c["tool"] for c in body["tool_calls"]] == ["get_squad", "squad_health"]


def test_history_survives_the_round_trip_as_plain_json(monkeypatch, tmp_path):
    """Continuing a conversation means resending it, so whatever comes back must be able to
    go out again. SDK content blocks are not JSON — if they leak, turn two fails."""
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("FPLEDGE_ADVISOR_STUB", "1")
    api_main._advisor_hits.clear()
    _write(tmp_path, _payload())
    c = TestClient(api_main.app)

    body = c.post("/advise", json={
        "gw": 1, "owned": list(range(1, 16)), "message": "review my squad",
    }).json()
    json.dumps(body["history"])          # raises if anything non-serialisable got through
    assert all(isinstance(m, dict) and "role" in m for m in body["history"])


def test_availability_is_checked_before_the_input(client, tmp_path):
    """Precedence, deliberately: "is this feature even on" outranks "is this input valid".
    A 400 would imply the request was nearly right, when nothing about it could have worked."""
    _write(tmp_path, _payload())
    assert client.post("/advise", json={"gw": 1, "owned": [1], "message": "  "}).status_code == 503


def test_an_empty_message_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("FPLEDGE_ADVISOR_STUB", "1")
    api_main._advisor_hits.clear()
    _write(tmp_path, _payload())
    c = TestClient(api_main.app)
    assert c.post("/advise", json={"gw": 1, "owned": [1], "message": "  "}).status_code == 400


def test_an_essay_is_rejected(monkeypatch, tmp_path):
    """This is a question box. Unbounded input is unbounded input tokens."""
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("FPLEDGE_ADVISOR_STUB", "1")
    api_main._advisor_hits.clear()
    _write(tmp_path, _payload())
    c = TestClient(api_main.app)
    res = c.post("/advise", json={
        "gw": 1, "owned": list(range(1, 16)), "message": "x" * 601,
    })
    assert res.status_code == 400


def test_a_long_history_is_rejected(monkeypatch, tmp_path):
    """Every turn resends the whole conversation, so history length IS cost."""
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("FPLEDGE_ADVISOR_STUB", "1")
    api_main._advisor_hits.clear()
    _write(tmp_path, _payload())
    c = TestClient(api_main.app)
    res = c.post("/advise", json={
        "gw": 1, "owned": list(range(1, 16)), "message": "hi",
        "history": [{"role": "user", "content": "x"}] * 50,
    })
    assert res.status_code == 400


def test_the_rate_limit_fires(monkeypatch, tmp_path):
    """Not the real quota — that needs a database. This is the fuse that stops the preview
    turning into a bill while the real one is still unbuilt."""
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("FPLEDGE_ADVISOR_STUB", "1")
    api_main._advisor_hits.clear()
    _write(tmp_path, _payload())
    c = TestClient(api_main.app)

    body = {"gw": 1, "owned": list(range(1, 16)), "message": "review my squad"}
    codes = [c.post("/advise", json=body).status_code for _ in range(api_main._ADVISOR_PER_WINDOW + 1)]
    assert codes[-1] == 429
    assert set(codes[:-1]) == {200}


# --- the model card ------------------------------------------------------------------ #
def test_model_card_404s_rather_than_inventing_numbers(client, monkeypatch, tmp_path):
    """A page that publishes the model's accuracy must not fall back to a placeholder."""
    monkeypatch.setattr(api_main.config, "DATA_DIR", tmp_path)
    res = client.get("/model")
    assert res.status_code == 404
    assert "build_model_card" in res.json()["detail"]


def test_model_card_is_served_when_generated(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api_main.config, "DATA_DIR", tmp_path)
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "model_card.json").write_text(json.dumps({"season": "2025-26"}))
    assert client.get("/model").json() == {"season": "2025-26"}
