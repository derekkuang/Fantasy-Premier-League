# fpledge — Project State & Full-Stack Pivot Plan

> Handoff document. Everything built so far + the plan to turn it into a web app with real
> users. Written 2026-07 (preseason 2026/27). 17 commits, 72 tests, all local, ~$0/mo.

---

## 1. What this is

`fpledge` is a complete **Fantasy Premier League (FPL) prediction + analytics engine** in
Python. It ingests live + historical data, fits a match model, produces per-player expected
points (xP), and turns that into actionable FPL tooling (captain/transfer/differential picks,
an optimal squad, a fixture ticker, a squad-health check). It is honestly validated against a
full season, and its limits are documented rather than hidden.

**Honest headline:** the model does **not** out-predict FPL's own projection (played-only
per-GW Spearman **0.32 vs FPL's 0.56** — the public-data ceiling). The value is the *tooling*,
the *optimizer*, and the *intellectual honesty*, not raw prediction superiority.

## 2. Architecture (the pipeline)

```
ingest (FPL API + Football-Data + vaastav)  →  DuckDB (immutable, point-in-time)
  →  Dixon-Coles match engine (MLE)  →  per-fixture expected goals (λ) + clean-sheet prob
  →  structured xP per player  = minutes × goal/assist shares × λ + CS + saves + DC + bonus
  →  rank (effective ownership) · optimizer (PuLP ILP) · balance · differentials · FDR · transfers
  →  walk-forward validation harness  (scores xP vs realized points, vs FPL's own xP)
```

## 3. What's built (modules + scripts)

**Core model**
- `models/dixon_coles.py` — from-scratch Dixon-Coles MLE (numpy/scipy L-BFGS-B), time-decay +
  τ low-score correction; promoted-team prior for unknown opponents.
- `models/xpoints.py` — the xP equation: appearance + goals + assists + clean sheet + saves +
  **2025/26 defensive-contribution** (Poisson-tail) + bonus. Plus `bonus_from_returns` (a tried
  alternative).
- `models/minutes.py` — `from_recent` (recency-weighted), `apply_availability` (live injury/
  status), `from_season` (preseason).
- `models/shares.py` — `match_shares` / `rate_shares` (minutes-aware per-90 goal/assist
  attribution, normalized per team).
- `scoring.py` — FPL 2025/26 points rules (incl. defensive contribution).

**Analytics / tooling**
- `models/optimizer.py` — squad optimizer (two-level ILP: best 15 + XI + captain) + `best_xi`
  (fast formation enumeration).
- `models/rank.py` — effective ownership, differential value, `differential_captain_index`.
- `balance.py` — squad balance / health check (budget, bench viability, club concentration,
  template-vs-differential, rotation risk, captain dependence).
- `differentials.py` — high-xP low-owned finder.
- `fdr.py` — true fixture difficulty (1–5) from engine λ (attack vs clean-sheet).
- `transfers.py` — best single transfer by xP gain net of the −4 hit.
- `models/points_ml.py` — LightGBM points model (walk-forward). **Honestly worse** than the
  structured model (0.28/0.24 vs 0.32); kept as a documented experiment.

**Data / infra**
- `ingest/` — `fpl_api.py`, `footballdata.py`, `vaastav.py`, `landing.py` (immutable raw),
  `understat.py` (stub), `idmap.py`.
- `storage/duck.py` (schema), `storage/load.py`, `gw.py` (assembles a gameweek end-to-end).
- `eval/fpl_backtest.py` — the walk-forward validation harness. `eval/metrics.py`,
  `eval/backtest.py` (match-engine backtest + CLV).

**Scripts (entry points)**
- `pull_data.py`, `build_db.py`, `pull_player_history.py` — ingest.
- `build_xp.py` — ranked xP table + captains + differentials.
- `build_squad.py` — optimal squad + XI + captain + **balance report**.
- `fixture_ticker.py` — true-FDR grid for the next 5 GWs.
- `suggest_transfers.py` — best transfer net of the hit.
- `validate_xp.py` — walk-forward A/B harness. `run_backtest.py` — match-engine + betting CLV.
- `train_points_model.py` — LightGBM A/B vs structured vs FPL.

