# Model fixes — the tracker

Errors in how the projection is put together, found by comparing each scoring term with the
points FPL actually awarded for it (HANDOFF §41). One row per error. Each fix follows the same
path: the rule is written and committed before any run, development seasons choose, one
held-out season confirms once, then a PR. A fix that fails its test stays out.

Status: **found** → **rule written** → **tested** (verdict) → **PR** → **live**.

| # | Error | Size | Status |
|---|---|---|---|
| E1 | Keeper saves: 3 per expected goal, measured 2.02 | keepers −0.8 pts/game | **PR #11**: held out 2022-23, SHIP |
| E2 | Defensive contribution: threshold chance computed on expected minutes | DEF about 30% under; ranking +0.0033 | **PR #12**: held out 2026-27, SHIP |
| E3 | Cards have no term | −0.18 to −0.23 pts/90 outfield | **PR #13: live on the owner's decision** after an inconclusive held-out; GW11-18 confirms or reverts |
| E4 | Forwards' assists under-projected | FWD +0.1 pts/game | with E3, same status |
| E5 | Keeper save points ignore FPL's per-match rounding | keepers −0.33 a fixture, uniform; their whole over-projection | **development passed** 2026-11-22; branch `fix/save-rounding`; confirms on 2026-27 GW12-15 |
| E6 | Starts: minutes are a recent average, not a start probability | ranking +0.0073 held out | **PR #14**: held out 2026-27, SHIP |
| E6b | The start model cannot use FPL's flags | flagged early exits discounted twice | found |
| E7 | Pre-deadline data is about 23 hours old | Friday team news missed | found |
| E8 | Penalty saves have no term | keepers +0.07 pts/game, cancelled by their cards | parked |
| E9 | Expected starters play less than projected | about −0.3 pts/game on players expected to play | fixed by E6 (bias within 0.1 at every position) |
| E10 | Midfielders' clean sheets priced over the whole match; FPL counts only his minutes on the pitch | MID +0.016 a fixture | found; parked: changes no pick |

Not errors, measured (HANDOFF §41): pulling a player's projection towards his misses (never
better than +0.0006, up to −0.014), and goals against xG (does not carry over within a season).
And (§49) the clean-sheet chance from closing odds: off by 4.3 points in 2023-24, when goals ran
above the market's line until about GW26, and within 1.2 in every other season since 2022-23.

---

## E1. Keeper saves constant — PR #11

`x_saves = 3 × opponent lambda`. Keepers make 2.02 saves per expected goal conceded (9,428 keeper
fixtures, 2023-26). Held out on 2022-23: keeper MAE 2.757 → 2.594, −0.165 [−0.194, −0.135],
ranking unchanged. Fix: `config.SAVES_PER_EXPECTED_GOAL = 2.02`.

## E2. Defensive contribution

**What is wrong.** `dc_point_probability` takes the player's actions per 90 × *expected*
minutes and asks how likely a Poisson count with that mean reaches the threshold (10 for
defenders, 12 for midfielders and forwards). Expected minutes already include the chance he
does not play. A player with a 60% chance of starting has his mean cut to 60% before the tail is
taken, and the tail is steep: a defender averaging 9 a full game reaches 10 about 41% of the
time, but at a mean of 5.4 only 5%. The right number is 60% × 41% = 25%.

**What is not wrong, checked on 2025-26.** The Poisson curve itself. For players with 15+ full
games, the hit rate at a known mean matches Poisson within 0.03 in every band (defenders at a
mean of 8-10 hit 40%; Poisson says 40%). Counts are only mildly overdispersed: variance/mean 1.38
for defenders, 1.13 for midfielders.

**Size.** The development audit showed defenders expected 0.13 DC points a game against 0.42
actual in 2025-26, and midfielders 0.06 against 0.22. That overstates production's error: in
2025-26 the season before had no defensive stat, so every rate started from zero and stayed
shrunk. Production this season has a real prior. The held-out test measures the live size.

**Fix.** Split the match into two cases from the minutes model: he plays 60+ (probability
`p_60`, at the minutes that implies) or comes on for less (`p_play − p_60`, at 22 minutes, the
2025-26 average for a 1-59 minute appearance). Take the tail in each case and weight them. The
negative binomial (size fitted per position) is tested as a second variant.

**Test.** Develop on 2025-26, the only finished season with the rule. Held out: 2026-27 GW2-10,
whose defensive numbers have not been looked at. Primary: DC Brier score for defenders and
midfielders. Guard: all-player ranking no worse than −0.002. Rule: `fpledge/eval/defensive_contribution.py`.

