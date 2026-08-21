"""Lambda entrypoints for the capture jobs — the same scripts, driven in-process.

WHY THIS EXISTS. The captures collect data that cannot be bought back at any price, and until
now they ran only where a laptop happened to be awake. launchd narrowed that risk (it runs
missed jobs on wake); it cannot remove it — a machine that is shut down through a deadline
window still loses that gameweek forever. A scheduler in the cloud can.

THE HANDLERS WRAP `main(argv)`, NOT A COPY OF IT. Each capture script's `main` now takes an
explicit argv, so the Lambda drives the identical code path that runs locally — same gates,
same index writes, same output. A parallel "cloud version" of a capture would drift from the
tested one within a month, and the divergence would be discovered by losing a week of data.

The event can carry {"force": true} to skip the near-deadline gate — that is how the deployed
function is smoke-tested without waiting for a deadline window to open.

ENVIRONMENT CONTRACT (set on the function, not defaulted here — a capture writing to the
wrong place should fail loudly, not guess):
    FPLEDGE_RAW_URI      s3://.../raw       where captures and their index land
    FPLEDGE_SERVING_URI  s3://.../serving   where capture_news writes the digest the API reads
"""

from __future__ import annotations

import os


def _require_s3() -> None:
    # A capture that silently writes to the Lambda's own filesystem reports success and loses
    # everything — /tmp dies with the execution environment. Refuse to run half-configured.
    if not (os.environ.get("FPLEDGE_RAW_URI") or "").startswith("s3://"):
        raise RuntimeError("FPLEDGE_RAW_URI is not an s3:// URI — this capture would write to "
                           "the Lambda's ephemeral disk and be discarded on exit")


def snapshot_handler(event, context):
    """Pre-deadline FPL state. Scheduled frequently; self-gates to the deadline window."""
    _require_s3()
    from scripts.snapshot import main

    argv = [] if (event or {}).get("force") else ["--if-near-deadline"]
    main(argv)
    return {"ok": True, "forced": bool((event or {}).get("force"))}


def props_handler(event, context):
    """Anytime-goalscorer prices. Scheduled frequently; self-gates to the deadline window,
    which is also the credit budget: ~27 of every 28 firings exit before touching the odds API."""
    _require_s3()
    if not os.environ.get("ODDS_API_KEY"):
        # Without the key the script exits 2 with a clear message — but on a scheduler a missing
        # env var is a deployment mistake, not a runtime condition, and deserves the alarm.
        raise RuntimeError("ODDS_API_KEY is not set on this function")
    from scripts.capture_props import main

    argv = [] if (event or {}).get("force") else ["--if-near-deadline"]
    main(argv)
    return {"ok": True, "forced": bool((event or {}).get("force"))}


def news_handler(event, context):
    """Club news feeds, all sources. Also rebuilds the serving digest the live API reads."""
    _require_s3()
    if not (os.environ.get("FPLEDGE_SERVING_URI") or "").startswith("s3://"):
        raise RuntimeError("FPLEDGE_SERVING_URI is not an s3:// URI — the digest would be "
                           "written to ephemeral disk and the live /news would never update")
    from scripts.capture_news import main

    main([])
    return {"ok": True}