## 4. How to run

```bash
make setup                       # venv + deps (numpy scipy duckdb pulp lightgbm requests pytest)
make test                        # 72 tests (stdlib-only core needs just pytest)
python scripts/pull_data.py      # land live FPL data
python scripts/build_db.py       # load teams/players/fixtures into DuckDB
python scripts/pull_player_history.py   # last-season per-player xG/xA/DC/bonus/ownership
python scripts/build_xp.py       # ranked xP table + captains + differentials
python scripts/build_squad.py    # optimal squad + balance report
python scripts/fixture_ticker.py # true-FDR grid
python scripts/suggest_transfers.py
python scripts/validate_xp.py    # walk-forward validation (downloads vaastav)
```
Deps are in `.venv` (gitignored). Season is `2026-27` (config.py); it is preseason, so all
player inputs are last season's.

## 5. Honest results & limitations

- **Match engine:** well-calibrated (predicted λ 0.70–3.01, matches actual). Betting: **no edge**
  (model log-loss ~1.06 vs de-vigged market ~1.01; ROI CI straddles 0). Framed as a calibration
  benchmark, not a profit tool.
- **FPL xP:** played-only per-GW Spearman **0.32 (structured) vs FPL 0.56**. The one measured
  improvement was recency-weighted minutes (all-players 0.67→0.73). Recency-xG, returns-bonus,
  and LightGBM were all null-or-worse → the structured model is at the public-data ceiling.
- **Limits:** preseason (last-season inputs); new signings carry prior-club output; promoted
  teams' players excluded (no data); single-gameweek (no multi-GW/chip planning); optimizer
  benches cheap fodder (the balance check flags this).

## 6. Git history (the narrative)

17 commits, each phase followed by an adversarial review that caught real bugs tests missed
(backtest subset-comparison, a shares minutes bug, a captain xP-floor, a harness attacking-
shares bug). This review-driven history is itself a portfolio signal. Résumé bullets B1
(end-to-end + APIs/scraping + feature eng + training) and B2 (trained + validated + iterative
experiments) are satisfied; B3 (AWS/MLOps) is the remaining engineering piece.

---

## 7. THE PIVOT — full-stack web app with real users

**Concept:** an FPL manager enters their team (FPL entry id) and gets a personalized weekly
action plan — projected points, best captain, best transfer (net of hit), differentials,
fixture ticker, squad-health — updated weekly. No login needed to start.