**Result (HANDOFF §42).** Development chose the negative binomial (sizes 20 defenders, 39
midfielders/forwards). Held out on 2026-27 GW2-10: Brier −0.0014 [−0.0022, −0.0004], ranking
+0.0033 [+0.0015, +0.0053]. SHIP. Defenders' DC points per fixture 0.157 → 0.202 against 0.219
actual. The threefold size above was the development season's zero prior; the live error was
about 30%.

## E3. Cards

**What is wrong.** No term. Yellow cards are −1 and reds −3: −0.21 points per 90 for defenders,
−0.23 midfielders, −0.18 forwards, −0.08 keepers (2023-26). Casemiro lost 12 points to them in
2025-26, Cucurella 11.

**Fix.** Expected card points = −(yellow rate + 3 × red rate) × expected minutes / 90, with each
player's rate blended towards his position's like the other rates. A player's rate is only
weakly his own (split-half r = 0.11-0.27), so the prior weighs heavily: k is chosen on the
development seasons from a grid, not set.

**Test.** Develop on 2023-26; held out 2022-23 (cards untouched there). Mostly a level shift; the
reordering is card-prone midfielders and full-backs.

## E4. Forwards' assists

**What is wrong.** Forwards get 0.094 assists a game against 0.062 projected; defenders and
midfielders run slightly below. FPL credits assists xA cannot see (a won penalty, a parried shot
scored from).

**Fix.** A multiplier per position on the assist term, measured on the development seasons. First
check whether the excess is a trait of particular forwards (then a per-player blend) or of the
position.

**Test.** Bundled with E3: develop on 2023-26, held out 2022-23.

**Result for E3 and E4 (HANDOFF §43).** Stopped at development; production stays; 2022-23 is still
unspent for both. Assist factors measured: defenders 0.78, midfielders 0.84, forwards 1.32; they
helped one season of three. The card term improved the ranking (+0.0012 [+0.0007, +0.0017]) but
made squared error on played rows worse, and that score turned out to be biased against any term
that lowers projections: on played rows every outfield position is already 0.3 under, because a
projection includes the chance of not playing. A rerun scored over every projected row is a
change of standard after a failure, so it is the user's call.

