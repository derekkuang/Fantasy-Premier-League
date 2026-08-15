# fpledge

**A Fantasy Premier League prediction system, and an unusually complete record of what it can and cannot prove.**

A from-scratch Dixon-Coles match engine produces per-fixture scoreline probabilities. Those feed a structured expected-points model, a squad optimiser, and a web app that turns both into decisions a manager can act on before a deadline.

The modelling is ordinary football-analytics work. What the repository is actually *for* is the validation discipline around it — several of the findings below are negative results about this project's own claims, kept because deleting them would make the rest untrustworthy.

---

## The honest headline

**The model out-ranks FPL's own published projection, and that does not translate into a demonstrable points advantage.**

Both halves are measured, and both matter.

| | result | where |
| --- | --- | --- |
| Our per-gameweek player ranking (played-only Spearman) | **0.361 → 0.378** across four consecutive seasons | §27 |
| FPL's own projection, same metric | 0.293 → 0.313 | §16, §27 |
| Does that edge win more points over a season? | **Not demonstrably.** It replicated on ranking and failed to replicate on decisions | §24 |
| Seasons needed to prove a points edge at this effect size | **~30.** Four exist | §26 |

The ranking edge is real, replicated, and concentrated exactly where decisions get made — it is largest among the 40 most-owned players, which is roughly a manager's real consideration pool (§27). It is also small enough that a season's noise swallows it. Anyone claiming a season-level FPL edge from four seasons of backtest is claiming something the data cannot support, and this project spent §23 doing precisely that before §24 retracted it.

A related correction worth reading: this project called FPL "mostly luck" in §25 and was **wrong**. Measured on real managers across ten seasons, rank percentile correlates **r = 0.574** season-to-season, giving a **56.4% skill share** — and that is a floor (§28).

---

## What we're capturing, and why it's urgent

Three capture jobs run on a schedule. They exist for one reason: **each collects something that cannot be bought back later at any price.** Every day one doesn't run is a permanent hole.

### 1. `make snapshot` — FPL's own pre-deadline state

**Weekly, from 2026-08-21.** Records `ep_next`, `chance_of_playing_next_round`, prices and ownership *before* each deadline, stamped with when.

This project spent four months believing its model lost to FPL's projection. It hadn't. The community dataset's `xP` column is scraped *after* each gameweek and absorbs that gameweek's result through FPL's `form` average — controlling for prior form it still carries 0.430 of information about the outcome it supposedly predicts, where a genuine forecast carries 0.034 (§16). The fix is to stop depending on anyone else's scrape timing. A value this script captures is unambiguously pre-deadline because it was captured before the deadline.

It also captures the **injury half of team news for free**, which is the input to the measurement that decides whether a paid feed is worth buying (§29).

### 2. `make capture-news` — club news feeds

**Daily.** Four publisher-emitted sources per club, deduped by guid.

Perfect team news is worth **+0.168** played-only Spearman against **+0.012** for the best modelling change found anywhere in this project (§19) — team news is roughly fourteen times more valuable than better maths. FPL's own availability field covers injury richly and **rotation not at all** (4 of 60 strings), and rotation is the entire commercial case for a paid feed. Press conferences are where rotation signal originates.

Feeds are a **rolling window** — 4 to 40 items per club, older ones fall off permanently.

