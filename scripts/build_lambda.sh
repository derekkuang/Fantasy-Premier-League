#!/usr/bin/env bash
# Build the Lambda deployment zips: the serving API, and the capture jobs.
#
# WHY A SCRIPT. A deployment package assembled by hand is one that gets assembled differently
# next time. Every choice below is load-bearing and none of it is obvious three months later.
#
# TWO PACKAGES, ONE RECIPE:
#   fpledge-api.zip       the FastAPI app behind API Gateway. fastapi/mangum/anthropic + fpledge.
#   fpledge-captures.zip  snapshot + news captures on EventBridge. requests + fpledge + scripts.
#                         No fastapi — the captures import fpledge.api.store, which is
#                         deliberately stdlib-only, and the import check below proves it stays so.
#
# WHAT STAYS OUT OF BOTH:
#   boto3/botocore  — the Lambda runtime provides them. Bundling a second copy adds ~50MB to a
#                     package whose entire advantage over a container is being small.
#   numpy/scipy/... — neither entrypoint imports them. They belong to the precompute, which runs
#                     elsewhere and writes artifacts these only read. Verified, not assumed.
#   tests, __pycache__, *.dist-info — dead weight in a cold start.
#
# ARCHITECTURE. Built for arm64 (Graviton): ~20% cheaper per ms, and it matches an Apple Silicon
# dev machine so a locally-tested wheel is the deployed wheel. The Lambda functions MUST be
# created with Architectures=arm64 to match — a mismatch fails at import with a manylinux error
# that reads like a missing package rather than a wrong platform.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_VERSION="${PY_VERSION:-3.13}"
PLATFORM="${PLATFORM:-manylinux2014_aarch64}"

pip_into() {  # pip_into <target-dir> <pkg...>
  # --only-binary=:all: is deliberate. Without it pip may build a source distribution against
  # THIS machine's libc and CPU, producing a package that imports fine locally and dies in
  # Lambda. The retry loop clears the target first: this network has dropped downloads mid-wheel,
  # and a half-populated directory must never be zipped.
  local target="$1"; shift
  local attempt=1
  until python3 -m pip install \
        --target "$target" \
        --platform "$PLATFORM" \
        --python-version "$PY_VERSION" \
        --only-binary=:all: \
        --upgrade --quiet \
        --timeout 120 --retries 10 \
        "$@"; do
    if [ "$attempt" -ge 3 ]; then
      echo "FAIL: pip could not fetch wheels after $attempt attempts (network/VPN?)." >&2
      exit 1
    fi
    echo "  pip attempt $attempt failed; clearing the partial target and retrying" >&2
    rm -rf "$target"; mkdir -p "$target"
    attempt=$((attempt + 1))
  done
}

trim() {  # remove what pip leaves behind; none of it is importable code
  local target="$1"
  find "$target" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$target" -type d \( -name 'tests' -o -name 'test' \) -prune -exec rm -rf {} + 2>/dev/null || true
  find "$target" -type d -name '*.dist-info' -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$target/boto3" "$target/botocore" "$target/bin" 2>/dev/null || true
}

verify() {  # verify <zip> <entrypoint-path> <pkg...>
  # The listing is captured ONCE instead of piped per check. `unzip -l | grep -q` looks obvious
  # and is wrong under pipefail: grep exits on match, unzip takes SIGPIPE, and the pipeline
  # reports failure for a check that PASSED. It cost a debugging detour into a good package.
  local zipfile="$1" entry="$2"; shift 2
  local listing; listing="$(unzip -l "$zipfile")"
  local missing=""
  grep -q "$entry" <<<"$listing" || missing="$missing $entry"
  local pkg
  for pkg in "$@"; do
    grep -q " $pkg/" <<<"$listing" || missing="$missing $pkg"
  done
  if [ -n "$missing" ]; then
    echo "FAIL: missing from $zipfile:$missing" >&2
    exit 1
  fi
  if grep -q " botocore/" <<<"$listing"; then
    echo "WARNING: botocore is bundled in $zipfile; the runtime already provides it" >&2
  fi
}

echo "building for python $PY_VERSION / $PLATFORM"

# ---- 1. the serving API --------------------------------------------------------------------
API_BUILD="$ROOT/build/lambda"
API_ZIP="$ROOT/build/fpledge-api.zip"
rm -rf "$API_BUILD" "$API_ZIP"; mkdir -p "$API_BUILD"
pip_into "$API_BUILD" mangum fastapi anthropic
rsync -a --quiet --exclude '__pycache__' --exclude '*.pyc' "$ROOT/fpledge" "$API_BUILD/"
trim "$API_BUILD"
( cd "$API_BUILD" && zip -qr "$API_ZIP" . -x '*.DS_Store' )
verify "$API_ZIP" 'fpledge/api/lambda_handler.py' mangum fastapi starlette pydantic anthropic
echo "  api zip:      $API_ZIP  ($(du -h "$API_ZIP" | awk '{print $1}'), $(du -sh "$API_BUILD" | awk '{print $1}') unzipped)"

# ---- 2. the captures -----------------------------------------------------------------------
CAP_BUILD="$ROOT/build/lambda-captures"
CAP_ZIP="$ROOT/build/fpledge-captures.zip"
rm -rf "$CAP_BUILD" "$CAP_ZIP"; mkdir -p "$CAP_BUILD"
pip_into "$CAP_BUILD" requests
rsync -a --quiet --exclude '__pycache__' --exclude '*.pyc' "$ROOT/fpledge" "$CAP_BUILD/"
# The capture entrypoints live in scripts/ (they are operational jobs, not library code); the
# package's scripts/__init__.py makes them importable as scripts.<name> from the zip root.
mkdir -p "$CAP_BUILD/scripts"
cp "$ROOT/scripts/__init__.py" "$ROOT/scripts/lambda_captures.py" \
   "$ROOT/scripts/snapshot.py" "$ROOT/scripts/capture_news.py" \
   "$ROOT/scripts/capture_props.py" "$CAP_BUILD/scripts/"
trim "$CAP_BUILD"
( cd "$CAP_BUILD" && zip -qr "$CAP_ZIP" . -x '*.DS_Store' )
verify "$CAP_ZIP" 'scripts/lambda_captures.py' requests fpledge
echo "  captures zip: $CAP_ZIP  ($(du -h "$CAP_ZIP" | awk '{print $1}'), $(du -sh "$CAP_BUILD" | awk '{print $1}') unzipped)"

# Prove the captures package imports WITHOUT fastapi — the digest write goes through
# fpledge.api.store, which is stdlib-only on purpose, and this is the check that keeps it so.
# If this fails, someone imported something heavy into the capture path; fix the import, don't
# add the dependency.
# The handlers import lazily, so importing only lambda_captures would prove nothing — the check
# has to load the actual capture modules, the same imports the first real invocation performs.
PYTHONPATH="$CAP_BUILD" python3 -c "
import sys
for mod in ('fastapi', 'starlette', 'pydantic', 'numpy', 'pandas', 'scipy', 'boto3'):
    sys.modules[mod] = None  # forces ImportError on any attempt to import these
import scripts.lambda_captures
import scripts.snapshot
import scripts.capture_news        # pulls fpledge.api.store — must stay stdlib-only
import scripts.capture_props
print('  capture modules import cleanly with fastapi/numpy/boto3 blocked')
"
