#!/usr/bin/env bash
# Build the Lambda deployment zip for the serving API.
#
# WHY A SCRIPT. A deployment package assembled by hand is one that gets assembled differently
# next time. Every choice below is load-bearing and none of it is obvious three months later.
#
# WHAT GOES IN: fpledge (the light half), fastapi/starlette/pydantic, mangum, anthropic.
# WHAT STAYS OUT:
#   boto3/botocore  — the Lambda runtime provides them. Bundling a second copy adds ~50MB to a
#                     package whose entire advantage over a container is being small.
#   numpy/scipy/... — the API imports NONE of them. They belong to the precompute, which runs on
#                     a schedule and writes an artifact the API only reads. Verified, not assumed:
#                     importing fpledge.api.main pulls in fastapi, starlette and pydantic only.
#   tests, __pycache__, *.dist-info — dead weight in a cold start.
#
# ARCHITECTURE. Built for arm64 (Graviton): ~20% cheaper per ms, and it matches an Apple Silicon
# dev machine so a locally-tested wheel is the deployed wheel. The Lambda function MUST be
# created with Architectures=arm64 to match — a mismatch fails at import with a manylinux error
# that reads like a missing package rather than a wrong platform.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build/lambda"
ZIP="$ROOT/build/fpledge-api.zip"
PY_VERSION="${PY_VERSION:-3.13}"
PLATFORM="${PLATFORM:-manylinux2014_aarch64}"

echo "building for python $PY_VERSION / $PLATFORM"
rm -rf "$BUILD" "$ZIP"
mkdir -p "$BUILD"

# --only-binary=:all: is deliberate. Without it pip may build a source distribution against THIS
# machine's libc and CPU, producing a package that imports fine locally and dies in Lambda.
# Generous timeout and retries, and a resumable cache. Not defensive padding: this build has
# already failed once on a read timeout partway through a wheel, which leaves a half-populated
# target directory that a naive re-run would happily zip up. `--retries` makes pip recover
# in-process, and the loop below re-attempts the whole install rather than proceeding with a
# partial one.
attempt=1
until python3 -m pip install \
      --target "$BUILD" \
      --platform "$PLATFORM" \
      --python-version "$PY_VERSION" \
      --only-binary=:all: \
      --upgrade --quiet \
      --timeout 120 --retries 10 \
      mangum fastapi anthropic; do
  if [ "$attempt" -ge 3 ]; then
    echo "FAIL: pip could not fetch the wheels after $attempt attempts." >&2
    echo "  Downloads from files.pythonhosted.org are timing out — check the network/VPN." >&2
    exit 1
  fi
  echo "  pip attempt $attempt failed; clearing the partial target and retrying" >&2
  rm -rf "$BUILD"; mkdir -p "$BUILD"
  attempt=$((attempt + 1))
done

# The application itself, minus anything that only matters in development.
rsync -a --quiet \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '*.pyo' \
  "$ROOT/fpledge" "$BUILD/"

# Trim what pip leaves behind. None of it is importable code.
find "$BUILD" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD" -type d \( -name 'tests' -o -name 'test' \) -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD" -type d -name '*.dist-info' -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$BUILD/boto3" "$BUILD/botocore" "$BUILD/bin" 2>/dev/null || true

( cd "$BUILD" && zip -qr "$ZIP" . -x '*.DS_Store' )

SIZE=$(du -h "$ZIP" | awk '{print $1}')
UNZIPPED=$(du -sh "$BUILD" | awk '{print $1}')
echo "  zip:      $ZIP  ($SIZE)"
echo "  unzipped: $UNZIPPED  (Lambda's limit is 250MB unzipped)"

# Prove the entrypoint is actually in there, rather than discovering at first invocation that
# the handler path is wrong.
#
# The listing is captured ONCE into a variable instead of being piped per check. `unzip -l | grep
# -q` looks obvious and is wrong under `set -o pipefail`: grep exits the moment it matches, unzip
# takes SIGPIPE, and the pipeline reports failure for a check that actually PASSED. It cost a
# debugging detour into a perfectly good package.
LISTING="$(unzip -l "$ZIP")"
missing=""
grep -q 'fpledge/api/lambda_handler.py' <<<"$LISTING" || missing="$missing fpledge/api/lambda_handler.py"
for required in mangum fastapi starlette pydantic anthropic; do
  grep -q " $required/" <<<"$LISTING" || missing="$missing $required"
done
if [ -n "$missing" ]; then
  echo "FAIL: missing from the package:$missing" >&2
  exit 1
fi
# boto3 must NOT be here — the runtime provides it and a second copy is dead weight.
if grep -q " botocore/" <<<"$LISTING"; then
  echo "WARNING: botocore is bundled; the Lambda runtime already provides it" >&2
fi
echo "  contents verified: handler + mangum + fastapi + starlette + pydantic + anthropic"
