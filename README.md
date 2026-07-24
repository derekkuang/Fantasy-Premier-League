# fpledge — an FPL-first football prediction system

**One Dixon-Coles match engine → two products.** A single per-fixture scoreline
probability matrix feeds (1) **Fantasy Premier League** expected points, captaincy,
transfers and a squad optimiser, and (2) an **honest betting benchmark** that
measures calibration and closing-line value rather than pretending to beat the market.

> **Honest scope (read this first).** EPL match markets are among the most efficient
> in the world. This project does **not** claim to beat the bookmaker's closing line —
> and it proves that claim would be false by measuring it. The **real, defensible edge
> is in FPL**, a game against millions of casual humans rather than an efficient price.

| Output | What it is | Honest status |
|---|---|---|
| **FPL** xP · captain · transfers · optimiser | Decisions vs the human field | **Genuine, modest edge** (target: strong overall rank + mini-league wins) |
| **Betting** 1X2 · BTTS · O/U · correct score | Model probs vs the **de-vigged** market | **Calibration / CLV benchmark, not a profit tool** — expected CLV ≈ 0 |

---

## Why this repo is more than "another football model"

The topic is common; the **engineering discipline** is the point:

- **Point-in-time, no-leakage feature engineering.** Every feature for a fixture at
  time *T* uses only rows with `kickoff < T`. It is *enforced*, not hoped for — see
  [`features/pointintime.py`](fpledge/features/pointintime.py) and the flagship guard
  test [`tests/test_no_leakage.py`](tests/test_no_leakage.py).
- **Walk-forward backtesting** (never shuffled CV) scored with **log-loss, Brier and
  calibration curves** — outputs are treated as probabilities to be *calibrated*, not
  accuracy to be maxed. See [`eval/`](fpledge/eval/).
- **Closing-line value (CLV) as the betting north-star**, with correct **de-vigging**
  (proportional + Shin) so we never compare a raw model prob to a vig-inflated price —
  the classic mistake that manufactures phantom edge. See [`betting/odds.py`](fpledge/betting/odds.py).
- **One shared engine** ([`models/match_engine.py`](fpledge/models/match_engine.py)):
  every market and the FPL clean-sheet probability = `P(opponent scores 0)` are sums
  over the same scoreline matrix.
- **Correct, current rules:** the 2025/26 **Defensive Contribution** point is modelled
  (DEF 10+ CBIT; MID/FWD 12+ CBIRT) — [`scoring.py`](fpledge/scoring.py).

## Architecture

```
ingest ─► immutable raw (timestamped) ─► point-in-time features (DuckDB ASOF)
      ─► Dixon-Coles engine ─► scoreline matrix
      ─► { betting: de-vig + CLV benchmark ,  FPL: xP ─► captain/transfer/optimiser }
      ─► walk-forward backtest (log-loss · Brier · calibration · CLV) ─► MLflow
```

## Quickstart

```bash
make setup          # venv + editable install (heavy deps: duckdb, penaltyblog, ...)
make test           # 21 tests; the core needs only pytest
make backtest       # walk-forward demo (synthetic until data is pulled)
make pull           # land bootstrap-static + fixtures into data/raw/
```

The **core numeric modules are stdlib-only**, so `make test` passes with nothing but
`pytest` — no need to install the full stack to see the discipline work.

## Repo layout

```
fpledge/
  ingest/       FPL API client + immutable timestamped raw landing + xG scraping stub
  storage/      DuckDB schema (write-once prediction tables tagged by model_ver+run_ts)
  features/     pointintime.py (as-of primitives + leakage guard) · build.py (DuckDB)
  models/       match_engine.py · minutes.py · xpoints.py · optimizer.py (PuLP)
  betting/      odds.py (de-vig + CLV)          eval/  metrics.py · backtest.py
  scoring.py    FPL 2025/26 points (incl Defensive Contribution)   config.py
tests/          scoring · odds · match_engine · no_leakage (flagship)
scripts/        pull_data.py · run_backtest.py
```

## Roadmap

- **Phase 0 — data plumbing:** land FPL API + Understat xG + vaastav history into
  DuckDB; build & **test** the FPL↔Understat id map.
- **Phase 1 — modelling (backs the ML story):** point-in-time features → Dixon-Coles →
  minutes model → LightGBM goal/assist shares → xP; walk-forward backtest to MLflow;
  produce a **baseline-vs-improved** table and **calibration diagrams**.
- **Phase 2 — thin AWS slice (ops story):** EventBridge → Lambda/Fargate → S3 →
  CloudWatch dashboard + retrain gate; Terraform + GitHub Actions OIDC.
- **Phase 3 — FPL edge levers:** price-change model, near-deadline team-news ingest,
  effective-ownership / expected-**rank** objective, chip-timing Monte-Carlo.

## Solo-realistic vs syndicate-required (so nothing is over-claimed)

Beating the EPL closing line at scale needs sub-hour lineup feeds, proprietary xG,
and automated multi-book execution — **syndicate territory, out of scope**. What a
solo builder *can* honestly do, and what this repo targets: a well-calibrated model,
a rigorous CLV null-result on 1X2, and a real, repeatable **FPL** edge over the field.

---

*Results section — to be filled after Phase 1 (calibration diagram, walk-forward
metric curve, honest CLV distribution, live FPL rank).*
