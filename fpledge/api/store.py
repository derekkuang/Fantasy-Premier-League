"""Serving store: the artifacts the API reads, on local disk or S3.

A precompute or a capture writes; the API only ever reads. That split is what keeps requests
instant and cost flat — no endpoint fits a model or touches a feed.

WHY THIS GREW A BACKEND. The captures moved to durable storage so they could run on a scheduler
instead of one laptop, and the serving artifacts have to follow: a capture running in Lambda
writes `news.json` to a filesystem that is discarded seconds later, so the page it feeds would
never update. Same switch as the raw zone, different variable — `FPLEDGE_SERVING_URI`.

MUTABLE, UNLIKE THE RAW ZONE, which is why this is its own module rather than a reuse of
`ingest.landing`. Raw objects are immutable and partitioned by ingest time; a serving artifact is
overwritten every precompute and addressed by a flat, stable name. Sharing a layer between
"never changes" and "always changes" would mean one set of guarantees pretending to be two.

READS ARE CACHED, and they have to be. Against S3 an uncached read is a network round trip on
every request to every endpoint, which is both slow and billed per call. A short TTL keeps the
API fast while staying far fresher than the frontend's own ISR window (5-15 minutes), so the
cache never becomes the reason a page is stale.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .. import config

S3_SCHEME = "s3://"

# Short enough that a capture's output appears within a minute; long enough that a burst of
# requests costs one S3 GET rather than hundreds. The frontend revalidates on 5-15 minutes, so
# this is never the binding constraint on freshness.
CACHE_TTL_S = float(os.environ.get("FPLEDGE_SERVING_CACHE_TTL", "60"))

_cache: dict[str, tuple[float, dict | None]] = {}
_cache_lock = threading.Lock()


class ServingError(RuntimeError):
    pass


def serving_uri() -> str:
    """`s3://bucket/prefix` when configured, else empty (local disk)."""
    return (os.environ.get("FPLEDGE_SERVING_URI", "") or getattr(config, "SERVING_URI", "")).strip()


def serving_dir() -> Path:
    return Path(os.environ.get("FPLEDGE_SERVING_DIR", config.DATA_DIR / "serving"))


def _s3():
    uri = serving_uri()
    bucket, _, prefix = uri[len(S3_SCHEME):].partition("/")
    if not bucket:
        raise ServingError(f"FPLEDGE_SERVING_URI is malformed: {uri!r}")
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ServingError('S3 serving is configured but boto3 is missing — pip install -e ".[aws]"'
                           ) from exc
    return boto3.client("s3"), bucket, prefix.strip("/")


def _key(name: str, prefix: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _cache_key(name: str) -> str:
    """Cache on WHERE as well as what.

    Keying on the artifact name alone is wrong and quietly so: `gw1.json` in one location and
    `gw1.json` in another are different objects, and a name-only key hands the first one's
    contents to a reader pointed at the second. It shows up first in tests, where every case
    gets its own `FPLEDGE_SERVING_DIR` — but the same hole exists in production the moment the
    serving URI is repointed, which is exactly what the S3 cutover does.
    """
    return f"{serving_uri() or serving_dir()}::{name}"


def invalidate(name: str | None = None) -> None:
    """Drop cached reads. A writer calls this so its own process sees its write immediately."""
    with _cache_lock:
        if name is None:
            _cache.clear()
        else:
            _cache.pop(_cache_key(name), None)


# --- artifacts ------------------------------------------------------------------------------ #
def write_artifact(name: str, payload: dict) -> str:
    """Write one serving artifact; return its locator.

    Local writes go through a temp file and `os.replace`, so a reader never sees a half-written
    artifact. S3 `put_object` is already atomic per key — a GET returns the old object or the new
    one, never a mixture — so no equivalent dance is needed there.
    """
    uri = serving_uri()
    body = json.dumps(payload, separators=(",", ":"))
    if uri.startswith(S3_SCHEME):
        client, bucket, prefix = _s3()
        key = _key(name, prefix)
        client.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                          ContentType="application/json")
        locator = f"{S3_SCHEME}{bucket}/{key}"
    else:
        d = serving_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / name
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(body)
        os.replace(tmp, path)
        locator = str(path)
    invalidate(name)     # this process must not serve its own stale copy
    return locator


def _read_uncached(name: str) -> dict | None:
    uri = serving_uri()
    if uri.startswith(S3_SCHEME):
        client, bucket, prefix = _s3()
        try:
            obj = client.get_object(Bucket=bucket, Key=_key(name, prefix))
        except Exception:  # noqa: BLE001 — any failure to fetch is "not available"
            return None
        return json.loads(obj["Body"].read().decode("utf-8"))
    path = serving_dir() / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def read_artifact(name: str) -> dict | None:
    """Read a serving artifact, or None if it has not been produced yet. TTL-cached.

    A missing artifact is cached too. Otherwise a request for a gameweek that was never
    precomputed re-hits S3 on every single call — the miss path is exactly the one that would
    get hammered, since it is what a crawler or a stale link produces.
    """
    key = _cache_key(name)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
    value = _read_uncached(name)
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def list_artifacts() -> list[str]:
    """Every artifact name present, unordered."""
    uri = serving_uri()
    if uri.startswith(S3_SCHEME):
        client, bucket, prefix = _s3()
        pages = client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=f"{prefix}/" if prefix else "")
        out = []
        for page in pages:
            for obj in page.get("Contents") or []:
                out.append(obj["Key"].rsplit("/", 1)[-1])
        return out
    d = serving_dir()
    return [p.name for p in d.iterdir() if p.is_file()] if d.exists() else []


# --- gameweek artifacts (the original surface, unchanged for callers) ------------------------ #
def write_gw(gw: int, payload: dict) -> str:
    """Atomically write the serving artifact for a gameweek; return its locator."""
    return write_artifact(f"gw{gw}.json", payload)


def read_gw(gw: int) -> dict | None:
    """Read the serving artifact for a gameweek, or None if it hasn't been precomputed."""
    return read_artifact(f"gw{gw}.json")


def available_gws() -> list[int]:
    """Gameweeks that have a precomputed artifact, ascending."""
    gws = []
    for name in list_artifacts():
        stem = name.removesuffix(".json")
        if stem.startswith("gw"):
            try:
                gws.append(int(stem[2:]))
            except ValueError:
                continue
    return sorted(gws)
