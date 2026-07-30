.PHONY: setup test lint pull backtest precompute serve clean

# Full setup: venv + editable install with dev extras (heavy deps).
setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev,api]"

# Phase 0 (API): precompute the serving artifact, then serve it.
# GW/HORIZON override the defaults, e.g. `make precompute GW=2 HORIZON=6`.
GW ?= 1
HORIZON ?= 5
precompute:
	.venv/bin/python scripts/precompute.py $(GW) $(HORIZON)

serve:
	.venv/bin/python -m uvicorn fpledge.api.main:app --reload

# Run the test suite (the stdlib-only core needs only pytest).
test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/python -m ruff check fpledge tests scripts

# Pull + land core FPL data into data/raw/.
pull:
	.venv/bin/python scripts/pull_data.py

# Walk-forward backtest (synthetic demo until DuckDB is populated).
backtest:
	.venv/bin/python scripts/run_backtest.py

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info