Measured on one capture, 2026-08-11 (recall is against FPL's own flagged players):

| source | clubs | items | mean text | names a player | recall |
| --- | --- | --- | --- | --- | --- |
| BBC per-club RSS | 20/20 | 284 | 145 | 22.5% | 0.079 |
| Guardian per-club RSS | 19/20 | 289 | 799 | 40.5% | 0.238 |
| club's own RSS | 9/20 | 215 | 1,536 | 34.9% | 0.159 |
| Premier League content API | 20/20 | 739 | 405 | 40.7% | 0.349 |
| **combined** | **20/20** | **1,527** | 591 | 36.5% | **0.508** |

Sources are **additive per club** — no publisher covers everyone, and none needs to. Brighton have no Guardian tag; eleven clubs publish no feed of their own. A publisher failing costs coverage; only a club losing *every* source is an error. (§30, §31)

### 3. `make capture-props` — anytime-goalscorer prices

**Weekly, from 2026-08-21.** Requires a free-tier `ODDS_API_KEY`.

The engine already matches the betting market's view of a *fixture* (§21), so a market feed is worth nothing for its opinion on Arsenal vs Chelsea. It is worth having for the one thing it alone carries: a market-clearing **player-level** P(scores), which is a split the engine derives rather than observes.

> **Status:** the live path is **unverified** — no API key has been used against it yet.

---

## The product

A FastAPI layer reads precomputed JSON artifacts, so requests are instant and cost stays flat as users grow. A Next.js 16 / React 19 front end sits on top.

```text
GET  /predictions/{gw}      per-player xP, sortable
GET  /fixtures/{gw}         fixture ticker + true difficulty from engine λ
GET  /differentials/{gw}    high-xP, low-owned
GET  /matches/{gw}          match list · /matches/{gw}/{id} for a grounded briefing
GET  /team/{entry_id}       a manager's 15, joined to projections
GET  /news                  team-news digest (beta)
GET  /model                 the model card — including the negative results
POST /advise                the squad advisor (agent loop over model tools)
```

Two LLM surfaces, both **grounded and guarded**:

- **Match briefings** (`claude-opus-5`) — generated behind a numeric guard: every figure in the prose must appear in the data passed to it, or the briefing is rejected rather than published.
- **Squad advisor** (`claude-sonnet-5`) — a manual agent loop with a hard 8-iteration ceiling, prompt-cached system+tools prefix, and per-conversation token accounting. Its system prompt forbids stating any number a tool did not return.

---

## Quickstart

```bash
make setup          # venv + editable install
make test           # 427 tests
make lint

make pull           # land FPL bootstrap + fixtures into data/raw/
make precompute     # write data/serving/gw{N}.json
make serve          # uvicorn on :8000, interactive docs at /docs

cd web && npm install && npm run dev    # front end on :3000
```

The captures, which should be on a schedule:

```bash
make snapshot        # weekly, pre-deadline
make capture-news    # daily — feeds roll off permanently
make capture-props   # weekly, needs ODDS_API_KEY

python scripts/probe_news_feeds.py   # re-verify every news source in one command
```

Validation and analysis:

```bash
make backtest          # walk-forward
make simulate-season   # full-season simulation with real FPL rules
make eval-news         # score the news extractor against FPL's own labels
make model-card        # regenerate the published model card
```

---

## How it works

```text
ingest (FPL API · Understat · Football-Data · vaastav · news feeds)
   └─► immutable timestamped raw landing
        └─► point-in-time features (DuckDB ASOF — leakage enforced, not hoped for)
             └─► Dixon-Coles MLE (time decay, τ low-score correction, promoted-team prior)
                  └─► per-fixture scoreline matrix → λ + clean-sheet probability
                       └─► structured xP = minutes × goal/assist shares × λ
                                          + CS + saves + defensive contribution + bonus
                            ├─► optimiser (two-level PuLP ILP: best 15 → XI → captain)
                            ├─► differentials · FDR · transfers · squad balance
                            └─► walk-forward validation vs realized points and vs FPL's own xP
```

## Repo layout

```text
fpledge/
  ingest/      fpl_api · understat · vaastav · footballdata · oddsapi · newsfeed · landing
  models/      dixon_coles · xpoints · minutes · shares · optimizer · rank · saves
  features/    pointintime.py (as-of primitives + leakage guard) · build.py
  eval/        backtest · fpl_backtest · season_sim · metrics · news_eval · snapshots
  api/         main.py (FastAPI) · precompute.py · store.py
  advisor/     agent.py (tool loop) · tools.py
  brief.py     grounded match briefings   ·   scoring.py  FPL 2025/26 rules   ·   config.py
web/           Next.js 16 · React 19 · Tailwind v4
scripts/       captures, backtests, probes, precompute
tests/         427 tests
docs/          HANDOFF.md (the record) · DEPLOY.md · OPERATIONS.md · PROJECT.md (superseded)
```

---

## What makes this more than another football model

- **Point-in-time features, enforced.** Every feature for a fixture at time *T* uses only rows with `kickoff < T`, guarded by [`tests/test_no_leakage.py`](tests/test_no_leakage.py).
- **Walk-forward validation only** — never shuffled CV — scored with log-loss, Brier and calibration curves. Outputs are probabilities to be calibrated, not accuracy to be maxed.
- **A contaminated benchmark, found and documented.** §16 is the story of discovering that the number this project had been losing to was not a forecast.
- **Guards written against specific quiet failures.** A feed that returns HTTP 200 with twenty valid items from the *wrong* club; a "newest first" sort that ordered by weekday name; a hardcoded club list that reported "20/20 clubs" while counting its own wrong list. Each has a test that names the bug it prevents.
- **Negative results kept.** §24 retracts §23. §26 supersedes §25. §28 corrects §25 again. The section numbers are load-bearing.

## What is not claimed

- **No betting edge.** EPL match markets are among the most efficient anywhere. The betting code exists as a calibration and closing-line-value benchmark, with correct de-vigging (proportional + Shin) so a raw model probability is never compared to a vig-inflated price. Expected CLV ≈ 0, and that is the finding.
- **No demonstrable season-level FPL points edge.** See the headline above.
- **The news extractor is beta and says so.** Keyword cues are *routing, not classification*; FPL's own status is printed beside every player and is the authority. Nothing on that page changes a projection anywhere else in the app.

## Documentation

**[`docs/HANDOFF.md`](docs/HANDOFF.md) is the canonical record** — 31 sections covering every finding, retraction and decision, in order. Start there for anything beyond this page.

`docs/DEPLOY.md` and `docs/OPERATIONS.md` cover running it. `docs/PROJECT.md` is superseded historical design rationale, kept for context.
