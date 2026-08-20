"""The capture index: durable, append-free, and it must not lose the history that predates it.

Two properties carry the weight here. One object per capture, because appending is not something
object storage does and two overlapping captures would otherwise erase each other. And a read
that merges the legacy local JSONL, because thirteen news captures and a snapshot exist only in
those files — an index that silently starts at zero is indistinguishable from a project that has
never captured anything.
"""

from __future__ import annotations

import json

import pytest

from fpledge.ingest import capture_index, landing
from fpledge.ingest.landing import LocalBackend


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Point both the raw zone and the legacy index at a scratch directory."""
    monkeypatch.setattr("fpledge.config.DATA_DIR", tmp_path)
    landing.configure(LocalBackend(tmp_path / "raw"))
    yield
    landing.configure(None)


def _legacy(kind: str, rows: list[dict]) -> None:
    p = capture_index.legacy_path(kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))


# --- the basic contract --------------------------------------------------------------------- #
def test_a_recorded_capture_reads_back():
    capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z", "n_items": 7})
    got = capture_index.entries(capture_index.NEWS)
    assert [r["n_items"] for r in got] == [7]


def test_no_captures_is_an_empty_list_not_an_error():
    assert capture_index.entries(capture_index.NEWS) == []


def test_entries_come_back_oldest_first():
    """`best_capture_per_gameweek` and `field_scores` both assume this ordering."""
    for ts in ("20260820T180000Z", "20260820T060000Z", "20260820T120000Z"):
        capture_index.record(capture_index.NEWS, {"ingest_ts": ts})
    assert [r["ingest_ts"] for r in capture_index.entries(capture_index.NEWS)] == [
        "20260820T060000Z", "20260820T120000Z", "20260820T180000Z"]


def test_two_captures_do_not_overwrite_each_other():
    """THE REASON THIS IS NOT A JSONL IN S3. Appending to an object means read-modify-write, and
    two captures overlapping — a retry, a manual run beside a scheduled one, a double-fired
    scheduler — would silently erase the earlier entry. One object each has no such window."""
    capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z", "n": 1})
    capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060001Z", "n": 2})
    assert sorted(r["n"] for r in capture_index.entries(capture_index.NEWS)) == [1, 2]


def test_kinds_do_not_bleed_into_each_other():
    capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z", "which": "news"})
    capture_index.record(capture_index.SNAPSHOT, {"ingest_ts": "20260820T060000Z", "which": "snap"})
    assert [r["which"] for r in capture_index.entries(capture_index.NEWS)] == ["news"]
    assert [r["which"] for r in capture_index.entries(capture_index.SNAPSHOT)] == ["snap"]


# --- not losing the past -------------------------------------------------------------------- #
def test_the_legacy_jsonl_is_still_read():
    """History that stops resolving is the failure this whole layer exists to avoid."""
    _legacy(capture_index.NEWS, [{"ingest_ts": "20260801T060000Z", "n_items": 196}])
    assert [r["n_items"] for r in capture_index.entries(capture_index.NEWS)] == [196]


def test_legacy_and_landed_entries_merge_in_time_order():
    _legacy(capture_index.NEWS, [{"ingest_ts": "20260801T060000Z", "era": "legacy"},
                                 {"ingest_ts": "20260802T060000Z", "era": "legacy"}])
    capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z", "era": "landed"})
    assert [r["era"] for r in capture_index.entries(capture_index.NEWS)] == [
        "legacy", "legacy", "landed"]


def test_a_capture_present_in_both_is_counted_once():
    """A migrated capture should not read as two runs just because its old line survives."""
    _legacy(capture_index.NEWS, [{"ingest_ts": "20260820T060000Z", "source": "legacy"}])
    capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z", "source": "landed"})
    got = capture_index.entries(capture_index.NEWS)
    assert len(got) == 1
    assert got[0]["source"] == "landed", "the landed copy should win — it is the one a re-run updates"


def test_a_legacy_row_without_an_ingest_ts_is_still_kept():
    """Older rows are not guaranteed to carry every field. Dropping one silently would be the
    same class of quiet loss, so the fallback key is captured_at, then the row itself."""
    _legacy(capture_index.SNAPSHOT, [{"captured_at": "2026-08-05T03:20:00+00:00", "n_players": 577}])
    assert [r["n_players"] for r in capture_index.entries(capture_index.SNAPSHOT)] == [577]


# --- it lands wherever the raw zone is configured -------------------------------------------- #
def test_the_index_entry_is_a_normal_landed_object(tmp_path):
    locator = capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z"})
    assert "source=_index" in locator and "endpoint=news" in locator
    assert landing.exists(locator)


def test_it_follows_the_backend_rather_than_the_filesystem():
    """The whole point: on a scheduler the raw zone is S3, and the index has to go with it."""
    from fpledge.ingest.landing import S3Backend
    from tests.test_landing import _FakeS3

    fake = _FakeS3()
    landing.configure(S3Backend("bkt", "raw", client=fake))
    locator = capture_index.record(capture_index.NEWS, {"ingest_ts": "20260820T060000Z", "n": 1})
    assert locator.startswith("s3://bkt/raw/source=_index/endpoint=news/")
    assert [r["n"] for r in capture_index.entries(capture_index.NEWS)] == [1]