**The honest edge** (since the model doesn't out-predict FPL): superior **tooling** (optimizer,
transfer planner, balance check), a **true fixture ticker** (real model λ, not FPL's static
FDR), and **radical honesty** (show calibration; don't claim to beat FPL) as a trust signal.

### Product / MVP screens
1. **Connect team** — enter FPL id (frictionless, shareable URL `/team/{id}`).
2. **Team dashboard** — your 15 with xP, projected GW total, best captain, top transfer.
3. **Fixture ticker** — true-FDR grid.
4. **Differentials** — low-owned, high-xP.
5. (later) Transfer planner, squad balance, accounts, notifications.

### Stack (right-sized for a solo Python dev)
- **Backend/API:** wrap `fpledge` UNCHANGED behind **FastAPI**. **Precompute** all player xP once
  per refresh (same for everyone) and store it; requests just READ + do the cheap per-user
  personalization (join their 15, run the transfer suggester). This makes reads instant and
  keeps cost flat as users grow.
- **Frontend:** **Next.js + Tailwind + shadcn/ui**, mobile-first/PWA (FPL is mobile-heavy) — the
  scalable, hireable choice. Fastest-to-validate alternative: **FastAPI + HTMX + Tailwind** to
  stay in Python and ship in days (migrate to Next.js if it takes off).
- **Serving store:** managed **Postgres (Supabase or Neon)** — `player_predictions(gw, model_ver,
  run_ts, element_id, xp, …)`, `fixtures`, `teams`. DuckDB stays for batch/analytics.
- **Auth/DB:** v1 = **no accounts** (just the FPL id). v2 = **Supabase** (Postgres + Auth + storage
  in one) — `users(id, email, fpl_entry_id, tier)`, `subscriptions`.
- **Hosting:** frontend on **Vercel**; Python engine/API on **Railway/Fly.io/Render** (or AWS
  Fargate); the weekly compute job = the already-planned AWS slice (EventBridge → Fargate →
  compute → write Postgres/S3). **This pivot REUSES the AWS/MLOps work.**
- **Payments (later):** **Stripe**, or a merchant-of-record (**Paddle / Lemon Squeezy**) so VAT/
  tax is handled for you.

### Cost (scales slowly — the expensive compute is fixed, not per-user)
- 100 users ≈ $0–10/mo (free tiers) · 1k ≈ $20–50/mo · 10k ≈ $100–300/mo. Precompute + CDN caching
  keeps reads cheap.

### Legal / risk (a first-class concern)
- **The FPL API is UNOFFICIAL** and the Premier League owns the trademarks. Real (but manageable)
  risks: being rate-limited/blocked, API changes, trademark. **Mitigations:** distinct brand
  (do NOT use "Fantasy Premier League"/PL logos; describe use only), a clear "not affiliated with
  the Premier League" disclaimer, respectful API use (don't hammer it), and precedent (many paid
  tools operate on this data → practical shutdown risk is low but non-zero).
- **Privacy (UK-GDPR):** storing emails + FPL ids = personal data → privacy policy, cookie
  consent, data deletion. v1 (no accounts) minimizes PII. Use Supabase's tooling.
- **No gambling advice:** keep betting outputs a clearly-labeled calibration benchmark; do NOT
  monetize tips. FPL side has no gambling exposure — good.

### Monetization / GTM (honest)
- **Market:** ~11M FPL players but a CROWDED tools market (Fantasy Football Hub, FPL Review,
  LiveFPL, Fantasy Football Fix) and generally LOW willingness to pay.
- **Model:** freemium — free basic xP/fixtures/dashboard; paid (~£3–5/mo or £20–30/season) for the
  optimizer, transfer planner, differentials, notifications.
- **Acquisition:** r/FantasyPL (respect self-promo rules), FPL Twitter/X, content/SEO
  ("best GW1 captain"), and the **preseason spike (July–Aug)** — the big setup window (it is
  preseason NOW — good timing).
- **Honest expectation:** for a solo builder, year 1 is realistically hundreds–low-thousands of
  users and modest revenue UNLESS the free tier goes viral. Treat it as a strong **portfolio piece
  + side income with upside**, not a guaranteed business. **The single biggest success factor: a
  viral free loop** — e.g. a shareable "your team's GW projection" card.

### Phased roadmap
- **Phase 0 (week 1): API-wrap the engine.** FastAPI: `/predictions/{gw}`, `/team/{id}`
  (personalized). Deploy the compute job + Postgres. Reuse `fpledge` unchanged.
- **Phase 1 (weeks 2–3): free MVP, no accounts.** Connect-team dashboard + fixture ticker +
  differentials. Ship it; share on r/FantasyPL for feedback.
- **Phase 2 (weeks 4–6): accounts + automation.** Supabase auth, saved teams, weekly automated
  refresh (AWS slice), mobile PWA polish.
- **Phase 3 (weeks 7+): paid tier + GTM.** Stripe/Paddle, gate premium tools, content/SEO,
  season launch.
- **DE-RISK FIRST:** ship the free connect-your-team dashboard and see if people use/share it
  **before** building accounts/payments/infra. Validate demand first.

## 8. Immediate next step

**Phase 0: FastAPI wrapper around `fpledge`** — the smallest step that turns the local engine
into something a frontend can call. Endpoints `/predictions/{gw}` (precomputed) and `/team/{id}`
(personalized). Everything else (frontend, accounts, hosting) builds on that.
