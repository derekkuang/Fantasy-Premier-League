# fpledge — Handoff

> **Read this first.** State as of **2026-08-05**. 40 commits plus a large uncommitted working
> tree, **265 tests passing**, nothing pushed to a remote. `PROJECT.md` is historical design
> rationale only — its "what's built" is nine months stale.

## START HERE — the three things that matter

**1. The model beats FPL's own projection.** This reverses the positioning the project carried
for four months. The old claim came from benchmarking against a dataset column that is scraped
*after* each gameweek and contains the result. Corrected, on 2024-25 (30 gameweeks, 21,886
player-gameweeks, played-only per-GW Spearman):

| | ours | FPL (clean) | FPL (as-scraped, contaminated) |
|---|---|---|---|
| ranking | **0.374** | 0.299 | 0.568 |
| error (MAE) | **2.013** | 2.244 | — |

Full story and the decisive test in **§16**. `README.md` and `PROJECT.md` still carry the old
claim in prose — **fix those before showing anyone.**

**2. Run `make snapshot` weekly from 2026-08-21.** The first deadline of the new season. This
captures FPL's pre-deadline state — a genuinely uncontaminated `ep_next`, plus the availability
fields (`chance_of_playing_next_round`, `status`, `news`) that exist in no historical dataset.
**Neither can be reconstructed later; the FPL API serves only the present.** Every week missed
is gone. See **§17**.

**3. Deploy.** Four config values and a Dockerfile (**§4**). It has been item one since
2026-08-03 and the list of things built since is longer than the list of things blocking it.
Ship with the advisor switched off — that is a supported, tested state.

## Where things are

```bash
make precompute     # data/serving/gw1.json (engine fit, ~2 min)
make serve          # FastAPI :8000
cd web && npm run dev
make snapshot       # weekly, from 2026-08-21
make model-card     # regenerate /model's numbers (slow)
make eval-brief     # briefing-guard recall (no API key needed)
.venv/bin/python -m pytest -q
```

Branch `feat/match-lab-and-advisor`, 11 ahead of `main`, never pushed, no remote.

## Section map

| § | |
|---|---|
| 1–9 | architecture, API, frontend, deploy blockers, known-broken, advisor design, LLM work, positioning, conventions |
| 10–11 | motion; the Apple-design interface pass |
| 12 | holistic review + prioritised next steps |
| 13 | a validation coverage bug (real, fixed) |
| 14–15 | the search for edge — **partly invalidated by §16 and §18, read those first** |
| **16** | **the contaminated benchmark. The most important section.** |
| **17** | **data collection for the new season** |
| 18 | Understat unblocked; the mirrored-pitch bug; the saves experiment |
| **19** | **where the model can still improve — and why it is team news, not modelling** |
| **20** | **working that list: what each grade of team news costs, and why props are back on** |
| 21 | free routes to market data; why prediction markets do not fit |
| **22** | **props capture live; §14's blend inverted; what is actually left to explore** |

