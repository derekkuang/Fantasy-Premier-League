"""Immutable, timestamped raw landing zone — local disk or S3, same callers.

    raw/source=fpl_api/endpoint=bootstrap/season=2025-26/gw=03/
        ingest_ts=2026-07-24T06-00-05Z/data.json.gz

Every object is stamped with ingest time and never overwritten, so the raw zone is replayable
and leakage-safe by construction. That property is the reason this module exists at all.

WHY A BACKEND AND NOT JUST A PATH. The captures collect data that cannot be bought back at any
price — the FPL API, the odds API and news feeds all serve only the present — and until now the
only copy lived on one laptop. Moving them to a scheduler in the cloud means the write path has
to reach durable storage. Callers are unchanged: `land()` still takes a payload and returns a
locator; only the locator's shape differs.

THE QUIET FAILURE THIS MODULE IS SHAPED AROUND. Locators are recorded into the index files, and
the code that read them back did `pathlib.Path(p).exists()` before opening. `Path("s3://b/k")`
is a perfectly valid relative path that does not exist, so the check returns False and the
reader skips the object — silently. After a migration, `load_corpus()` would return zero items
and `availability_map()` would return nothing, with no error anywhere and every other signal
looking healthy. So reading is routed through here too, and a locator this module cannot
interpret RAISES rather than reading as absent. A misconfiguration and an empty week must never
produce the same answer.
"""

from __future__ import annotations

import gzip
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .. import config

S3_SCHEME = "s3://"


class LandingError(RuntimeError):
    """Raised when a locator cannot be interpreted or a backend is unusable."""


