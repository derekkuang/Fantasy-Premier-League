# fpledge — Handoff

> **Read this first.** Current state as of **2026-08-03**. 39 commits, 226 tests passing,
> nothing pushed to a remote. Supersedes the status sections of `PROJECT.md`, which is now the
> historical design rationale (written 2026-07-28 at 17 commits / 72 tests) — still worth
> reading for *why* the architecture is shaped the way it is, but its "what's built" is stale.

---

## 1. Where the code is right now

**Branch `feat/match-lab-and-advisor`, 10 commits ahead of `main`.** `main` sits at `06533de`.
The project's whole history is otherwise on `main`; to keep that pattern:

```bash
git checkout main && git merge --ff-only feat/match-lab-and-advisor
```

Nothing has ever been pushed. There is no remote.

### Run it

```bash
make precompute          # writes data/serving/gw1.json (engine fit, ~2 min)
make serve               # FastAPI on :8000
cd web && npm run dev    # Next.js on :3000
.venv/bin/python -m pytest -q
```

---

## 2. What exists

### Backend (`fpledge/`)

The engine is unchanged and documented in `PROJECT.md` §2. New since that document:

| Module | What it does |
|---|---|
| `playermeta.py` | Availability (status/news/**factor**), form, price momentum, set-piece order — parsed from the bootstrap blob already being landed. Explanatory only; changes no projection. |
| `matches.py` | Per-fixture scoreline distributions. The engine was already building `MatchProbabilities` for every fixture and discarding all but one field; this serialises it. |
| `lineup.py` | Projected XI derived from the minutes model — 11 highest expected minutes in a legal shape, best of 8 real formations. |
| `brief.py` | Grounded match briefings: fact pack → LLM → **numeric guard** → deterministic template fallback. |
| `advisor/tools.py` | 5 tools over existing engine code for the squad advisor. |
| `advisor/agent.py` | The tool-use loop. Sonnet 5, effort `medium`, hard iteration cap, usage accounting. |
| `ingest/understat.py` | Tier-2 identity join + shot zones. **Fetch adapters do not currently work — see §5.** |

`models/rank.py` gained `risk_tier` / `risk_label` (ownership banded 1–5).
`models/minutes.py` gained `availability_factor`, so the serving layer can report the exact
multiplier applied rather than re-deriving it.

### API (`fpledge/api/main.py`)

```
GET /health
GET /predictions/{gw}
GET /fixtures/{gw}?horizon=
GET /matches/{gw}
GET /matches/{gw}/{match_id}     ← + both clubs' players ranked by xP
GET /differentials/{gw}?...
GET /team/{entry_id}?gw=         ← /team/0 is the sample squad
```

All read from `data/serving/gw{N}.json`. The engine is never fitted here.

### Frontend (`web/`)

Next.js 16 + React 19 + Tailwind v4. Routes: `/`, `/predictions`, `/fixtures`,
`/differentials`, `/team/[id]`, `/privacy`, `/terms`, plus `robots.ts` and `sitemap.ts`.

All three content pages have been redesigned. Pagination (25/50/100, default 50) on Predictions
and Differentials. Global footer carries the legal notices.

---

## 3. Do this next

**In order. The first item is the only one that matters until it's done.**

1. **DEPLOY.** The product has been finishable for a while and keeps growing instead. See §4
   for the blocking list — it is four config values and a Dockerfile.
2. **Match page UI.** The backend is complete and serving; there is no UI for it. Needs a
   design handoff like the other three pages got. This is the highest-value visible feature
   sitting unused.
3. **Supabase + advisor endpoint + chat UI.** Auth, quota, payments are one project — see §6.
4. Optional/parked: Tier-2 shot zones (§5), an eval harness for the briefing guard (§7), the
   one deferred animation (§10).

---

## 4. Before deploy — the blocking list

| Item | Where |
|---|---|
| `NEXT_PUBLIC_SITE_URL` | everything currently emits `http://localhost:3000` into canonical URLs, OG tags, robots, sitemap |
| Contact email | `web/src/app/privacy/page.tsx` and `terms/page.tsx`, marked `[ADD CONTACT EMAIL BEFORE DEPLOY]` |
| Governing jurisdiction | `web/src/app/terms/page.tsx` |
| `FPLEDGE_CORS_ORIGINS` | defaults to `*` |

**Preseason reality:** the GW1 deadline is **2026-08-21**. Until then the FPL API exposes no
manager squads, so every real `/team/{id}` 404s and `/team/0` is the only working demo. The
market-λ path is also dormant until books post lines (~2 weeks pre-GW1).

**Known operational trap:** the weekly precompute can silently degrade. A dropped Football-Data
season fetch prints only `warn:` and still exits 0 — `fallback_fixtures` jumps 2→4 and the fit
quietly gets worse. **Give it a non-zero exit before scheduling it.**

**Brand risk, undecided:** "FPL Edge" uses FPL's own abbreviation and the Premier League word
mark. Common among third-party tools and mitigated by the disclaimers now in the footer,
metadata and terms — but not zero-risk. A distinct name is the only way to remove it entirely.

---

## 5. Things that don't work, and why

**Live LLM path is unverified.** `brief.py` and `advisor/agent.py` have never made a real API
call — no `ANTHROPIC_API_KEY` and `anthropic` isn't installed in the venv. The template path,
the guard, retry and fallback are all tested against a stubbed client. **The first real run may
need a fix to the request shape.** Install with `pip install -e ".[llm]"`.

**Understat fetch adapters fail, for two separate reasons** (both documented at the call site
in `ingest/understat.py`):

1. `soccerdata` reaches Understat through `tls_requests`, which downloads a 10.3 MB native
   library from GitHub with `urllib.urlopen(..., timeout=15)`. On a slow link it lands
   **truncated**, and reports `OSError: Failed to download the required TLS library`. Fix:
   fetch it with curl, verify the byte count against the GitHub API's `size`, drop it in
   `tls_requests/bin/`. Already done in this venv. In a container, bake it into the image.
2. With that fixed it still fails: Understat restructured. `getMatchData/{id}` now 404s and
   match pages no longer embed `shotsData`. Needs a newer soccerdata or a hand-written scraper.

Everything pure in that module (the identity join, shot zones) is tested and depends on neither.

---

## 6. The advisor — design decisions already made

**What it is.** `suggest_transfers` computes the best single move deterministically. It cannot
express a *constraint* — "keep Haaland", "no hits", "saving for a wildcard", "not a third
Arsenal player". Supporting those in the optimiser means a new parameter per constraint,
forever; the space of things a manager says is open-ended while the space of operations is
small and fixed. That asymmetry is the whole justification.

**The model plans, the tools compute.** Every number it can report comes from `AdvisorTools`,
the same engine behind the rest of the site. Structural, not checked — it has no way to produce
an xP itself. The tools also *enforce the rules* (budget, 2/5/5/3, max 3 per club, the −4 hit)
and return refusals with reasons rather than numbers, so the model self-corrects instead of
recommending something the game rejects.

**UX split — decided.** Auto-suggestion must **not** use the agent. "What's my best transfer?"
is already answered deterministically at precompute, free and cached; running an agent to
recompute it would cost ~9¢ for something you have. So:

- **Free / precomputed, shown to everyone:** *"Best transfer: X → Y, +1.4 xP net of hit."*
- **Paid / conversational:** the follow-ups, opened by starter chips beneath it —
  `But I want to keep X` · `What if I take a hit?` · `I'm saving for a wildcard` · `Review my squad`

The chips solve the blank-page problem *and* teach what the agent is uniquely good at. A user
typing "who's good this week" into an empty box gets an expensive answer they could read free on
Predictions.

**Cost — Sonnet 5, effort `medium`, estimated not measured:** ~$0.09 per 5-turn conversation
(~$0.06 at intro pricing through 31 Aug). Levers in order: prompt caching (prefix is identical
every turn, already wired), effort, model tier. `advise()` returns `usage` and `cost_usd` per
conversation — **replace these estimates with measurements as soon as anything real runs.**

**Quota — agreed:** free **2 / gameweek**, paid **10 / gameweek**, hard iteration cap **8**
rounds (already in code). Per-gameweek not per-month, because FPL is gameweek-shaped and a
monthly quota gets burned in week one. Check quota at conversation *start*, never mid-way. The
quota is a **fuse, not a usage target** — set where one user stops being profitable, not where
usage feels "reasonable", because a quota people actually hit generates churn from your best
users.

**Auth — decided: don't build it yet, and don't build it alone.** Quota needs persistent
per-user state and the app currently has no database at all. Auth and payments are the same
project (you need real accounts to attach a subscription to), so doing auth now and payments
later means building the identity model twice. When you do it: Supabase anonymous auth → a row
for quota → upgrade to a real account at checkout. For testing with a handful of people, a
shared password or an allowlist of entry ids needs no database.

**Not wired to an endpoint.** `advise()` raises without a client rather than degrading quietly —
an endpoint that costs money per call must never look like a working feature when it isn't.

---

## 7. The LLM work, and how to talk about it

Two features, one discipline: **the model never produces a number.**

- **Briefings** achieve it by *verification* — generate, then mechanically check every number
  against the fact pack it was given, at the precision written, scoped to the facts each
  sentence cites. Fails → retry with the reason → fall back to a deterministic template.
- **The advisor** achieves it *structurally* — the model can only obtain numbers by calling a
  tool, so there is nothing to verify.

**Techniques genuinely used** (and safe to claim): schema-constrained/structured output,
grounded generation with a programmatic verification gate, evidence-attributed claims,
deterministic fallback, bounded retry with error feedback, offline batch inference, tool use /
agentic loop with an iteration ceiling and per-conversation cost accounting.

**Do not claim:** RAG (there is no retrieval — the fact pack is *context injection*: small,
structured, fully known, nothing to select), fine-tuning, or production deployment.

**The best story here** is the bug found in the guard while testing it: checking numbers against
the *whole* fact pack let "41% down the left" through, because 41 happened to be that fixture's
clean-sheet probability. A value-based check cannot separate an *invented* number from a
*misattributed* one. Fix: scope each sentence to only the facts it cites.

**Cheapest thing that would strengthen all of this:** an eval harness — run the generator over N
fixtures and log guard rejection rate, retry-success rate, fallback rate. Turns "I built a
hallucination guard" into "measured a 12% rejection rate over 200 generations". Needs an API key.

---

## 8. Where the honesty positioning lives

This matters more than any feature; it's the product's only real differentiator.

- The model does **not** beat FPL's own xP (played-only per-GW Spearman ~0.33 vs 0.59). Say so.
- `recent.ep_next` (FPL's own projection) ships in the payload and is **deliberately never
  displayed** — one xP number on the site, ours.
- Ownership is `selected_by_percent`, a *proxy* for effective ownership. The risk band inherits
  that caveat and the UI states it.
- `low_coverage` (promoted/low-data clubs) are excluded from rankings, and the exclusion is
  labelled where it bites.
- Preseason zeros (`form`, `price_moves`) must read as **"not yet"**, never as "no form".
- The briefing ships its `fact_pack` alongside the prose so a reader can check every number.

---

## 9. Conventions worth knowing

- **Design handoffs** arrive in `design_handoff_*/` (gitignored) with a README of exact
  Tailwind. Implement with utilities and `lg:` breakpoints — never the prototype's inline
  styles or `ResizeObserver`.
- **`ruff check fpledge tests scripts` is red at ~138 errors on HEAD** and always has been. All
  new files pass clean; check per-file, not repo-wide, and don't treat the baseline as a
  regression.
- **ESLint** reports 8 pre-existing problems in `captain-compare`, `predictions-table`,
  `team-dashboard`, `theme-toggle`. Not from recent work.
- **Next dev-server gotcha:** after a response-shape change the fetch cache serves stale data.
  `rm -rf` the **absolute** `web/.next` path (shell cwd drifts into `web/`), then restart.
- **Cross-language coupling:** `rank.RISK_TIERS` cut points are printed as copy by
  `web/src/lib/risk.ts` `BAND_RANGE`. A test guards the pair. Change both or neither.

---

## 10. Motion

An audit (`find-animation-opportunities`) found the app had essentially **zero** motion — one
`transition`, one skeleton pulse, no easing tokens, no `prefers-reduced-motion` handling, and
no `:active` state anywhere. Four things survived the gate; three are implemented, in
`globals.css` under the MOTION banner:

1. **Sheet enter/exit** — mobile slides from the bottom edge and returns the same way, desktop
   scales from 0.96 in place. Entry is `@starting-style` (no JS); the exit needs deferred
   unmount, which is what `lib/use-dismissable.ts` is for.
2. **Press feedback** — `.press` on rows, pills, preset cards and pager buttons. Deliberately
   near-imperceptible (0.98 / 140ms) because these are pressed constantly.
3. **Skeleton → content** — `.enter` on the team dashboard bridges the one-frame snap.

**Deliberately NOT animated**, and it should stay that way: pagination page changes, the
fixture ticker's lens switch, and filter-driven list re-renders. All three move content the
user is in the middle of reading, which hinders rather than helps. This is a dense analytics
app; the failure mode here is motion, not the lack of it.

**Deferred — the formation swap** (`team-dashboard.tsx:44 applySwap`). Swapped players teleport
between pitch and bench, and a FLIP/layout transition would show the exchange. It is the only
item needing either a motion library or a careful manual FLIP / View Transitions implementation,
so it was left for a session where the dependency decision can be made deliberately rather than
unattended. Everything else in the audit is done.