---

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
GET /model                       ← measured accuracy; 404s until build_model_card.py runs
GET /advise                      ← is the advisor configured, and why not
POST /advise                     ← one conversational turn (the only route that costs money)
```

All read from `data/serving/gw{N}.json` except `/model` (its own artifact) and `/advise`.
The engine is never fitted here.

### Frontend (`web/`)

Next.js 16 + React 19 + Tailwind v4. Routes: `/`, `/squad`, `/predictions`, `/fixtures`,
`/differentials`, `/model`, `/team/[id]`, `/privacy`, `/terms`, plus `robots.ts` and `sitemap.ts`.

- **`/squad` — build a team by hand.** Pick 15 under the real rules, or Auto-pick a legal one,
  then get the full dashboard. Needs no team id and works in preseason, which is why it is the
  landing page's primary call to action. Squads encode to a 45-char `?s=` code, so they share.
  No backend involvement: a `Prediction` is a squad row plus two booleans, and the dashboard
  already computed everything client-side.
- **`/model` — the honesty page.** Renders `GET /model`; every figure comes from the artifact,
  nothing is typed into the template, and the generation date is printed so a stale claim
  announces itself.
- **Advisor chat** sits on the team dashboard below the free precomputed transfer answer.

Pagination (25/50/100, default 50) on Predictions and Differentials. Global footer carries the
legal notices.

---

## 3. Do this next

**In order. The first item is the only one that matters until it's done.**

**See §12 for the reasoned version of this list.** The short form:

1. **DEPLOY, with the advisor switched off.** See §4 — four config values and a Dockerfile.
   No key means `/advise` reports unavailable and the UI says so; that is a supported state.
2. **Make the weekly precompute exit non-zero on a dropped fetch** (§4) before scheduling it.
3. **Get five people to build a squad at `/squad`.** Works today, preseason, no team id —
   user feedback is available now and has never been collected.
4. **Match page UI.** Backend complete since 2026-08-02, still no UI.
5. **Supabase + real quota + a live advisor key.** Auth, quota, payments are one project (§6).
4. Optional/parked: Tier-2 shot zones (§5), the one deferred animation (§10). The briefing
   eval harness (§7) is built; its live half runs the first time there's an API key —
   `make eval-brief LIVE=1`, which is also the first real exercise of the LLM path (§5).

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

**No real model call has ever been made by anything in this project.** No `ANTHROPIC_API_KEY`,
no `anthropic` package, no `ant` CLI. `brief.py` and `advisor/agent.py` are both exercised only
against scripted clients. **The first real run may need a fix to the request shape** — though
the shapes were checked against current API docs on 2026-08-03 and were correct as written.
Install with `pip install -e ".[llm]"`.

`FPLEDGE_ADVISOR_STUB=1` runs the advisor against `advisor/stub.py`: the real loop and the real
tools, with scripted prose. Every number it reports is genuine; only the sentences are canned,
and the `stub` flag is carried through to the browser and shown as a banner. It proves the loop,
the tool layer and the UI — it proves nothing about whether a model reasons well. **Never set it
in production.**

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

**The eval harness is built** — `fpledge/eval/brief_eval.py` + `scripts/eval_brief.py`
(`make eval-brief`, add `LIVE=1` to generate for real). It has two halves, because the guard
has two failure directions and only one of them is obvious:

- **Injection (offline, no API key, in CI).** Corrupts briefings the guard already passed —
  digit drift, misattribution, arithmetic on two cited values, invented precision, phantom
  evidence keys — and counts what it catches. Known-bad *by construction from the fact pack*,
  never by asking `verify`, so it's a true recall number rather than the guard grading itself.
  **Measured 2026-08-03: 400/400 = 100% recall over 80 fixtures** (template-seeded, so the
  prose is formulaic — model prose is the harder corpus and needs the live half).
- **Live generation.** First-attempt pass rate, guard rejection rate, **retry-success rate**
  (the only test of whether feeding the rejection reason back actually works), fallback rate,
  a taxonomy of *why* the guard fired, and cost per gameweek. Never run — needs a key.

**The harness is discriminating, and here is the proof.** Swap `verify` for the pack-wide check
that predated the evidence-scoping fix and recall drops **100% → 60%**: misattribution goes
80/80 → **0/80**. That is the §7 story with a number attached — "a value-based check cannot
separate an invented number from a misattributed one" is now measured, not asserted.

Three things changed in `brief.py` to make this possible, all of which matter on their own:
`narrate()` takes an optional `trace` (production passes none); the failure modes are now
distinguishable (`api_error` / `parse_error` / `refusal` / `guard_rejected` — they were one
bare `except` that made a dead API key look like a 100% hallucination rate); and a
`stop_reason == "refusal"` check runs **before** reading content, since a declined request is a
successful response with an empty `content` array that would otherwise raise and be filed as
malformed output. `model`/`effort` are now arguments, which makes the harness an A/B rig —
`--model claude-haiku-4-5` answers the 5×-cost question with data.

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

---

## 11. Interface pass (2026-08-03)

A second review, against Apple's fluid-interface and design principles rather than the motion
audit in §10. The conclusion there still holds — this app earns very little *decorative* motion
— so nothing was added for its own sake. What was missing was **response**, not animation.

**Foundation, in `globals.css`:**

| Addition | Why |
|---|---|
| `.tap` | Grows the hit area ±8px with no layout change. A 28px close button stays 28px however much padding surrounds it. |
| `:where(…):focus-visible` ring | Zero-specificity default. The search input had `outline-none` and *nothing* replacing it; rows had a background tint too faint to locate. |
| `.chrome` / `.chrome-edge` | Translucent floating chrome with a soft scroll edge instead of a 1px rule. |
| `--nav-h: 48px` | Replaces `sticky top-[43px]`, which was a measurement of whatever the nav happened to be. |
| `t-display` / `t-title` / `t-label` | **Eleven** ad-hoc tracking values became three size-specific roles across 33 sites. `.07em` and `0.07em` both appeared — the tell that they were picked per-site, not from a scale. |
| `prefers-reduced-transparency`, `prefers-contrast` | Neither was handled; the app is built on `backdrop-filter`. |

**`components/sheet.tsx` (new)** — both sheets were near-identical copies, which is how they came
to agree on what didn't matter and differ on what did. The shell now owns focus-into/restore-on-
close, a Tab trap, body scroll lock, and `role="dialog"` + `aria-modal` — none of which either
copy had.

**`lib/use-sheet-drag.ts` (new)** — drag-to-dismiss on the mobile sheet. 1:1 tracking under
pointer capture, rubber-banding upward against the sheet's own top edge, momentum projection on
release (`(v/1000)·d/(1−d)`, `d = 0.998` — the exponential-decay form, not `v²/2a`), and a live
`DOMMatrix` read on grab so a sheet caught mid-spring-back is picked up where it visually *is*.
Touch only. **The grip's `touch-action: none` is load-bearing, not cosmetic:** the panel scrolls,
so the browser may claim a vertical drag before one `pointermove` arrives, and a claimed gesture
can't be taken back.

**Press feedback** reached the pitch tokens, bench tokens, sheet swap buttons, nav links, theme
toggle and the submit button — all of which previously had `hover:` only, i.e. **nothing at all
on the touch device the view is designed for**.

**Verified:** `tsc` clean, production build clean, all five routes render, every new class and
all three `prefers-*` branches present in the compiled CSS, ESLint unchanged at the same 8
pre-existing problems (§9).

**NOT verified — no browser driver in this session:** the drag gesture itself. The physics are
right on paper and the code paths typecheck, but nobody has pulled the sheet down. Do that first.

**Knowingly left alone:**

- **`text-[8px]` in `next3-strip`, `split-cell`, `fixture-ticker`** (and a `text-[7px]` FDR digit
  in `next3-strip`). Everything else at 8–9px went to 10px; these sit in 34px grid cells that
  were tuned around them, and both carry comments showing the size was already reasoned about.
  Raising them needs a visual check, not a find-and-replace. **It is still too small.**
- **Full `rem`/Dynamic Type conversion.** Every size is px, so browser text-size settings do
  nothing. This is the largest remaining typography gap and a genuinely big refactor.
- **Desktop sheets don't anchor to their trigger** — they scale from centre with no spatial
  relationship to the row that opened them.
- **No route to the team dashboard from the nav.** Once you leave `/team/{id}` there is no way
  back to it except the home page. That's a product call, not a design one.

---

## 12. Holistic review — 2026-08-04

Written at the end of a long working session, for whoever picks this up next. It is a review of
the whole project, not of the session.

### Where this actually is

Roughly **7,400 lines of Python** and **5,700 of TypeScript**, 258 tests, eight web routes, and
one thing it has never had: **a URL**. That imbalance is the single most important fact about
the project, and it has been true for three sessions running. The handoff has said "DEPLOY" as
item 1 since 2026-08-03 and the list of things built since then is longer than the list of things
blocking deploy.

**What is genuinely good, and rarer than it looks:**

- **A real from-scratch model.** Dixon-Coles by MLE, not a library call. A full scoreline matrix
  per fixture with everything downstream derived from it. That is the substance most portfolio
  projects of this shape don't have.
- **Validated, and validated honestly.** Walk-forward, leakage-guarded, scored against FPL's own
  projection, with the losses recorded. `/model` now publishes it.
- **A discipline that shows up in the code.** The numeric guard on briefings, tools-compute-not-
  the-model in the advisor, `low_coverage` exclusions, "not yet" instead of "no form" in
  preseason. These are the same instinct applied at six different layers.
- **Review-driven history.** Multiple real bugs caught by adversarial passes and written down.

**What is weak:**

- **No users, no deploy, no feedback.** Every design decision so far is a guess validated only
  by taste. That is fine for six weeks and dangerous at three months.
- **Preseason has hidden the hardest problems.** Nothing has been tested against live team news,
  price changes, a real deadline, or a weekly precompute that must not fail. The known silent-
  degradation trap (§4) is exactly the class of bug that only appears in production.
- **One person's taste, uncorrected.** Including mine, in the last two sessions.

### The three risks that actually matter

1. **Scope growth is outrunning shipping.** This session alone added a squad builder, a model
   page, a chat feature, an eval harness and a landing-page rewrite. Every one is defensible.
   Collectively they are three more sessions of not deploying. **The next session should add no
   features.**
2. **The name.** "FPL Edge" uses FPL's abbreviation and the Premier League word mark, and it is
   now the first thing on a page explicitly designed to be shared. Free to change today.
   Expensive once a link is in circulation. Decide before deploying, not after.
3. **The advisor is a cost surface with no durable quota.** The in-process limiter (§6) dies
   with the process and a second worker doubles the ceiling. It is a fuse, not a quota. Do not
   deploy the advisor with a real key until the Supabase work lands — or ship it with the key
   absent, which is a supported state and degrades honestly.

### What I'd do next, in order

1. **Deploy, with the advisor switched off.** Four config values and a Dockerfile (§4). The
   advisor is designed to be absent — no key means `/advise` reports unavailable and the UI says
   so. Everything else is a read from a JSON file. There is no reason this isn't live.
2. **Make the weekly precompute fail loudly** before anything schedules it. A dropped
   Football-Data fetch currently prints `warn:` and exits 0 while the fit quietly degrades.
   This is the one thing that will silently rot a deployed site.
3. **Name decision.** Ten minutes, and it stops being reversible the moment someone shares a link.
4. **Get five real people to build a squad.** The builder works today, preseason, with no team
   id — which means user feedback is available *now* and doesn't need the 21 August deadline.
   This is the highest-information, lowest-cost action available and it has never been taken.
5. **Then, and only then:** the Match Lab UI (backend complete since 2026-08-02, still no UI),
   Supabase + real quota + the advisor with a key, and the eval harness's live half.

### Things that are done but unproven

Listed together because they share a failure mode — they typecheck, they render, nobody has
used them:

| Thing | Unproven part |
|---|---|
| Sheet drag-to-dismiss | The gesture itself. No browser driver in any session so far. |
| Squad builder | Verified against the real 555-player pool in Node; never driven by a human. |
| Briefing guard | 100% injection recall — but on template-seeded prose, not model prose. |
| Advisor | Loop, tools and UI proven end-to-end via the scripted stub. **No real model call has ever been made, by anything, in this project.** |
| Model card | Numbers are real and freshly measured. The page has never been read by anyone but me. |


---

## 13. A validation bug, and what it changes (2026-08-04)

**The headline claim this project has made since 2026-07-26 was measured wrong.** Found while
searching for model improvements; the search is §14, this is the correction.

### The bug

`eval/fpl_backtest._subset_metrics` compared our projection against FPL's own. It did this:

```python
if sm == sm: sp_m.append(sm)     # ours: appended whenever ours was defined
if sf == sf: sp_f.append(sf)     # FPL's: appended whenever THEIRS was defined
```

Two averages over **different sets of gameweeks**, printed side by side as a comparison. The
community dataset does not carry FPL's `xP` for every gameweek — in 2025-26 it is populated for
**4 of 30**, an empty column for the rest. So our score averaged 30 gameweeks and FPL's averaged
4, and nothing in the output said so.

The MAE comparison was worse. FPL's error was taken across *every* record, 86% of which had
`xP = 0`, so most of that average was the distance from an empty column to reality. Our model
duly "beat" it.

### What the numbers actually are

Fixed: a gameweek counts only when both predictors are defined on it, MAE is computed on exactly
those records, and the card now reports `baseline_gws` so a thin comparison declares itself.
Primary season moved to **2024-25**, which carries the baseline for 27 usable gameweeks against
2025-26's 4.

| Played-only | Was reported | Corrected (2024-25, 27 GWs, 8,113 player-GWs) |
|---|---|---|
| per-GW Spearman | 0.338 vs 0.587 | **0.373 vs 0.581** |
| MAE | 2.148 vs 2.896 — *we win* | **1.995 vs 1.733 — we lose** |
| gameweeks we're closer in | 26/30 | **2/27** |

**The ranking gap was roughly right. The error claim was inverted.** "Lower MAE but worse
ranking", and the under-dispersion story built on it, was an artifact of comparing against
zeros. FPL's projection is better than ours on *both* measures.

### What had to change because of it

- `/model` no longer says we miss by less — it says FPL wins on both, and carries a section
  explaining that an earlier version got this wrong in our own favour. An honesty page that
  quietly restates a number is worth nothing.
- `scripts/build_model_card.py` defaults to a season with a real baseline and records how wide
  the comparison is.
- `ingest/vaastav.py` normalises an `AM` position code present on ~1.2% of 2024-25 rows, which
  is not an FPL position and raised `KeyError` mid-walk-forward.

### The lesson worth keeping

The bug survived four months and multiple review passes because **both branches looked
individually reasonable** — each guards a NaN, which is correct in isolation. What was missing
was the invariant that binds them: *these two numbers must describe the same gameweeks.*
Nothing asserted it, so nothing caught it. Any future baseline comparison should carry an
explicit coverage count next to it.

---

## 14. The search for edge (2026-08-04) — what was tried, what was found

`scripts/model_search.py`. The six earlier A/Bs each changed the model and re-ran the whole
walk-forward, which is why so few of them ran. This takes a cheaper axis: cache one walk-forward's
`(gw, element, my_xp, fpl_xp, actual, pos, minutes)` records, then score any number of
transformations without refitting anything. Rules it holds to — gameweeks split in half by time
so nothing is tuned on what it is judged by, and no monotone rescaling is tested, because
Spearman is rank correlation and cannot move under one.

Run it: `python scripts/model_search.py [season]` (defaults to 2024-25; `--refresh` re-walks).

### Result 1 — our model adds nothing to FPL's. Not a little. Nothing.

Blend weights fitted on GW9–21, scored on GW23–38:

| | test Spearman |
|---|---|
| ours alone | 0.383 |
| FPL alone | **0.601** |
| best blend (0.2 ours / 0.8 FPL) | 0.586 |
| rank-blend, z-blend, every weight | all between the two, monotone |

**The optimal weight on our model is 0.0 at every position** — GK, DEF, MID and FWD alike. Any
amount of our projection mixed into FPL's makes it worse. There is no orthogonal signal to
recover; whatever we know, they already know.

### Result 2 — our ranking is mostly "who plays", not "who returns"

Conditioning on minutes collapses us and not them:

| subgroup | ours | FPL |
|---|---|---|
| under 60 min | 0.033 | 0.298 |
| 60–85 min | 0.202 | 0.505 |
| 85+ min | 0.229 | 0.516 |

Among players we already know will play a full match, our ordering is close to noise. That is
the gap in one line, and it says the minutes model is carrying almost all of our signal.

### Result 3 — goalkeepers are the worst area, and it looks fixable

Per-position played-only Spearman: **GK 0.064** (FPL 0.438), DEF 0.300, MID 0.399, FWD 0.477.

It is not a degenerate prediction — within-gameweek spread of our GK xP is 1.36, against FPL's
1.66 — so the ordering is simply wrong. A likely cause is in `fpl_backtest`/`xpoints`: saves are
modelled as `opp_lambda × 3 × (x_minutes/90)`, i.e. proportional to expected goals conceded. That
sets clean-sheet points and save points against each other almost exactly — a good defence earns
the clean sheet, a bad one earns the saves — which flattens the ranking. Real save volume tracks
*shots faced*, which is not the same as goals conceded and is not in the model. **Fixing this
needs shots-against data**, which is the Tier-2 ingest that is currently broken upstream (§5).

### Result 4 — we are under-dispersed everywhere (real, but not the explanation)

Within-position standard deviations: ours 1.46–2.00, FPL 2.17–2.65, actual 2.76–3.45. Our
projections really are too tightly clustered. It is worth knowing for anything that reads the
*value* — captaincy margins, transfer deltas — but it cannot be the ranking gap, because
stretching a distribution monotonically leaves every rank exactly where it was.

### The strategic question this raises — for a human, not for me

§8 records a deliberate decision: FPL's own `ep_next` ships in our payload and is **never
displayed**, because there should be "one projection per player, ours". That was defensible when
the two were thought to be near-par. They are not. On the thing a manager actually wants — who
to pick — FPL's number is materially better, and we ship it and hide it.

Four options, none of them obviously right:

1. **Keep showing ours.** Consistent with the model card, which now says plainly that theirs is
   better. Costs the user accuracy in exchange for an explainable number.
2. **Show theirs.** Best for the user, and raises the obvious question of what the model is for.
3. **Show both.** Most transparent; two numbers per player is a real UX cost and invites
   "which do I trust?"
4. **Rank by theirs, explain with ours.** Our decomposition is the thing FPL genuinely does not
   provide — but the two disagree, so the explanation would not add up to the headline number.

My read: option 1 remains defensible **only because** `/model` now states the loss outright, and
the product's value was already re-based on tooling rather than forecasting. But this should be a
conscious choice, re-made now with the real numbers, not inherited from when the gap was thought
to be smaller.

### What is NOT worth trying again

- Blending with FPL's projection, in any space, at any weight, globally or per position.
- Anything justified by "the model is under-dispersed" that aims to improve *ranking*.
- LightGBM on single-gameweek points (already rejected 2026-07-27; nothing here changes that).

### What might still be worth trying

- **Saves from shots faced** (Result 3). The clearest mechanical defect found, in the position
  with the biggest gap. Blocked on Tier-2 ingest.
- **Set-piece and penalty duty as a forward-looking signal.** Skipped earlier as "xG already
  includes penalty xG" — true of *historical* xG, but a player who has just taken over penalties
  has no historical penalty xG and their future rate should reflect the duty, not the past.
- **A bonus-point model from underlying BPS components** rather than a per-90 bonus rate.

---

## 15. Where the edge actually is (2026-08-04)

§14 established that no combination of our model and FPL's beats FPL's alone. This asks the
next question — *what is FPL's number made of, and can it be reconstructed?* — and the answer
redirects the whole search. Scripts: `scripts/returns_model.py`, plus the oracle probes recorded
below.

### The target was re-posed first

The 2026-07-27 LightGBM attempt predicted a player's total points. That was the wrong target,
because it bundles a problem already solved with the one that isn't:

| | ours | FPL |
|---|---|---|
| predicting **who plays at all** | **0.744** | 0.710 |
| ranking returns among players who went 85+ min | 0.229 | **0.516** |

Our minutes model is *better than FPL's*. The entire deficit is ranking returns given a player
featured. So `returns_model.py` trains only on players who featured.

### Result: historical statistics cannot reconstruct FPL's number

Point-in-time rolling per-90s of every column the model had never touched — `threat`,
`creativity`, `influence`, `ict_index`, `bps`, `saves`, `expected_goals_conceded` — plus our own
xP, on a time-split test half:

| predictor | Spearman |
|---|---|
| ours (structured xP) | 0.334 |
| **FPL xP** | **0.562** |
| `threat` per 90 alone | 0.094 |
| recent points per 90 alone (pure form) | 0.130 |
| LightGBM on all unused columns + our xP | 0.256 |
| LightGBM *with FPL's xP handed to it as a feature* | 0.504 |

Every historical rate is near-worthless alone (~0.1). The learned model is worse than our
structured one, and it is worse than FPL's number even when given that number to work with —
it destroys signal rather than adding any. **That is the third independent null for machine
learning on this problem.** Stop trying.

### Then: how much skill is even achievable?

Oracles that cheat, as an upper bound:

| predictor | Spearman |
|---|---|
| ORACLE — each player's true season points-per-appearance | 0.421 |
| ORACLE — actual minutes played in that gameweek | 0.430 |
| ORACLE — true season rate × actual minutes | 0.553 |
| ORACLE — true season rate + our fixture model (rank-blended) | 0.442 |
| **FPL xP** | **0.571** |

**FPL's projection beats an oracle that knows both the player's true season-long scoring rate
and how many minutes they actually played.** A perfect player-quality estimate combined with our
fixture model reaches 0.442 and still loses by 0.13.

So what FPL has is not player quality, and not fixture difficulty. Both of those are bounded
above by numbers we just measured, and neither gets there. It is **match-level forward-looking
information** — who is starting, who is carrying a knock, who is being rested — which no
historical statistics table contains and no model of the past can recover.

### The one caveat that cuts in our favour

**The backtest is handicapped against us and always has been.** Production applies
`availability_factor` from the live bootstrap (injury status, `chance_of_playing_next_round`).
The historical dataset carries no such column, so `validate_xp` runs a version of our model with
availability switched off — while FPL's `xP`, recorded at the time, had that information baked
in. The published 0.373 therefore understates the shipped model by an unknown amount.

This is not an excuse and must not be used as one: the direction and rough size of the gap are
not in doubt, and the fix is to measure it, not to claim it. **Highest-value validation work
available:** capture `chance_of_playing_next_round` weekly from now on so that a future backtest
can run availability-on and quantify what it is worth. That data does not exist retroactively —
if it isn't captured starting now, this question stays unanswerable for another season.

### What this means for data sources

The evidence points in one direction, and it is not "more history".

**Worth pursuing — player prop betting odds.** Anytime-goalscorer prices are precisely the
missing quantity: a market-clearing probability that a specific player scores in a specific
match, which already incorporates the team news, rotation intelligence and sharp money that the
oracle probes say we are missing. It maps directly onto the model too — the anytime-scorer
probability substitutes for `goal_share × team_lambda`, the single largest term for attackers.
It also solves the minutes problem for free, because a player expected to be benched is priced
long. Two honest obstacles: **historical prop data for backtesting is expensive and scarce**, so
this could be built forward but not validated before committing; and it is a live weekly fetch
with a real failure mode next to a precompute that already degrades silently (§4).

**Worth pursuing — expected lineups / team news.** The same information, from the other
direction and much cheaper. Starts with the free version: capture FPL's own availability fields
weekly, as above.

**Not worth pursuing.** More historical statistics in any form, finer xG decomposition,
Understat shot zones *for this purpose* (they remain interesting for the Match Lab), and any
further machine learning on single-gameweek points. Three nulls is enough.

**And the honest option that should stay on the table:** stop competing on projection. The
oracle probes suggest a genuinely good single-gameweek projection needs inputs this project is
unlikely to obtain cheaply. The tooling — true split FDR, the optimiser, squad health, the
builder — has no equivalent in FPL and does not depend on winning this fight.

---

## 16. The benchmark was contaminated. We beat FPL. (2026-08-04)

**Supersedes §13–§15's conclusion.** Everything in those sections was measured against a column
that is not a forecast. The mechanics were right; the thing being compared to was not.

### What the `xP` column actually is

Upstream's own README, verbatim:

> The `xP` column in `gws/merged_gw.csv` is sourced from the FPL bootstrap-static API's
> `ep_this` field.
>
> The scraper runs **after** each gameweek ends, so if FPL updates `ep_this` post-match, the
> scraped value will contain information that was not available to managers before the deadline.
>
> If you are training ML models on this dataset: treat `xP` as potentially post-match. Either
> apply `shift(1)` within each `element` group, or exclude the column entirely.
>
> Using it unshifted as a feature to predict same-GW `total_points` has been observed to cause
> severe lookahead bias.

And the mechanism, from the same file: **live `ep_this` correlates ~0.98 with `form`.** FPL's
projection is essentially a function of its rolling points average — and that average absorbs a
gameweek's points the moment the gameweek ends. A value scraped afterwards has therefore already
seen the result it is being asked to predict.

### Confirmed independently, before the README was found

| test | result | reading |
|---|---|---|
| `xP(N)` → points(N) | 0.571 | suspiciously high |
| `xP(N)` → points(N+1) | 0.311 | a real forecast would not fall this far |
| `xP(N-1)` → points(N) | 0.290 | what it is worth as an actual forecast |
| `xP(N)` → goals *minus* xG (pure conversion luck) | **−0.018** | it does **not** know match detail |
| `xP(N)` → yellow cards | **−0.033** | nor unforecastable events |

The last two matter: the leak is not the match, it is the **points total** entering the form
average. Precisely what the README's 0.98 correlation predicts. It also explains the result that
first raised suspicion — the unshifted column beats a hindsight oracle that knows a player's true
season scoring rate *and* their actual minutes (0.571 vs 0.553). Nothing that forecasts can do
that. Something that has already seen the answer can.

### The corrected comparison

`ingest/vaastav.py` now emits `fpl_xp_prev` (the projection as it stood before the deadline) and
`eval/fpl_backtest.py` scores against that. Three cases are kept distinct — key absent means a
legacy caller and sets `baseline_clean=False`; key `None` means a player's first gameweek and the
row is skipped rather than scored against an implicit zero; a number is used.

2024-25, 30 gameweeks, 21,886 player-gameweeks:

| played-only | ours | FPL (clean) | FPL (as-scraped) |
|---|---|---|---|
| per-GW Spearman | **0.374** | 0.299 | 0.568 *(contaminated)* |
| MAE | **2.013** | 2.244 | — |
| all-players Spearman | **0.685** | 0.608 | 0.757 *(contaminated)* |

**We beat FPL's own projection on every measure**, by about +0.075 Spearman.

### What this invalidates

- **"The model does NOT beat FPL's xP"** — the project's central positioning since 2026-07-26,
  in `PROJECT.md`, this handoff, the README and (until today) the site. It was never measured
  against a forecast.
- **§14's "our model adds nothing to FPL's"** — the optimal-blend-weight-of-zero result was
  measured against the contaminated column, which of course dominates: it has seen the answer.
  **Rerun `scripts/model_search.py` against `fpl_xp_prev` before trusting any of it.**
- **§15's oracle framing** — the ceiling probes stand on their own (they never used `xP`), but
  "FPL beats a hindsight oracle, therefore they have match-level information we lack" was the
  wrong inference. They beat the oracle because they had already seen the gameweek.
- **§15's conclusion that historical statistics cannot reconstruct FPL's number** — true, and now
  unsurprising: no historical feature can reconstruct a value containing the outcome. That null
  says nothing about whether historical features are useful.

### What still stands

- The `_subset_metrics` coverage bug (§13) was a real, separate bug and its fix is still correct.
- The LightGBM nulls stand — those compared against our own structured model, not against `xP`.
- The minutes-vs-returns diagnostic stands in shape, though the FPL side of every number in it
  needs recomputing against the clean baseline.
- The oracle ceilings stand: player-quality-oracle 0.421, quality × actual-minutes 0.553. Our
  0.374 against those is a fair reflection of how hard single-gameweek prediction is.

### The lesson

Two measurement bugs in one day, both in the same direction: **the comparison was wrong, not the
model.** The first (§13) flattered us, the second flattered FPL, and neither was visible in code
that read correctly line by line. What was missing both times was a check on the *meaning* of the
thing being compared to — coverage in one case, timing in the other.

Any future benchmark against an external number must answer, in writing, before it is trusted:
**when was this value recorded, relative to the event it predicts?**

---

## 17. Collecting our own data — start 2026-08-21

`scripts/snapshot.py` / `make snapshot`. Written 2026-08-05, before the season starts, because
of what §16 found.

### Why

§16 established that the community dataset's `xP` is not a forecast — it is scraped after the
gameweek and absorbs the result through FPL's `form` average. The corrected benchmark works by
shifting that column back a week, which is honest but imperfect: it takes FPL's snapshot from
just after the *previous* gameweek, so it misses whatever they learn in the days before the next
deadline. FPL is being judged on a slightly stale version of itself.

Capturing our own removes the guesswork. A value this script writes is unambiguously
pre-deadline, because it is written before the deadline and stamped with how long before.

Two things become possible, and **both are lost forever for any week the capture doesn't run**:

1. **An honest benchmark, permanently.** FPL's `ep_next` recorded against the deadline it
   applies to. No shifting, no reconstruction, no argument.
2. **Availability in the backtest.** `chance_of_playing_next_round`, `status` and `news` live
   only in the live bootstrap — no historical dataset carries them. Production already uses them
   to cut an injured player's projection; the backtest cannot, so **every validation number this
   project has published describes a handicapped version of the shipped model.** A season of
   snapshots makes that measurable for the first time.

The FPL API serves only the present. There is no back-fill.

### What it does

Captures `bootstrap-static` (every player: `ep_this`, `ep_next`, `form`, `status`,
`chance_of_playing_*`, `news`, price, ownership, ICT components, BPS — plus events and teams) and
`fixtures`. Both land immutably under `data/raw/` partitioned by ingest timestamp, so a re-run
never overwrites an earlier capture. Each run appends one line to
`data/raw/snapshot_index.jsonl` recording when it ran, which gameweek it was for, how many hours
before the deadline, and how many players were flagged — so "what do we have" never means walking
the partition tree.

### Running it

```
0 */6 * * *  cd /path/to/repo && .venv/bin/python scripts/snapshot.py --if-near-deadline
```

`--if-near-deadline` exits without capturing unless a deadline is inside `--window` hours
(default 12), so a frequent cron yields roughly one useful snapshot per gameweek. Omit the flag
to force one. **Aim for 2–4 hours before the deadline** — late enough that team news has landed,
early enough that it is still a forecast.

Verified against the live API on 2026-08-05: found the GW1 deadline (2026-08-21 17:30 UTC),
captured 568 players, 527 already carrying a non-zero `ep_next`, 60 flagged. Four tests cover
deadline selection, because a snapshot filed against the wrong gameweek looks like evidence and
is not — the exact failure mode this whole effort exists to eliminate.

### What to do with it, once a season exists

1. Re-run the validation with a **real** pre-deadline FPL baseline and replace §16's shifted
   figures. That settles the comparison permanently.
2. Run the backtest with availability **on** and quantify what it is worth. This is the number
   nobody has ever been able to compute.
3. Re-run `scripts/model_search.py` against the clean baseline — §14's "our model adds nothing
   to FPL's" was measured against the contaminated column and is not to be trusted.
4. Re-examine whether the site should still hide FPL's `ep_next` (§8, §14). The reasoning
   changes now that we are ahead rather than behind.

### Worth adding later, not now

Player prop odds (anytime goalscorer) remain the most promising external source — they price
exactly the forward-looking information no historical table carries. But **historical props are
scarce and expensive**, which means a prop-based model could be built forward and not validated
before committing. Snapshotting is the cheaper move and it starts paying immediately. Revisit
props once there is a season of our own data to test against.

---

## 18. Understat is fixed, and what the saves model did with it (2026-08-05)

### The Tier-2 blocker was one request header

§5 said `getMatchData/{id}` "now 404s" and that Tier-2 was blocked upstream. Half right, and the
wrong half was the actionable one.

The match page really did stop embedding `shotsData` — that part is true and it is what breaks
every scraper written against the HTML, `soccerdata` 1.9.1 included. But `getMatchData/{id}` is
alive: it is what the site's own `match.min.js` calls, and it answers **404 to a plain GET and
200 to the same GET carrying `X-Requested-With: XMLHttpRequest`**. An unadorned request gets a
response indistinguishable from a deleted endpoint, which is how it was misread.

`ingest/understat.py` now talks to the JSON endpoints directly: `getLeagueData/{league}/{season}`
for a season's teams, players and 380 fixtures in one call, `getMatchData/{id}` for shots and
rosters. Verified live — 20 teams, 562 players, 380 fixtures, 9,878 shots for 2024-25.

Two consequences worth keeping:

- **No browser impersonation is needed.** The project's own honest User-Agent gets 200s. There is
  no Cloudflare challenge and no TLS fingerprint check on these endpoints, so the `tls_requests`
  native-library saga in §5 was *soccerdata's* transport requirement, never Understat's.
- **`soccerdata` is off the dependency list.** It was there for this module alone.

### The pitch was mirrored, and nobody had checked

`Y_ZERO_IS_LEFT` was `True`, with a comment saying it **must** be verified before anything was
labelled "left" to a user. It never was, and it was backwards.

The check is self-contained, which is why it now lives in the module: Understat's roster
`position` codes encode a side (`AML`/`AMR`, `DL`/`DR`, `ML`/`MR`, `FWL`/`FWR`). Take every player
whose codes are consistently one-sided and who took 8+ shots, compare to their mean shot Y:

| | n | mean Y | consistent |
|---|---|---|---|
| left-coded | 37 | 0.572 | 33/37 above 0.5 |
| right-coded | 33 | 0.436 | 29/33 below 0.5 |

**Low Y is the attacking team's right.** Exactly the silent flip the original comment feared —
every team's attack mirrored, every number still plausible. Re-run this probe whenever the
upstream convention is in doubt; it needs no outside knowledge of who plays where.

### What shot zones can and cannot support

Shot **origin** is ~80% central for every team, because that is where shots are taken regardless
of which flank the move came down. The only varying signal is the left/right split of the
remaining fifth, and at 150 matches **only 34% of the observed between-team spread is real** —
the rest is sampling noise. A full season puts noise sd near 0.037 against a true between-team sd
of ~0.057.

So it is a real tendency and a weak one, and it is **not** Opta's "attacks down the left", which
is built from possession chains. A better proxy that costs no new data: every shot carries
`player_assisted`, and the roster codes give that assister's side — assist-chain-by-channel is
much closer to "where the attack came from" than shot XY.

### Saves from shots faced — measured, and only half of it worked

§14 called this the clearest mechanical defect in the model. `x_saves = opp_lambda * 3 *
(x_minutes/90)` makes saves proportional to expected goals conceded, so clean-sheet points and
save points move against each other and cancel.

**The feature was validated before anything was built on it.** Understat `SavedShot` counts
against FPL's own recorded saves, 758 keeper-matches: Pearson **0.968**, 90.6% exact agreement,
97.5% within one save.

Two full walk-forwards, 2024-25, 30 gameweeks, clean baseline:

| | baseline | saves-from-shots | p |
|---|---|---|---|
| GK MAE | 2.4648 | **2.3282** | 8.5e-09 |
| GK per-GW Spearman | 0.0711 | 0.0893 | **0.40 — not significant** |
| all played MAE | 2.0107 | 2.0017 | 1.3e-08 |
| DEF / MID / FWD | unchanged | unchanged | — |

**Accuracy improves significantly. Ranking does not** — 13 of 30 gameweeks improved, 17 got
worse, and the mean gain rides on a few large ones. A hybrid taking the opponent factor from the
engine's fixture λ is worse (MAE 2.3375, Spearman back at baseline): the opponent's season-long
save-forcing rate beats the engine's view of the specific fixture, because λ predicts goals and
this term needs shots on target.

**§14's per-position table needs the §16 treatment.** It reported GK 0.064 against FPL's 0.438
and called it the model's biggest positional deficit. Against the clean pre-deadline baseline FPL
manages **0.115**. Single-gameweek goalkeeper ranking is near-noise for everyone; 0.438 was the
contaminated column again.

**Not wired to production.** Default is still `saves_mode="lambda"`; `xp_table.py` is untouched.
Turning it on means a weekly Understat fetch beside a precompute that already degrades silently
(§4). Do the loud-failure work first, then decide — the gain is a MAE improvement on one position
with no ranking gain, which does not by itself justify a new live dependency.

### Do the Understat features improve ranking? No — and this null is clean

§15 concluded that historical statistics cannot reconstruct FPL's number, but §16 voided the
reasoning: that was measured against a column containing the outcome, so it said nothing about
whether historical features are useful. This re-asks the question properly, against the clean
baseline, with features the project has never had — `xGChain` and `xGBuildup` in particular have
no FPL equivalent.

Point-in-time rolling per-90s, 2024-25, 7,168 played player-gameweeks over 30 gameweeks.

**1. Marginal — each feature alone against actual points:**

| our structured xP | xG | xGChain | xA | shots | key_passes | xGBuildup |
|---|---|---|---|---|---|---|
| **+0.331** | +0.134 | +0.130 | +0.123 | +0.124 | +0.114 | −0.017 |

**2. Orthogonal — and this is where the naive version of the test lies.** The obvious check is
whether a feature correlates with `rank(actual) − rank(our xP)`. It does, strongly and
negatively, for almost everything. That result is an **artifact**: rank residuals are bounded by
construction, so the player we rank first can only move down and the player we rank last can only
move up. Any feature correlated with our xP inherits a negative correlation for purely mechanical
reasons — and every feature here is correlated with our xP, because our xP is built from xG and
xA. Reported as-is it would have looked like a large exploitable bias.

The correct test is a partial correlation with our xP held constant: *among players we already
rate equally, does this feature separate them?*

| feature | partial r | p | within DEF / MID / FWD |
|---|---|---|---|
| key_passes | +0.068 | 0.0003 | all p > 0.08 |
| shots | +0.058 | 0.0024 | all p > 0.36 |
| xGChain | +0.056 | 0.0033 | all p > 0.28 |
| xA | +0.056 | 0.0009 | all p > 0.22 |
| xG | +0.051 | 0.0037 | all p > 0.13 |
| xGBuildup | −0.001 | 0.96 | — |

Significant pooled, tiny, and **it disappears within position** — every per-position effect is
insignificant and roughly a third the size. The pooled signal is largely *between* positions:
the features proxy for what position a player plays, which the model already knows.

**3. Conversion — time-split, weights fitted on GW9–23 and scored on GW24–38:**

| model | test Spearman | vs xP alone |
|---|---|---|
| **our xP alone** | **0.3550** | — |
| xp + xGChain | 0.3376 | −0.017 |
| xp + xGBuildup | 0.3267 | −0.028 |
| xp + chain + buildup | 0.3269 | −0.028 |
| xp + all six | 0.3004 | −0.055 |
| Understat features only | 0.1032 | −0.252 |

**Every combination is worse out of sample.** A linear rank blend, deliberately — §15 recorded
LightGBM destroying signal on this problem three times, and the partial correlations above bound
what *any* model could extract regardless of its capacity.

**This is the fourth null, and the first one that stands on its own.** The three in §14–§15 were
measured against the contaminated column and were void. This one uses the clean baseline, new
features, and a test that survives its own artifact check. Historical per-player statistics —
including ones FPL does not publish — do not improve our ranking of players who feature.

**So the Match Lab is the right home for this data**: it is genuinely interesting to *read* and
does not predict. Use it for content and matchup context, not as model features.

Caveats worth carrying: one season; 94.3% identity-join coverage with the miss skewed toward
mid-season transfers; and this tests features *added to* our xP, not a ground-up model built on
them.

---

## 19. Where the model can still improve (2026-08-05)

A survey of the remaining options — different engine, different features, different data —
measured rather than argued. **The headline: one modelling change works and it is small, and the
thing that actually matters is not a model at all.**

### The number that should drive prioritisation

`validate_xp(oracle_minutes=True)` replaces the minutes model with the minutes actually played.
It cheats; that is the point. 2024-25, played-only per-GW Spearman:

| configuration | played | all players |
|---|---|---|
| shipped | 0.3758 | 0.6866 |
| + xG-fitted engine | 0.3878 | 0.6895 |
| **+ xG engine + perfect minutes** | **0.5562** | **0.8285** |
| *(FPL clean baseline)* | *0.2993* | *0.6077* |

**Perfect team news is worth +0.168. The best modelling change found is worth +0.012.** Fourteen
to one. And +0.168 is a LOWER bound — goal and assist shares are allocated before the oracle
substitutes, so an attacker's largest term still runs on predicted minutes.

Everything below is inside the small gap. The large one is bought with data.

### What worked: fit the engine on xG, not goals

The practitioner consensus is that xG estimates team strength better than goals. The canonical
reference for combining it with Dixon-Coles (statsandsnakeoil, 2018) says outright that it never
tested the claim — "I would like to put it to the test" — so this does.

Mechanically it is a substitution: the likelihood already uses `gammaln(y+1)`, the continuous
generalisation of `log(y!)`, and that term is constant in the parameters, so feeding it
non-integer xG leaves the MLE valid.

| season | goals | xG | delta | p | gws better |
|---|---|---|---|---|---|
| 2024-25 | 0.3758 | 0.3878 | +0.0120 | 0.0015 | 20/30 |
| 2023-24 (out of sample) | 0.3714 | 0.3770 | +0.0057 | 0.076 | 18/30 |
| **pooled** | | | **+0.0088** | **0.0003** | **38/60** |

95% CI **[+0.0042, +0.0135]**. Replicated in direction on a season no parameter was chosen on,
though the out-of-sample effect is half the size and only marginal on its own.

**The control matters.** Fitting on xG silently disables Dixon-Coles' tau correction, whose masks
key on exact integer scorelines — so the comparison is really DC-on-goals against Poisson-on-xG.
Re-running goals with `+1e-9` added (identical likelihood, masks stop matching) isolates it: **tau
is worth −0.0002.** The whole gain is the xG. As a side finding, the tau correction is worth
nothing to FPL player ranking, whatever it does for exact-scoreline betting markets.

**npxG is worse than xG** (+0.0097 in 2024-25, +0.0008 in 2023-24 — not replicated). Stripping
penalties removes real signal, not noise.

Not wired in: it needs a weekly Understat fetch beside a precompute that still degrades silently
(§4), same trade as the saves model in §18, and it is small next to the team-news number.

### What did not work

- **Understat player features** (`xGChain`, `xGBuildup`, `key_passes`, shots, xG, xA) — §18. Tiny
  pooled partial correlations that vanish within position; every out-of-sample blend worse than
  our xP alone. Fourth null, first one measured against a clean baseline.
- **Saves from shots faced** — §18. Significantly better goalkeeper MAE, no ranking gain.
- **npxG** — above.

### The ranked list, with the reasoning attached

1. **Team news / expected lineups.** Worth up to +0.168, an order of magnitude beyond anything
   else. The free version is already running: `scripts/snapshot.py` captures
   `chance_of_playing_next_round`, `status` and `news` weekly from 2026-08-21, and **production
   already applies `availability_factor` while the backtest cannot** — so every published number
   understates the shipped model by an unmeasured amount. A season of snapshots makes that
   measurable and is the precondition for judging anything else here.
2. **Paid expected-lineups feed.** Sportmonks advertises 84% EPL accuracy pre-kickoff. Now has a
   price attached: a fraction of +0.168. Worth revisiting once snapshots quantify what the free
   FPL availability fields already deliver — buy the gap, not the whole thing.
3. **xG-fitted engine.** +0.0088, replicated, ready. Cheap, but carries the same weekly-fetch
   operational cost as everything else Understat-based, so it should land after the precompute
   fails loudly.
4. **Set-piece and penalty duty as a forward-looking signal.** Still untested and still the best
   remaining *feature* idea (§14). Historical xG cannot express "took over penalties last week";
   `playermeta.py` already parses the order fields and is explanatory-only today.
5. **Player prop odds.** Unchanged from §15: prices exactly the forward-looking information no
   historical table carries, and historical props remain scarce and expensive, so it can be built
   forward but not validated before committing.

### What is now firmly closed

More historical per-player statistics, in any form, from any source. That is four independent
nulls, and §18's was measured against the clean baseline with features FPL does not even publish.
The model's remaining error is not in what it knows about the past.

---

## 20. Working the §19 list, 1 to 5 (2026-08-05)

Each item measured or built rather than argued. Two produced code, two produced nulls, one
overturned a standing assumption about cost.

### 1 & 2 — team news: what each grade of it is actually worth

§19's +0.168 for perfect team news is not purchasable. Graded into things that are:

| what you know | played-only | all players |
|---|---|---|
| model minutes (shipped) | 0.3878 | 0.6895 |
| the STARTING XI | 0.5252 | 0.6947 |
| who APPEARS | 0.3906 | 0.8194 |
| EXACT minutes | 0.5562 | 0.8285 |

The two columns disagree, and that is the useful part. For ranking players who feature, knowing
the eleven is **82% of the whole prize** and knowing merely who appeared is worth nothing — that
is what "played-only" already conditions on. Across the full pool it inverts: knowing who appears
is worth +0.130 and knowing the eleven almost nothing, because the dominant error there is
projecting points for players who never get on.

**Our minutes model already names the starting XI at 78.3%** (5,024 of 6,413 slots, point-in-time).
Graded by feed accuracy:

| feed accuracy | played-only | all players |
|---|---|---|
| 78.4% (ours today) | +0.0431 | −0.0725 |
| **84% (Sportmonks' EPL claim)** | **+0.0671** | **−0.0513** |
| 90% | +0.0874 | −0.0295 |
| 100% | +0.1374 | +0.0052 |

So a paid feed is worth about **+0.067 on who-to-pick, not +0.168** — and naive integration makes
all-player ranking *worse*, because replacing the model wholesale commits ~16,000 non-starters to
a crude bench profile the continuous model handles better. A real integration would blend, so the
truth sits between the columns. Smaller and more conditional than §19 implied.

**A rejected idea, recorded because it looks obviously right.** The feed-at-our-own-accuracy row
gaining +0.043 suggests the gap is sharpness, not accuracy — our model hedges a nailed-on starter
and a rotation risk into the same 60–75 minute band. So `sharpen_minutes` takes our own top eleven
and applies the empirical starter profile: same information, discretised, no new data. **It loses**
(−0.0062 played, −0.0889 all). Committing to an XI you get right 78% of the time amplifies your
own errors; the continuous model is the better description of real uncertainty.

**Built:** `fpledge/eval/snapshots.py` reads pre-deadline captures back, and
`validate_xp(availability=...)` finally lets the backtest apply the `availability_factor`
production has always applied. Writing its test **found a real bug** — the first version applied
availability *after* `rate_shares`, so a ruled-out player scored zero appearance points while
keeping a full share of his team's attack. Production has the order right; a backtest that
disagrees measures a model nobody ships.

### 3 — the xG-fitted engine, now a supported path

`ingest/understat.substitute_xg(matches, understat_fixtures)` returns engine-ready matches plus a
coverage report. Verified on real data: 380/380 joined, all twenty teams mapped. The join needs
the date — each pairing happens twice a season, so matching on teams alone attaches the reverse
fixture's xG to half of them, plausibly. Partial coverage is reported rather than logged, because
part-xG-part-goals is a different model on different seasons.

### 4 — set-piece duty: real signal, does not convert

§14's last untested idea, and the argument for it is good: our xG per 90 already contains
historical penalty xG, so the "it double-counts" objection is right about the past and silent
about the future. Three duties built point-in-time from Understat — penalties (83 events all
season), direct free kicks (269), corner delivery via `player_assisted` on corner shots (1,619).

Partial correlation with points, our xP held constant:

| duty | all players | p | among players WITH the duty | p |
|---|---|---|---|---|
| penalty | +0.0045 | 0.64 | **+0.1575** | **0.0013** |
| freekick | +0.0022 | 0.80 | +0.0183 | 0.61 |
| corner | +0.0031 | 0.77 | −0.0203 | 0.30 |

**Penalty duty carries genuine signal among takers.** It still does not convert. A rank blend is
worse (−0.0095) for a mechanical reason — 94% of rows are zero, so `rankdata` collapses them into
one tied block and shuffles every non-taker. So it was retried the way a model would do it, as a
targeted additive bonus `xp' = xp + k·pen_share` that moves only takers: train improves
monotonically to k=1.5, **test is flat** (peak +0.0003 at k≈0.5), and choosing k honestly on train
gives **−0.0006**. Textbook overfitting on a sparse feature.

