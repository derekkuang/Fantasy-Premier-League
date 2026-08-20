"""The serving store: both backends, and the cache correctness the API depends on.

The store had no tests of its own — it was four functions over a path, exercised only through
the API tests. It is now a cached, two-backend read/write pair on the request path of every
endpoint, and the failure modes it can produce (a stale artifact, or worse, a DIFFERENT
location's artifact) are invisible from the outside: the endpoint returns 200 with plausible
JSON either way.
"""

from __future__ import annotations

import json

import pytest

from fpledge.api import store


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(tmp_path / "serving"))
    monkeypatch.delenv("FPLEDGE_SERVING_URI", raising=False)
    monkeypatch.setattr("fpledge.config.SERVING_URI", "")
    store.invalidate()
    yield
    store.invalidate()


# --- the basic contract --------------------------------------------------------------------- #
def test_an_artifact_round_trips():
    store.write_artifact("news.json", {"n_items": 12})
    assert store.read_artifact("news.json") == {"n_items": 12}


def test_a_missing_artifact_is_none_not_an_error():
    assert store.read_artifact("nope.json") is None
    assert store.read_gw(99) is None


def test_a_gameweek_artifact_round_trips():
    store.write_gw(3, {"gw": 3})
    assert store.read_gw(3) == {"gw": 3}
    assert store.available_gws() == [3]


def test_available_gws_is_sorted_and_ignores_other_artifacts():
    for gw in (7, 2, 11):
        store.write_gw(gw, {"gw": gw})
    store.write_artifact("news.json", {})
    assert store.available_gws() == [2, 7, 11]


def test_a_local_write_is_atomic_leaving_no_temp_file(tmp_path):
    """A reader must never see a half-written artifact, and must never trip over the scratch
    file either — `available_gws` globs the directory."""
    store.write_gw(1, {"gw": 1})
    names = store.list_artifacts()
    assert names == ["gw1.json"], f"stray file left behind: {names}"


# --- the cache ------------------------------------------------------------------------------- #
def test_a_write_is_visible_to_the_writing_process_immediately():
    """The capture writes the digest and then, in the same process, the API layer may read it.
    Without invalidation on write the writer would serve its own stale copy for a full TTL."""
    store.write_artifact("news.json", {"v": 1})
    assert store.read_artifact("news.json") == {"v": 1}
    store.write_artifact("news.json", {"v": 2})
    assert store.read_artifact("news.json") == {"v": 2}


def test_reads_are_cached_within_the_ttl(monkeypatch, tmp_path):
    """The point of the cache: a burst of requests costs one backend read, not hundreds."""
    store.write_artifact("news.json", {"v": 1})
    store.read_artifact("news.json")                      # populate

    calls = {"n": 0}
    real = store._read_uncached

    def counting(name):
        calls["n"] += 1
        return real(name)

    monkeypatch.setattr(store, "_read_uncached", counting)
    for _ in range(5):
        store.read_artifact("news.json")
    assert calls["n"] == 0, "served from cache, so the backend should not be touched at all"


def test_the_cache_is_keyed_on_location_not_just_name(tmp_path, monkeypatch):
    """THE BUG THIS EXISTS TO PREVENT.

    `gw1.json` in one location and `gw1.json` in another are different objects. Keying the cache
    on the name alone hands the first one's contents to a reader pointed at the second — a 200
    with plausible JSON from the wrong place, which no endpoint could detect. It surfaces first
    in tests, where each case gets its own serving dir, but the same hole opens in production the
    moment the serving URI is repointed. Which is exactly what the S3 cutover does.
    """
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(a))
    store.write_gw(1, {"where": "a"})
    assert store.read_gw(1) == {"where": "a"}

    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(b))
    store.write_gw(1, {"where": "b"})
    assert store.read_gw(1) == {"where": "b"}

    monkeypatch.setenv("FPLEDGE_SERVING_DIR", str(a))
    assert store.read_gw(1) == {"where": "a"}, "location A was overwritten by B's cache entry"


def test_a_missing_artifact_is_cached_too(monkeypatch):
    """The miss path is the one that gets hammered — a crawler or a stale link asking for a
    gameweek that was never precomputed. Uncached, every one of those is a live S3 GET."""
    assert store.read_gw(42) is None
    calls = {"n": 0}
    real = store._read_uncached
    monkeypatch.setattr(store, "_read_uncached",
                        lambda n: (calls.__setitem__("n", calls["n"] + 1), real(n))[1])
    assert store.read_gw(42) is None
    assert calls["n"] == 0


# --- the S3 backend --------------------------------------------------------------------------- #
def _client_error(code: str) -> Exception:
    """A botocore-shaped error: the classifier reads response["Error"]["Code"]."""
    err = Exception(code)
    err.response = {"Error": {"Code": code}}
    return err


