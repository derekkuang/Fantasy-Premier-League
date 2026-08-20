"""The raw landing zone: both backends, and the migration failure it is shaped to prevent.

There were no tests here at all, which was survivable while `land()` was six lines writing to a
local path. It stops being survivable the moment the same function is the only thing standing
between an irreplaceable capture and nowhere — the FPL API, the odds API and news feeds all
serve only the present, so an object that fails to land is gone permanently.

The S3 backend is exercised through an injected fake. A storage layer that can only be tested
against real infrastructure is one that gets tested once, by hand, and then never again.
"""

from __future__ import annotations

import gzip
import io
import json

import pytest

from fpledge.ingest import landing
from fpledge.ingest.landing import LandingError, LocalBackend, S3Backend


class _FakeS3:
    """Just enough of boto3's S3 client: put/get/head/list."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(f"NoSuchKey: {Key}")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(f"404: {Key}")
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def get_paginator(self, _name):
        objects = self.objects

        class _Pager:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for (b, k) in sorted(objects) if b == Bucket
                                    and k.startswith(Prefix)]}

        return _Pager()


@pytest.fixture(autouse=True)
def _reset_backend():
    yield
    landing.configure(None)          # never leak a backend into the next test


@pytest.fixture
def local(tmp_path):
    backend = LocalBackend(tmp_path)
    landing.configure(backend)
    return backend


@pytest.fixture
def s3():
    fake = _FakeS3()
    backend = S3Backend("bkt", "raw", client=fake)
    landing.configure(backend)
    return fake


# --- the shared contract, proven identically on both backends ------------------------------- #
@pytest.mark.parametrize("which", ["local", "s3"])
def test_a_landed_payload_reads_back_identical(which, request, tmp_path):
    request.getfixturevalue(which)
    payload = {"captured_at": "2026-08-20T00:00:00Z", "items": [{"guid": "a"}, {"guid": "b"}]}
    locator = landing.land(payload, source="fpl", endpoint="bootstrap", season="2026-27")
    assert landing.read_json(locator) == payload


@pytest.mark.parametrize("which", ["local", "s3"])
def test_a_landed_object_reports_as_existing(which, request):
    request.getfixturevalue(which)
    locator = landing.land({"x": 1}, source="fpl", endpoint="bootstrap", season="2026-27")
    assert landing.exists(locator)


@pytest.mark.parametrize("which", ["local", "s3"])
def test_the_partition_layout_is_the_same_on_both(which, request):
    request.getfixturevalue(which)
    locator = landing.land({}, source="fpl", endpoint="bootstrap", season="2026-27",
                           gameweek=3, ingest_ts="2026-08-20T06-00-00Z")
    for part in ("source=fpl", "endpoint=bootstrap", "season=2026-27", "gw=03",
                 "ingest_ts=2026-08-20T06-00-00Z", "data.json.gz"):
        assert part in locator, part


@pytest.mark.parametrize("which", ["local", "s3"])
def test_captures_never_overwrite_each_other(which, request):
    """The raw zone's whole value is being a timeline. Two captures of the same endpoint on the
    same day must be two objects, or replay silently loses history."""
    request.getfixturevalue(which)
    a = landing.land({"n": 1}, source="fpl", endpoint="bootstrap", ingest_ts="2026-08-20T06-00-00Z")
    b = landing.land({"n": 2}, source="fpl", endpoint="bootstrap", ingest_ts="2026-08-20T12-00-00Z")
    assert a != b
    assert landing.read_json(a)["n"] == 1 and landing.read_json(b)["n"] == 2


@pytest.mark.parametrize("which", ["local", "s3"])
def test_partitions_list_oldest_first(which, request):
    """`latest_raw` takes the LAST entry, so the ordering is load-bearing. It works because the
    ingest stamp is zero-padded UTC, making lexicographic order chronological."""
    request.getfixturevalue(which)
    for ts in ("2026-08-20T18-00-00Z", "2026-08-20T06-00-00Z", "2026-08-20T12-00-00Z"):
        landing.land({"ts": ts}, source="fpl", endpoint="bootstrap", season="2026-27",
                     ingest_ts=ts)
    found = landing.list_partitions("fpl", "bootstrap", "2026-27")
    assert [landing.read_json(p)["ts"] for p in found] == [
        "2026-08-20T06-00-00Z", "2026-08-20T12-00-00Z", "2026-08-20T18-00-00Z"]


@pytest.mark.parametrize("which", ["local", "s3"])
def test_listing_an_endpoint_that_never_landed_is_empty_not_an_error(which, request):
    request.getfixturevalue(which)
    assert landing.list_partitions("fpl", "never_captured", "2026-27") == []


# --- THE MIGRATION BUG ---------------------------------------------------------------------- #
def test_an_s3_locator_under_a_local_backend_raises_rather_than_reading_as_absent(local):
    """THE FAILURE THIS MODULE EXISTS TO PREVENT.

    The readers used to do `pathlib.Path(p).exists()` before opening. `Path("s3://b/k")` is a
    perfectly valid RELATIVE path that does not exist, so the check returned False and the
    object was skipped — silently. After moving the raw zone to S3 with the backend still
    pointed at disk, `load_corpus()` would have returned an empty corpus and `availability_map()`
    an empty dict, with no error and every other signal looking healthy.

    A misconfiguration and an empty week must never produce the same answer."""
    with pytest.raises(LandingError, match="configured for local disk"):
        landing.exists("s3://bucket/raw/source=fpl/data.json.gz")
    with pytest.raises(LandingError, match="configured for local disk"):
        landing.read_json("s3://bucket/raw/source=fpl/data.json.gz")


def test_a_local_locator_still_reads_under_an_s3_backend(tmp_path):
    """THE CUTOVER CASE, and the one most likely to be missed.

    Flipping the captures to S3 does not rewrite the index files. From that moment every index
    holds BOTH — local absolute paths for everything captured before, `s3://` URIs after — and
    the whole history has to keep resolving or `load_corpus` quietly halves. An S3 backend must
    therefore still read a local locator, rather than treating "not mine" as "not there".
    """
    landing.configure(LocalBackend(tmp_path))
    local_locator = landing.land({"era": "before cutover"}, source="fpl", endpoint="bootstrap")

    landing.configure(S3Backend("bkt", "raw", client=_FakeS3()))
    s3_locator = landing.land({"era": "after cutover"}, source="fpl", endpoint="bootstrap")

    # Both eras readable while the S3 backend is the active one.
    assert landing.exists(local_locator) and landing.exists(s3_locator)
    assert landing.read_json(local_locator) == {"era": "before cutover"}
    assert landing.read_json(s3_locator) == {"era": "after cutover"}


def test_a_genuinely_missing_local_object_is_absent_not_an_error(local, tmp_path):
    """The other half of the same rule: a real path that is simply not there is a legitimate
    answer, and must stay distinguishable from the misconfiguration above."""
    assert landing.exists(str(tmp_path / "nope" / "data.json.gz")) is False


def test_a_missing_s3_object_is_absent_not_an_error(s3):
    assert landing.exists("s3://bkt/raw/source=fpl/endpoint=x/data.json.gz") is False


def test_an_empty_locator_raises(local):
    with pytest.raises(LandingError, match="empty locator"):
        landing.exists("")


def test_a_malformed_s3_locator_raises(s3):
    with pytest.raises(LandingError, match="malformed"):
        landing.read_json("s3://bucket-only-no-key")


# --- backend-specific properties ------------------------------------------------------------ #
def test_local_locators_are_absolute(local, tmp_path):
    """The locator is written into an index that outlives the working directory the capture ran
    from. A relative path resolved against the wrong cwd is the same silent miss."""
    locator = landing.land({}, source="fpl", endpoint="bootstrap")
    assert locator.startswith("/") and "data.json.gz" in locator


def test_s3_locators_are_full_uris_including_the_prefix(s3):
    locator = landing.land({}, source="fpl", endpoint="bootstrap", season="2026-27")
    assert locator.startswith("s3://bkt/raw/source=fpl/")


def test_the_payload_is_gzipped_on_disk(local):
    from pathlib import Path

    locator = landing.land({"hello": "world"}, source="fpl", endpoint="bootstrap")
    raw = Path(locator).read_bytes()
    assert raw[:2] == b"\x1f\x8b", "not gzip — the raw zone would balloon"
    assert json.loads(gzip.decompress(raw)) == {"hello": "world"}


def test_s3_writes_are_gzipped_bytes(s3):
    landing.land({"hello": "world"}, source="fpl", endpoint="bootstrap")
    (blob,) = list(s3.objects.values())
    assert blob[:2] == b"\x1f\x8b"
    assert json.loads(gzip.decompress(blob)) == {"hello": "world"}


def test_gzip_output_is_deterministic(local):
    """mtime is pinned to 0 so the same payload gzips to the same bytes. Without it every
    capture differs from its predecessor by a timestamp header, which defeats deduplication and
    makes any content-hash comparison useless."""
    a = landing.land({"x": 1}, source="fpl", endpoint="a", ingest_ts="2026-01-01T00-00-00Z")
    b = landing.land({"x": 1}, source="fpl", endpoint="b", ingest_ts="2026-01-01T00-00-00Z")
    from pathlib import Path
    assert Path(a).read_bytes() == Path(b).read_bytes()


# --- backend selection ---------------------------------------------------------------------- #
def test_selection_defaults_to_local_when_no_uri_is_configured(monkeypatch):
    landing.configure(None)
    monkeypatch.setattr("fpledge.config.RAW_URI", "")
    assert isinstance(landing.backend(), LocalBackend)


def test_an_s3_uri_selects_the_s3_backend(monkeypatch):
    landing.configure(None)
    monkeypatch.setattr("fpledge.config.RAW_URI", "s3://my-bucket/raw")
    chosen = landing.backend()
    assert isinstance(chosen, S3Backend)
    assert chosen.bucket == "my-bucket" and chosen.prefix == "raw"


def test_a_malformed_raw_uri_raises_at_selection_rather_than_at_first_write(monkeypatch):
    """Failing here means a bad deploy dies on startup. Failing at first write means it dies
    six hours later, mid-capture, on the one machine nobody is watching."""
    landing.configure(None)
    monkeypatch.setattr("fpledge.config.RAW_URI", "s3://")
    with pytest.raises(LandingError, match="malformed"):
        landing.backend()
