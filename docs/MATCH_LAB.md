# Match Lab — its own page: the plan and the checklist

Started 2026-11-16. Match Lab becomes a destination of its own in the site's navigation, not a
page you only reach by tapping a fixture. **Fixtures** stays the planning tool (scan eight
gameweeks wide); **Match Lab** is the depth tool (one gameweek's matches, studied one at a time).

Two levels:

- **The hub, `/match-lab`**: this gameweek's matches as cards, in kickoff order.
- **A match, `/match-lab/[match]`**: everything we know about one fixture, in sections.

`/fixtures/[match]` (live since §40) moves to `/match-lab/[match]`, and the old address redirects
so no link breaks.

## Ground rules (unchanged from the original plan)

- Every number comes from the pipeline. A language model never writes a number; the written
  read is checked against its fact pack and hidden when it fails or is only the template.
- The bookmakers' odds lead when they exist; our model is the second opinion (§35, §45).
- No betting advice. Approximations are labelled as approximations.
- Phone first (390 wide), then desktop (1440); dark and light; no horizontal scroll.

## The hub: `/match-lab`

| Part | Shows | Data | Status |
|---|---|---|---|
| Header | "Gameweek 11", deadline in local time | `/health` gameweek | **built**, kickoff per match; the deadline is not in the payload yet |
| Gameweek switch | current + next seven; later weeks show odds only | `/matches/{gw}` | **built** (arrows) |
| Match card | both clubs, kickoff time, win/draw/win bar, expected goals, clean-sheet chances | match payload | **built** |
| Card flags | "our model disagrees" when expected goals differ by 0.3+; number of FPL-flagged players per club | `model` (#15); availability (injured, doubtful, suspended only) | **built** |
| Card picks | best FPL pick from each side | `/predictions/{gw}` grouped by club, on the server | **built** |
| Sort | kickoff (default), most goals expected, biggest disagreement, best clean-sheet chance | client side | **built** |

## A match: `/match-lab/[match]`

A sticky strip of section links (Overview · News · Lineups · FPL · Scores) under the header,
scrolling sideways on a phone.

| Section | Shows | Data | Status |
|---|---|---|---|
| Overview | teams, kickoff, result bar, the four tiles | match payload | **live** (§40) |
| The read | a short written summary, every number with its source beside it | `brief.py` + numeric guard; needs an API key | **built**, waits for the key |
| Our model's view | engine against bookmakers, one sentence on the gap | `model` | **live** (#15) |
| Form | each club's last five results, goals for and against | finished fixtures (scores in the FPL fixtures table) | **built** |
| Team news | FPL's flags for both clubs, then the week's stories about each club | assets' availability; `/news` grouped by club | **built** |
| Predicted lineups | both XIs in each club's usual shape, Nailed/Regular/Rotation tags | `lineups` | **live** (§40, §44) |
| Set-piece takers | FPL's order; likely taker marked | assets' `set_pieces` | **live** (#15) |
| FPL angles | best picks; each player's chance to score, to assist, of a clean sheet; captain pick and a differential from this match | assets' breakdowns (chance to score = 1 − e^−expected goals, labelled as our model's) | **built** |
| Scores | likeliest scores, both to score, over 2.5 | match payload | **live** (§40) |
| Key matchups | "attacks down the left" style angles | shot locations from an outside source; always an approximation | later, needs a decision |

Empty states: a later gameweek has odds but no lineups, picks or set pieces; a model-priced
match has no comparison; a match with no odds at all says so.

## Checklist

### Phase 0 — decisions (owner)
- [x] Name and address: "Match Lab" at `/match-lab` (recommended), or "Matches".
- [x] Navigation: a fifth tab (recommended; the phone bar fits five at 78px each) or a switch
      inside Fixtures.
- [x] The written read: built and wired; it switches on when the owner adds the key.
- [ ] Key matchups: build the approximation later, or leave out. **Still open.**
- [x] Merge PR #15 first (its two sections move into the new page).

### Phase 1 — the address and the hub
- [x] `/match-lab/[match]`: move the match page; redirect `/fixtures/[match]` permanently.
- [x] Fixtures grid links, player sheet links and the sitemap point to the new address.
- [x] Navigation: Match Lab on desktop and in the phone tab bar.
- [x] Backend: `kickoff` on every match preview (from `fixtures.kickoff_utc`); test.
- [x] `/match-lab` hub: cards for the current gameweek, kickoff order, gameweek switch.
- [x] Card flags and best pick per side.
- [x] Sort control.
- [x] Metadata (title, description, canonical) for both pages.

### Phase 2 — the match page's structure
- [x] Sticky section strip with anchors; phone sideways scroll.
- [x] Sections in the order above; #15's two sections in place.
- [x] Every empty state written and checked.

### Phase 3 — new content
- [x] Backend: each club's last five results on the match preview (`form`); test.
- [x] Form section.
- [x] Team news section: flags for both clubs from the assets, stories from `/news` filtered to
      the two clubs (no backend change).
- [x] FPL angles: chance to score / assist / clean sheet per player from the breakdowns; captain
      pick (highest expected points) and a differential (highest expected points under 10% owned).

### Phase 4 — the written read (only after the Phase 0 decision)
- [x] The precompute reads `ANTHROPIC_API_KEY` from a GitHub secret and installs the `llm` extra.
- [ ] **Owner:** add the `ANTHROPIC_API_KEY` repository secret. Until then every read is the
      template and hidden.
- [ ] One live run: check the numeric guard rejects and falls back as designed; read every
      summary for a gameweek by hand before showing any.
- [x] Provenance: each sentence's numbers shown with their source fact beside them.
- [x] Hidden whenever `generated_by` is the template.

### Phase 5 — key matchups (only after the Phase 0 decision)
- [ ] Decide the source and the labelling first; nothing presented as Opta.

### Every phase: checks before the PR
- [ ] Phone 390 and desktop 1440, dark and light: no overflow, no glued words, screenshots read.
- [ ] Backend tests for every new payload field; web typecheck, lint, build.
- [ ] After merge: precompute, then the live pages checked once their cache refreshes.
- [ ] HANDOFF section and this checklist updated.

## Status, 2026-11-16

Phases 1 to 3 built (HANDOFF §46). Phase 4 is wired: the read runs on Claude Opus 5.5 at low effort
with server-side fallbacks, and the precompute logs `n_briefs_written`; it starts the day the owner
adds the `ANTHROPIC_API_KEY` secret, and the first run must be read by hand before trusting it.
Phase 5 is still a decision. Found on the way and fixed: the main nav had not been sticky since
2026-08-05 (`.chrome-edge` beat Tailwind's `sticky`), and the template briefing called the
bookmakers' odds "the model's".