The reason is arithmetic. At 0.22 penalties per match, a designated taker's expected penalty value
is ~0.1 xP per gameweek — below the noise floor of single-gameweek scoring. **Fifth null.**

### 5 — player props are NOT scarce or expensive. §15 was wrong about this

§15 parked props because "historical props are scarce and expensive, which means a prop-based
model could be built forward and not validated before committing." That is no longer true, and it
was the only thing keeping this off the list.

[The Odds API](https://the-odds-api.com/historical-odds-data/) carries historical **player props
from 3 May 2023** at 5-minute snapshots, on every tier including free. Historical additional
markets cost 10 credits per market per region per event. Three EPL seasons is 1,140 events ×
10 credits = **~11,400 credits — one month of the $30/20K tier.**

So the whole "cannot validate before committing" objection collapses to roughly **$30 and a
weekend**. And props are strategically better than they look: an anytime-goalscorer price is a
market-clearing P(scores) that already embeds team news, so a benched player is priced long. It is
a way to buy a share of the +0.168 team-news prize *and* a quality estimate in one number, from a
source with no 84%-accuracy ceiling.

**This is now the highest-value untested idea in the project**, ahead of the lineups
subscription, and it is cheap enough to settle rather than argue.

### Revised order

1. **Buy one month of historical props and backtest them.** ~$30, three seasons, settles the
   largest open question. Was parked on an assumption that is no longer true.
2. **Snapshots from 2026-08-21.** Unchanged, free, cannot be backfilled, and the plumbing to
   consume them now exists.
3. **xG engine.** +0.0088, replicated, ready — after the precompute fails loudly.
4. **Expected-lineups feed.** +0.067 on who-to-pick, negative on all-players without blending.
   Revisit once snapshots show what the free FPL availability fields already deliver.
5. **Nothing else on the modelling side.** Five nulls now: recency-xG, returns-bonus, LightGBM
   (×3), Understat player features, set-piece duty.

---

## 21. Free routes to market data, and whether prediction markets help (2026-08-05)

§20 said props cost ~$30 to validate. Asked whether that is avoidable, three free routes exist and
one of them was already sitting in the repo.

### The free market signal we already had — and it works

`validate_xp(fixture_lambdas=)` and the production precompute both prefer market-implied lambdas
over the engine's. **That preference had never been scored on FPL player ranking**, only on match
outcomes, and it could not be: `parse_csv` carried the closing 1X2 triple but not the over/under
2.5 prices, and `market_lambdas` needs both — 1X2 fixes supremacy, O/U fixes total goals. The
`_ou_odds` helper existed and was wired only into the live path. So the historical half of a
shipped feature was unmeasurable by construction.

Two fields later, 2024-25 played-only per-GW Spearman:

| engine | played | vs shipped | p |
|---|---|---|---|
| goals (shipped) | 0.3758 | — | — |
| goals + market λ | 0.3853 | +0.0095 | 0.017 |
| **xG (§19)** | **0.3878** | **+0.0120** | **0.0015** |
| xG + market λ | 0.3853 | +0.0095 | 0.017 |

**The market-lambda preference is vindicated** against the shipped engine — assumed until now.
**And our xG-fitted engine already matches the market** (−0.0025, p=0.42, indistinguishable). Free
Football-Data closing odds, free Understat xG, and the two land in the same place.

The last row is identical to the second because `validate_xp` bypasses the engine entirely for any
fixture carrying a market lambda; at 380/380 coverage the engine is never consulted. Production
coverage is partial (books post lines ~2 weeks out), so production is a real hybrid — do not read
that row as "market and xG cancel out".

**This narrows the props case usefully.** If a team-level market view adds nothing over our own xG
engine, props are not worth buying because "the market knows the fixture better". They are worth
buying for the two things they uniquely carry: the **player-level split** of a team's goals, and
**team news priced in by construction** — a benched player is priced long, which is a share of the
+0.168 prize from §19.

### Free routes to props

| route | cost | what you get | catch |
|---|---|---|---|
| **The Odds API, forward capture** | **free** | anytime-goalscorer weekly from now | ~10 credits/gameweek against a 500/month free tier — fits ten times over. Builds history from zero, same bet as `snapshot.py` |
| **The Odds API, historical** | free, slowly | 50 events/month on the free tier | 380-match season ≈ 8 months. A 150-match sample for a first read ≈ 3 months, or $30 buys it now |
| **Betfair Exchange historical** | **free** | Basic tier, 1-minute last-traded price, back to 2016 | **no volume field** — and an illiquid last-traded price is not a market-clearing probability, so the free tier strips exactly what you would need to tell the two apart. Whether goalscorer markets are downloadable on Basic is NOT confirmed in public docs; it needs a Betfair account and ten minutes to check |

The honest recommendation: **start the free forward capture now**, alongside the snapshot cron, for
the same reason — it cannot be backfilled and it costs nothing. Buy the historical month only if
you want the answer before next May.

### Prediction markets — no, not for this

Kalshi does list EPL match markets and is CFTC-regulated with no vig, which makes it attractive in
principle. It is the wrong instrument here for reasons that are structural rather than incidental:

- **Breadth.** This model needs ~200 player-match scoring probabilities per gameweek — every
  plausible starter across ten fixtures. Kalshi's soccer props are mostly season-long futures
  (Golden Boot, relegation), not per-match goalscorer lines. Bookmakers price all 200 every week.
- **Liquidity.** A prediction market is informative in proportion to its volume, and Kalshi's
  depth sits in US sports and marquee soccer events. An EPL mid-table anytime-goalscorer contract
  would be thin or absent.
- **Redundancy where it does have coverage.** Kalshi's EPL match markets duplicate what
  Football-Data closing odds already give us for free — and the table above shows our xG engine
  already matches that signal.

Where a prediction market genuinely would help is a question with one contract and real volume —
title winner, top four, relegation, Golden Boot. Those are season-long, and this model is a
single-gameweek player-ranking model. Different question.

---

## 22. The props capture is live, and §14's blend result is now inverted (2026-08-05)

### Forward capture, running

`scripts/capture_props.py` / `make capture-props`. Weekly anytime-goalscorer prices, ~10 credits
a gameweek against a free tier of 500 a month. Same discipline as `snapshot.py`: run it from
2026-08-21, because by roughly GW10 there is enough paired data to answer whether props beat our
xP, and every week missed costs $30-scale money to recover later.

**Do this once before trusting it:** `make capture-props ARGS=--list-markets`. A wrong market key
returns an empty bookmaker list rather than an error — indistinguishable from "no book has priced
it yet" — so it would capture nothing all season and look like a quiet week every time. A capture
where every fixture returns zero bookmakers now prints that ambiguity and exits non-zero.

**The live path is unverified.** Written without an API key; offline behaviour is tested through a
fake session and no real request has been made.

### Can the model use props now? Two different questions

**Validation: no, not yet** — that is what the capture is for, and why it starts now.

**Production use: yes, technically, from GW1** — props are available live; nothing stops the
precompute consuming them. The reason not to is discipline, not capability: this project's whole
position is that it publishes measured numbers, and shipping an unvalidated signal into the
projection would be the first time it acted on a hunch. Capture now, measure around GW10, ship
after. That sequencing costs one half-season and keeps the claim honest.

### §14's headline is now inverted, not merely void

§16 said to re-run the blend against the clean baseline and nobody had. §14 concluded "the
optimal weight on our model is 0.0 at every position" — measured against a column that had
already seen the gameweek.

Clean baseline, rank space, weights fitted on GW9–23 and scored on GW24–38:

| weight on OURS | train | test |
|---|---|---|
| 0.0 (FPL alone) | 0.2792 | 0.3182 |
| 0.5 | 0.3608 | 0.3818 |
| 0.8 | 0.3834 | 0.3919 |
| **1.0 (ours alone)** | **0.3888** | 0.3869 |

Weight chosen honestly on train: **1.0**, and the gain over ours alone is **+0.0000**. Per
position the answer is 1.00 everywhere except FWD at 0.95, worth +0.0021.

**"Our model adds nothing to FPL's" is now exactly backwards: FPL's clean projection adds nothing
to ours.** One caveat kept because it is real — the test half peaks at w≈0.8 (0.3919) where the
train half peaks at 1.0. That is either noise or a small blend benefit the train half is too
short to see, and honest selection does not capture it. Not established, worth one re-run on a
second season.

**This settles the §8 / §14 strategic question.** The site shows one xP per player, ours, and
hides FPL's `ep_next`. That was defensible-but-awkward when we thought we were behind. It is now
simply correct: ours is better, and theirs adds nothing on top of it.

### What is actually left to explore

The *prediction* is close to its ceiling on public data — five nulls and two small wins this
session. The remaining upside sits in two places, and only one of them is about modelling.

**A. Data we do not have** (§19–§21): team news, and props. Both now capturing.

**B. Turning predictions into DECISIONS — never measured at all.** Every number this project has
published is a *ranking* metric. The product does not rank; it decides: which transfer, who to
captain, who to bench, when to play a chip. A +0.01 Spearman may change no decision, and a
recalibration that cannot move Spearman at all may change many.

1. **Simulate a season following the model's own advice** and report final points and rank against
   the field, as a distribution with a skill-vs-luck split. This is the number a user cares about
   and the one `/model` should arguably lead with. Never computed.
2. **Expected-rank objective instead of raw xP.** `models/xpoints.py` says outright that raw-xP
   maximisation is not rank maximisation and that captaincy and differentials should optimise
   expected rank against effective ownership. `models/rank.py` exists; the optimiser still
   maximises raw xP. A product improvement needing no new data and no better forecast.
3. **Dispersion, judged by decisions rather than by Spearman.** We are under-dispersed (ours sd
   1.46–2.00, actual 2.76–3.45). A monotone rescaling cannot move Spearman by construction — which
   is exactly why it has never been tested — but it moves every threshold that matters: whether a
   transfer clears the −4 hit, how big a captaincy edge looks.
4. **Auto-subs and bench order.** Pure optimisation, no new data, worth real points over a season.
   The optimiser currently has no bench ordering at all.
5. **Chip timing** (wildcard, bench boost, triple captain, free hit) as a Monte Carlo over the
   fixture calendar.
6. **Price-change model.** Team value compounds across a season and is entirely unmodelled.
7. **Defensive Contribution calibration.** New 2025/26 scoring, a meaningful share of DEF/MID
   points now, and `dc_point_probability` has never been validated on its own.
