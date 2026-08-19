.PHONY: setup test lint ci web-check docker-check pull backtest precompute serve eval-brief snapshot capture-props capture-news eval-news simulate-season model-card clean

# Full setup: venv + editable install with dev extras (heavy deps).
setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev,api]"

# Phase 0 (API): precompute the serving artifact, then serve it.
# GW/HORIZON override the defaults, e.g. `make precompute GW=2 HORIZON=6`.
GW ?= 1
HORIZON ?= 8
precompute:
	.venv/bin/python scripts/precompute.py $(GW) $(HORIZON)

serve:
	.venv/bin/python -m uvicorn fpledge.api.main:app --reload

# Run the test suite (the stdlib-only core needs only pytest).
test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/python -m ruff check fpledge tests scripts

# Everything CI runs, in the same order, so a red pipeline can be reproduced without pushing.
# Kept as literal commands rather than a call out to `act`: the point is that this is runnable
# on a laptop with nothing installed but the venv and node.
ci: lint test web-check
	@echo "── all CI checks passed ──"

web-check:
	cd web && npx tsc --noEmit && npm run lint && npm run build

# Build the container and prove it SERVES, not just that it builds. libgomp (CBC's runtime
# dependency, which PuLP shells out to for the optimiser) is the reason: without it the image
# builds cleanly and fails only when someone asks for an optimal squad.
docker-check:
	docker build -t fpledge-api:local .
	docker run -d --name fpledge-check -p 8000:8000 fpledge-api:local
	@for i in $$(seq 1 30); do \
	  curl -fsS http://127.0.0.1:8000/health && echo "" && break || sleep 1; \
	done; \
	status=$$?; docker rm -f fpledge-check >/dev/null; exit $$status

# Pull + land core FPL data into data/raw/.
pull:
	.venv/bin/python scripts/pull_data.py

# Walk-forward backtest (synthetic demo until DuckDB is populated).
backtest:
	.venv/bin/python scripts/run_backtest.py

# Capture FPL's pre-deadline state. Run weekly from 2026-08-21; the data cannot be
# reconstructed later (see docs/HANDOFF.md §17). WINDOW=12 hours by default.
snapshot:
	.venv/bin/python scripts/snapshot.py --if-near-deadline $(if $(WINDOW),--window $(WINDOW))

# Capture anytime-goalscorer prices before the deadline. Weekly, from 2026-08-21, alongside
# `snapshot`. Free tier: ~10 credits/gameweek against 500/month. Needs ODDS_API_KEY.
# Run `capture-props ARGS=--list-markets` ONCE first to confirm the market key.
capture-props:
	.venv/bin/python scripts/capture_props.py --if-near-deadline $(if $(WINDOW),--window $(WINDOW)) $(ARGS)

# Capture club news feeds. DAILY (or more often) — unlike snapshot/props these are a rolling
# window and older items fall off permanently, so a weekly run misses midweek press conferences.
capture-news:
	.venv/bin/python scripts/capture_news.py $(ARGS)

# Score the news extractor against FPL's own availability field. No API key needed.
eval-news:
	.venv/bin/python scripts/eval_news.py $(ARGS)

# Play a whole season on each projection and count the points — the first measurement of
# DECISIONS rather than ranking. Slow (a walk-forward plus a simulation per policy).
simulate-season:
	.venv/bin/python scripts/simulate_season.py $(SEASON)

# Regenerate the measured accuracy the /model page reads. Slow (full walk-forward).
model-card:
	.venv/bin/python scripts/build_model_card.py $(SEASON)

# Measure the briefing guard. Default is the injection pass: corrupt briefings the guard
# passed and report recall — no API key, no network. Add LIVE=1 to also generate for real.
LIVE ?=
eval-brief:
	.venv/bin/python scripts/eval_brief.py $(if $(LIVE),--live) $(EVAL_ARGS)

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info
