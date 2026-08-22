"""One retrying GET for every ingest client.

Every capture collects something that cannot be re-fetched later, and the clients' own
docstrings promised retries "before going to prod" while the captures were already running
in prod on a schedule. This module is that promise kept, in one place. Policy:

  * TRANSIENT transport failures (timeout, connection reset, truncated body) and 5xx
    responses are retried with exponential backoff — they are the failures that pass on a
    second try. Deterministic transport failures — a bad certificate, a malformed URL, a
    redirect loop — are answers, not weather: they re-raise immediately, because retrying
    them costs seconds per club per run forever and returns the identical exception;
  * every other status is returned immediately. 404, 401 and 429 each MEAN something, and
    retrying them turns a clear answer into a slow one (or, on a metered API, a paid one);
  * after the last attempt a 5xx response is RETURNED, not raised — the caller owns status
    handling and its own error type — while a transport failure re-raises the original
    requests exception for the caller to wrap into its domain error. That wrapping matters:
    the capture scripts' partial-failure handling catches domain errors, so a transport
    exception that escapes as itself crashes a whole capture with everything already fetched
    still unlanded.
  * `before_attempt` runs before EVERY attempt, first and retried alike. It exists for the
    clients' politeness throttles: a retry that skips the throttle sends extra requests to a
    host that just said it was struggling — inside the very interval the throttle promised
    to respect — which is retry amplification wearing a resilience costume.
"""

from __future__ import annotations

import random
import time

ATTEMPTS = 3
BACKOFF_S = 1.0
TRANSIENT = frozenset({500, 502, 503, 504})

# Module-level so tests can no-op the backoff; the throttles' sleeps are separate on purpose.
_sleep = time.sleep


def _is_transient(exc) -> bool:
    """Worth a retry? SSLError must be checked first: requests makes it a ConnectionError
    subclass, but a bad certificate does not heal on the second attempt."""
    import requests

    if isinstance(exc, requests.exceptions.SSLError):
        return False
    return isinstance(exc, (requests.ConnectionError, requests.Timeout,
                            requests.exceptions.ChunkedEncodingError))


def get_with_retries(session, url, *, timeout, attempts: int = ATTEMPTS,
                     backoff_s: float = BACKOFF_S, before_attempt=None, **kwargs):
    """GET with bounded retries on transient failures and 5xx. See the module docstring."""
    import requests

    attempts = max(1, attempts)
    for attempt in range(attempts):
        if attempt:
            # Exponential with jitter, so several captures retrying at once don't re-converge
            # on the endpoint that just told them it was struggling.
            _sleep(backoff_s * (2 ** (attempt - 1)) * (1.0 + random.random() * 0.25))
        if before_attempt is not None:
            before_attempt()
        try:
            resp = session.get(url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            if attempt == attempts - 1 or not _is_transient(exc):
                raise
            continue
        if resp.status_code in TRANSIENT and attempt < attempts - 1:
            continue
        return resp
    raise AssertionError("unreachable: the final attempt always returns or raises")
