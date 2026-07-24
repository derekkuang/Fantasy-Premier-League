.PHONY: setup test lint pull backtest clean

# Full setup: venv + editable install with dev extras (heavy deps).
setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

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
