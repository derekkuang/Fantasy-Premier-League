# Presence of this file at the repo root puts the root on sys.path for pytest,
# so `import fpledge` works without an editable install.

import pytest


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    """Retry backoff must never make the suite sleep. Any test exercising a repeated 5xx or
    transport failure would otherwise pay real seconds per attempt; the backoff schedule itself
    is asserted in tests/test_httpget.py by recording the sleeps, not by serving them."""
    monkeypatch.setattr("fpledge.ingest.httpget._sleep", lambda s: None)
