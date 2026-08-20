# The API and the precompute worker in one image.
#
# ONE IMAGE, TWO ENTRYPOINTS, deliberately. The API itself is light — it reads a JSON artifact
# and never fits a model — while the precompute needs numpy and scipy for the Dixon-Coles fit.
# Splitting them would be tidier and is not worth a second build for a first deploy; the same
# image serves `uvicorn` and runs `scripts/precompute.py` on a schedule.
# STATUS: BUILT AND SERVING, verified in CI on 2026-08-19 (linux/amd64). The `docker` job in
# .github/workflows/ci.yml builds this image, starts it, and polls /health until it answers —
# it reported `healthy after 2s` and `{"status":"ok","available_gws":[]}`. That second field
# matters: it is an empty artifact directory answering correctly rather than raising, which is
# what lets the container come up before any data is mounted.
#
# Building it is not the same as proving it runs. libgomp below is why: it is CBC's runtime
# dependency, PuLP shells out to CBC for the squad optimiser, and without it the image builds
# perfectly and fails only when a user asks for an optimal squad. A build-only check would have
# gone green and shipped that.
#
# A local arm64 attempt failed the same day, and NOT for an architecture reason worth encoding
# here — pip resolved the correct `manylinux_2_28_aarch64` wheel and the download died on DNS
# partway through pyarrow. Network, not image. Noted so the next person who sees it does not go
# looking for a portability bug that is not there.
FROM python:3.13-slim AS base

# libgomp is CBC's runtime dependency, which PuLP shells out to for the squad optimiser. Without
# it the ILP fails only when a user asks for an optimal squad — a failure that would pass every
# smoke test and appear in production.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Source before install. A tighter version would copy pyproject.toml alone to cache the
# dependency layer, but an editable install against a half-copied package is exactly the kind of
# thing that fails once, in CI, on a machine you cannot poke at. Correct first, fast later.
COPY pyproject.toml README.md ./
COPY fpledge/ fpledge/
COPY scripts/ scripts/
RUN pip install --upgrade pip && pip install -e ".[api]" 

# The captures and the precompute all write here, and the contents are IRREPLACEABLE — the FPL
# API, the odds API and news feeds serve only the present. Mount a volume; a container layer
# would discard a season of snapshots on the next deploy.
VOLUME ["/app/data"]
ENV FPLEDGE_DATA_DIR=/app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Read-only, single-process. The advisor's rate limiter is per-process, so a second worker would
# double the ceiling (§6) — run one until quota lives in a database.
CMD ["uvicorn", "fpledge.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