def utc_stamp() -> str:
    """Filesystem-safe UTC timestamp, e.g. 2026-07-24T06-00-05Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def partition(source: str, endpoint: str, season: str, gameweek: int | None,
              ingest_ts: str) -> str:
    """The key suffix shared by both backends — one definition, so they cannot drift apart."""
    parts = [f"source={source}", f"endpoint={endpoint}", f"season={season}"]
    if gameweek is not None:
        parts.append(f"gw={int(gameweek):02d}")
    parts.append(f"ingest_ts={ingest_ts}")
    return "/".join(parts)


# --- backends ------------------------------------------------------------------------------ #
class Backend(Protocol):
    def write(self, key: str, blob: bytes) -> str: ...
    def read(self, locator: str) -> bytes: ...
    def exists(self, locator: str) -> bool: ...
    def list_partitions(self, prefix: str) -> list[str]: ...
    def handles(self, locator: str) -> bool: ...


class LocalBackend:
    """Files under `config.RAW_DIR`. Locators are absolute filesystem paths.

    Absolute rather than relative on purpose: the locator is written into an index that outlives
    the working directory the capture ran from, and a relative path resolved against the wrong
    cwd is the same silent-miss this module exists to prevent.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else config.RAW_DIR

    def handles(self, locator: str) -> bool:
        return not locator.startswith(S3_SCHEME)

    def write(self, key: str, blob: bytes) -> str:
        fp = self.root / key
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(blob)
        return str(fp.resolve())

    def read(self, locator: str) -> bytes:
        return Path(locator).read_bytes()

    def exists(self, locator: str) -> bool:
        return Path(locator).exists()

    def list_partitions(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        # `**` may match zero directories, so this finds both season-level objects
        # (ingest_ts=... directly under the prefix) and gw-partitioned ones (gw=NN/ingest_ts=...).
        # It MUST stay recursive to mirror S3's prefix scan: the single-level version answered
        # "nothing landed" on disk for objects the cloud run could see — a local/S3 divergence
        # in the one function whose docstring says the backends cannot be allowed to drift.
        return sorted(str(p.resolve()) for p in base.glob("**/ingest_ts=*/data.json.gz"))


class S3Backend:
    """Objects under `s3://{bucket}/{prefix}`. Locators are full `s3://` URIs.

    The boto3 client is injected rather than constructed here so the whole path is testable with
    a fake — no credentials, no network, no moto. A storage layer that can only be exercised
    against real infrastructure is one that gets tested once, by hand, and then not again.
    """

    def __init__(self, bucket: str, prefix: str = "", client=None):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - environment-dependent
                raise LandingError(
                    "S3 landing is configured but boto3 is not installed — "
                    'install it with `pip install -e ".[aws]"`'
                ) from exc
            self._client = boto3.client("s3")
        return self._client

    def handles(self, locator: str) -> bool:
        return locator.startswith(S3_SCHEME)

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def _uri(self, key: str) -> str:
        return f"{S3_SCHEME}{self.bucket}/{key}"

    @staticmethod
    def _split(locator: str) -> tuple[str, str]:
        bucket, _, key = locator[len(S3_SCHEME):].partition("/")
        if not bucket or not key:
            raise LandingError(f"malformed S3 locator: {locator!r}")
        return bucket, key

    def write(self, key: str, blob: bytes) -> str:
        full = self._key(key)
        self.client.put_object(Bucket=self.bucket, Key=full, Body=blob)
        return self._uri(full)

    def read(self, locator: str) -> bytes:
        bucket, key = self._split(locator)
        return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def exists(self, locator: str) -> bool:
        bucket, key = self._split(locator)
        try:
            self.client.head_object(Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001 — any failure to confirm is "cannot confirm"
            return False
        return True

    def list_partitions(self, prefix: str) -> list[str]:
        full = self._key(prefix).rstrip("/") + "/"
        paginator = self.client.get_paginator("list_objects_v2")
        out = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full):
            for obj in page.get("Contents") or []:
                if obj["Key"].endswith("/data.json.gz"):
                    out.append(self._uri(obj["Key"]))
        # Lexicographic == chronological, because ingest_ts is a zero-padded UTC stamp.
        return sorted(out)


# --- backend selection --------------------------------------------------------------------- #
_backend: Backend | None = None


def configure(backend: Backend | None) -> None:
    """Install a backend explicitly. `None` restores selection from config."""
    global _backend
    _backend = backend


def backend() -> Backend:
    """The configured write backend: S3 when `FPLEDGE_RAW_URI` is set, local disk otherwise."""
    global _backend
    if _backend is not None:
        return _backend
    uri = (getattr(config, "RAW_URI", "") or "").strip()
    if uri.startswith(S3_SCHEME):
        bucket, _, prefix = uri[len(S3_SCHEME):].partition("/")
        if not bucket:
            raise LandingError(f"FPLEDGE_RAW_URI is malformed: {uri!r}")
        _backend = S3Backend(bucket, prefix)
    else:
        _backend = LocalBackend()
    return _backend


def _reader_for(locator: str) -> Backend:
    """The backend that can interpret this locator — never a silent fallback.

    A locator whose scheme nothing handles is a CONFIGURATION error and is raised as one. The
    alternative, treating it as absent, is what turns a missing dependency into an empty page.
    """
    if not locator:
        raise LandingError("empty locator")
    active = backend()
    if active.handles(locator):
        return active
    if locator.startswith(S3_SCHEME):
        raise LandingError(
            f"{locator} is an S3 object but landing is configured for local disk. Set "
            "FPLEDGE_RAW_URI to the bucket, or this data reads as missing rather than remote."
        )
    return LocalBackend()


# --- the public surface -------------------------------------------------------------------- #
def land(
    payload,
    source: str,
    endpoint: str,
    season: str | None = None,
    gameweek: int | None = None,
    ingest_ts: str | None = None,
) -> str:
    """Write `payload` (JSON-serialisable) to the partitioned raw zone; return its locator.

    Returns a `str` rather than a `Path` because the locator may be an `s3://` URI. Callers
    already recorded `str(path)` into their indexes, so old index rows keep resolving.
    """
    key = partition(source, endpoint, season or config.SEASON, gameweek,
                    ingest_ts or utc_stamp()) + "/data.json.gz"
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(payload).encode("utf-8"))
    return backend().write(key, buf.getvalue())


def read_json(locator: str):
    """Parse a landed object. Raises rather than returning None — see the module docstring."""
    return json.loads(gzip.decompress(_reader_for(locator).read(locator)).decode("utf-8"))


def exists(locator: str) -> bool:
    """Whether a landed object is there. Raises on a locator nothing can interpret."""
    return _reader_for(locator).exists(locator)


def list_partitions(source: str, endpoint: str, season: str | None = None,
                    gameweek: int | None = None) -> list[str]:
    """Every landed object for an endpoint, oldest first.

    `gameweek` narrows the listing to one gw partition (the layout `land(gameweek=...)`
    writes). It is a filter, not a correctness requirement: a season-wide listing returns
    gw-partitioned objects too, on both backends.
    """
    season = season or config.SEASON
    prefix = f"source={source}/endpoint={endpoint}/season={season}"
    if gameweek is not None:
        prefix += f"/gw={int(gameweek):02d}"
    return backend().list_partitions(prefix)


_GW_SEGMENT = re.compile(r"/gw=(\d+)/")


def gameweek_of(locator: str) -> int | None:
    """The gw=NN partition a locator sits under, or None for a season-level object.

    One definition, next to `partition()` which writes the segment, so a reader deriving
    gameweeks from a listing cannot drift from the writer's layout.
    """
    m = _GW_SEGMENT.search(locator)
    return int(m.group(1)) if m else None