**Retest (2026-11-16, at the user's request; HANDOFF §43).** Scored on every player the model
expected to play (p_play ≥ 0.5 before the deadline), whether or not he did. Development chose cards
+ assists: squared error −0.111 [−0.124, −0.096], better every season, ranking +0.0011. Held out on
2022-23: −0.047 [−0.103, +0.009], INCONCLUSIVE; production stays. 2022-23 was a weak stage (no
rate prior, and its attackers were under-projected where every other season had them over).
**Next:** the fixed candidate is confirmed or closed on 2026-27 GW11-18, rule written before GW11
was played: `python scripts/compare_cards_assists.py --confirm` once GW18 is final.

**Live on the owner's decision (2026-11-16).** The tested candidate went live without passing its
held-out test, because the model over-projects players expected to play and cards are a real
deduction. If the GW11-18 confirmation says DO NOT SHIP, revert `CARD_RATES_PER90` and
`ASSIST_SCALE` use in `xp_table`.

## E5. Keeper save rounding

**What is wrong.** FPL pays 1 point per 3 saves in a match, rounded down. Production pays a third
of a point per expected save, so a keeper making about 2 a game is still credited for saves that
earn nothing. Code exists and is unused: `xpoints.expected_save_points`.

**Parked.** The rounding takes 0.30-0.34 points off every keeper whatever his save volume (1.5
to 5 expected saves), so it changes no keeper's rank and no pick. It would only make keeper
totals honest; fold it into an all-rows calibration test if one is run.

**Unparked 2026-11-22.** A term audit on 2023-26 at production's settings, over keepers the
model expected to start: save points 0.906 a fixture projected, 0.611 with the rounding, 0.599
awarded. Keepers' total is 3.297 projected against 2.966 scored, and the save term is the whole
of that −0.33. Keepers are the one position the site shows as plainly over-projected every week,
and the boom/bust distribution already rounds, so its centre and xP disagree for keepers.

**Test** (`fpledge/eval/save_rounding.py`, `scripts/compare_save_rounding.py`). Judged on the
term itself, against the save points FPL awarded, over keepers the model expected to start.
Development 2023-26: the rounded term must reach within ±0.05 of awarded in every season, beat
production's keeper squared error pooled, and pass the usual ranking guard. Confirmation:
2026-27 GW12-15, the first four gameweeks not yet played when the rule was committed, run once
after GW15 is final (`--confirm`).

**Development (2026-11-22, HANDOFF §49): passes all three rules.** Save term, awarded minus
projected a fixture: production −0.263, −0.330, −0.327; rounded +0.030, −0.036, −0.030, each
interval inside ±0.05. Keeper squared error 7.640 → 7.539, −0.10 [−0.17, −0.03]; keeper bias
−0.34 → −0.04. All-player ρ −0.0008 [−0.0015, −0.0001]: inside the guard, and reliably a touch
negative, because honest keeper numbers rank keepers slightly lower against outfielders.
Production change committed on `fix/save-rounding` (`xp_table` pays `expected_save_points`);
GW12 built locally moves every keeper −0.30 with their order unchanged. Not merged: it waits
for the confirmation, or for the owner to ship it first as a decision.

## E6. Start probability

**What is wrong.** `MinutesModel.from_recent` averages the last six gameweeks. It does not know
that a player benched once after five starts is still likely to start, or that a player back from
injury starts on the bench. On 2023-26, knowing who starts lifts the ranking from 0.374 to 0.510:
more than every other fix here combined. Saliba's 69 minutes is the same problem.

**Fix.** A start-probability model trained on past seasons: starts in the last 1, 3 and 5 matches,
weeks since last start, minutes when last played, FPL's flag, home/away; separately, minutes
given a start. Then the DC and appearance terms use the start probability directly.

**Test.** Train on 2023-25, choose on 2025-26, held out on 2026-27 to date. Measured against the
current minutes model on start log-loss and the ranking.

**Result (HANDOFF §44).** Development, 2025-26: squared error on players expected to play −0.339
[−0.420, −0.261], ranking +0.0219 [+0.0132, +0.0307]. Refit on 2023-26 and held out on 2026-27
GW2-10: −0.204 [−0.292, −0.112], ranking +0.0073 [+0.0011, +0.0135]. SHIP. The expected-starter
bias (E9) is within 0.1 at every position.

## E6b. The start model and FPL's flags

The start model was fitted without FPL's injury flags; production multiplies its prediction by
FPL's chance of playing. A starter who went off early last time is already marked down by the
model (history: 12-18% start next), so when FPL then flags him the injury counts twice (Xhaka,
GW11: 0.36 × 75%). And a player FPL calls fully fit gets no credit for it. Fix: add the
pre-deadline flag (status, chance of playing) as features, fitted on the snapshots we have
captured since 2026-08-21. Test on gameweeks not yet played, since every past season lacks the
flags and 2026-27 GW2-10 is spent for minutes.

## E7. Refresh timing

The precompute is scheduled for 04:30 UTC but GitHub starts it around 12:00-13:10, so before an
11:00 Saturday deadline the newest projection is about 23 hours old. Fix: the snapshot Lambda
already knows the deadline and wakes every 3 hours; have it dispatch the precompute 2-4 hours
before. Needs a fine-grained GitHub token stored in AWS. Operational, not a model test.

## E9. Expected starters play less than projected

Found by the E3 retest. On players the model expected to play, it is too high at every position
(development: keepers −0.62 a game, defenders −0.35, midfielders −0.30, forwards −0.25). Cards account
for about 0.15 of the outfield gap and save rounding about 0.3 of the keepers'; the rest is the
minutes model being too sure a likely starter plays. Folded into E6, whose test should report this
bias before and after.

## E8. Penalty saves

+5 per saved penalty, no term: about +0.07 a game for keepers, roughly equal across keepers and
cancelled by their −0.08 in cards. Parked.

## E10. Clean sheets while on the pitch

**What is wrong.** FPL gives a clean sheet to a player who plays 60+ minutes if his team concedes
nothing *while he is on the pitch*. Production prices it as the team's full-match chance,
exp(−λ_opp), for every position. On 2023-26, midfielders who played 60+ and came off before 85
minutes kept a clean sheet 33.5% of the time: the full-match chance said 25.4%, the chance over
the minutes they played 32.8% (3,656 fixtures, the same in every season). Over every midfielder
who played 60+: 28.3% actual, 25.7% full match, 28.6% on the pitch.

**Defenders are different.** Defenders who came off before 85 kept clean sheets 25.0% of the time,
the full-match rate (25.2%), not the on-pitch one (32.1%). A defender comes off when his side is
chasing or hurt, so coming off goes with conceding, and for defenders the full-match chance is
right. Keepers almost never come off.

**Size and status.** Midfielders expected to start: clean-sheet points 0.140 a fixture projected,
0.156 awarded, about +0.016 a game, most for midfielders of strong defences who are often
withdrawn. It changes no pick, so it is parked. The fix when it is picked up: in the "plays 60+"
case, exp(−λ_opp × m / 90) with m from `full_game_minutes`, for midfielders only, judged on the
term as E5 was.