class _FakeS3:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            # Shaped like botocore's ClientError, not a bare KeyError. The first version raised
            # KeyError, which the production classifier correctly treated as "unknown failure" —
            # so the fake was the thing lying, and a realistic one caught it immediately.
            raise _client_error("NoSuchKey")
        import io
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def get_paginator(self, _name):
        objects = self.objects

        class _Pager:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for (b, k) in sorted(objects)
                                    if b == Bucket and k.startswith(Prefix)]}
        return _Pager()


@pytest.fixture
def s3(monkeypatch):
    fake = _FakeS3()
    monkeypatch.setenv("FPLEDGE_SERVING_URI", "s3://bkt/serving")
    monkeypatch.setattr(store, "_s3", lambda: (fake, "bkt", "serving"))
    store.invalidate()
    return fake


def test_s3_artifacts_round_trip(s3):
    store.write_artifact("news.json", {"n_items": 5})
    assert store.read_artifact("news.json") == {"n_items": 5}
    assert ("bkt", "serving/news.json") in s3.objects


def test_s3_write_returns_a_uri_locator(s3):
    assert store.write_gw(1, {"gw": 1}) == "s3://bkt/serving/gw1.json"


def test_s3_available_gws_lists_from_the_bucket(s3):
    for gw in (5, 1, 3):
        store.write_gw(gw, {"gw": gw})
    store.write_artifact("news.json", {})
    assert store.available_gws() == [1, 3, 5]


def test_a_missing_s3_object_is_none_rather_than_an_exception(s3):
    """The API must 404, not 500, for a gameweek nobody has precomputed."""
    assert store.read_gw(99) is None


def test_s3_json_is_written_compactly(s3):
    store.write_artifact("news.json", {"a": 1, "b": 2})
    blob = s3.objects[("bkt", "serving/news.json")].decode()
    assert blob == '{"a":1,"b":2}', "whitespace in a serving artifact is bytes over the wire"
    assert json.loads(blob) == {"a": 1, "b": 2}


# --- transient failure is not absence -------------------------------------------------------- #
class _BrokenS3(_FakeS3):
    """Reads time out mid-body — the 1MB-artifact failure seen against real S3."""

    def get_object(self, Bucket, Key):
        raise TimeoutError("Read timed out.")


class _EmptyS3(_FakeS3):
    """The object genuinely is not there."""

    def get_object(self, Bucket, Key):
        raise _client_error("NoSuchKey")


def test_a_transient_failure_raises_rather_than_reporting_absence(monkeypatch):
    """THE BUG THIS EXISTS TO PREVENT. A timeout fetching a 1MB artifact is not the same claim as
    "this gameweek was never precomputed". Returning None turns an outage into a confident 404,
    and the body read — the slowest operation on the request path — was originally outside the
    try block entirely, so it escaped as a 500."""
    monkeypatch.setenv("FPLEDGE_SERVING_URI", "s3://bkt/serving")
    monkeypatch.setattr(store, "_s3", lambda: (_BrokenS3(), "bkt", "serving"))
    store.invalidate()
    with pytest.raises(store.ArtifactUnavailable, match="could not fetch"):
        store.read_gw(1)


def test_a_genuinely_missing_object_is_still_none(monkeypatch):
    """The other half: NoSuchKey really does mean absent, and must stay a plain 404."""
    monkeypatch.setenv("FPLEDGE_SERVING_URI", "s3://bkt/serving")
    monkeypatch.setattr(store, "_s3", lambda: (_EmptyS3(), "bkt", "serving"))
    store.invalidate()
    assert store.read_gw(1) is None


def test_a_transient_failure_is_not_cached(monkeypatch):
    """Caching a blip would serve "not precomputed" for a full TTL after it had passed."""
    monkeypatch.setenv("FPLEDGE_SERVING_URI", "s3://bkt/serving")
    broken = _BrokenS3()
    monkeypatch.setattr(store, "_s3", lambda: (broken, "bkt", "serving"))
    store.invalidate()
    with pytest.raises(store.ArtifactUnavailable):
        store.read_gw(1)

    healthy = _FakeS3()
    monkeypatch.setattr(store, "_s3", lambda: (healthy, "bkt", "serving"))
    store.write_gw(1, {"gw": 1})
    assert store.read_gw(1) == {"gw": 1}, "the failed read was cached and outlived the outage"


class _UrllibShapedError(_FakeS3):
    """An exception whose `.response` is NOT a dict — urllib3 raises these.

    The handler used to call `.get()` on it unconditionally and raised AttributeError from
    inside the except block, converting every transient failure into a different and far more
    confusing one. An error path that can itself error is worse than no error path.
    """

    def get_object(self, Bucket, Key):
        err = Exception("Read timed out.")
        err.response = "not-a-dict"
        raise err


def test_an_error_whose_response_is_not_a_dict_is_still_classified(monkeypatch):
    monkeypatch.setenv("FPLEDGE_SERVING_URI", "s3://bkt/serving")
    monkeypatch.setattr(store, "_s3", lambda: (_UrllibShapedError(), "bkt", "serving"))
    store.invalidate()
    with pytest.raises(store.ArtifactUnavailable, match="could not fetch"):
        store.read_gw(1)
