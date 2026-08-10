# Operations runbook

Everything that has to run on a schedule, in one place. The handoff explains *why* each exists;
this says what to run and what failure looks like.

> **The one rule.** Three of these captures are **irreplaceable**: the FPL API, the odds API and
> news feeds all serve only the present. A week not captured cannot be bought back at any price
> (props) or at all (snapshots, news). If something has to be skipped, skip the precompute — it
> can be re-run.

## The schedule

```cron
# --- captures: start 2026-08-21, the GW1 deadline -----------------------------------------
# Pre-deadline FPL state: ep_next, chance_of_playing, status, news.  §17
0  */6 *  *  *   cd /path/to/repo && .venv/bin/python scripts/snapshot.py --if-near-deadline

# Anytime-goalscorer prices, free tier (~10 credits/gameweek against 500/month).  §22
15 */6 *  *  *   cd /path/to/repo && .venv/bin/python scripts/capture_props.py --if-near-deadline

# Club news feeds. DAILY — see the note below, this one is different.  §29
0  7,13,19 * * * cd /path/to/repo && .venv/bin/python scripts/capture_news.py

# --- serving ------------------------------------------------------------------------------
# Weekly refresh of the artifact the API reads. Exits NON-ZERO if degraded.  §4
30 4  *  *  2    cd /path/to/repo && .venv/bin/python scripts/precompute.py 1 8
```

**Why news is daily and the other two are not.** Snapshot and props want a single reading as
close to the deadline as possible, so a six-hourly cron with `--if-near-deadline` yields roughly
one useful capture per gameweek and does nothing the rest of the time. News feeds are a **rolling
window** of ~4–24 items that fall off permanently, so a weekly run misses the Tuesday press
conference entirely. Items dedupe by guid, so running it often costs nothing.

## Before the first run

| | |
|---|---|
| `ODDS_API_KEY` | free key from the-odds-api.com. **Without it `capture_props.py` exits 2** rather than writing an empty file |
| **run once**: `make capture-props ARGS=--list-markets` | confirms the goalscorer market key. A wrong key returns an empty bookmaker list — indistinguishable from "no book has priced it yet" — and would capture nothing all season while looking like a quiet week |
| `data/` must persist | every capture writes there and it is gitignored. In a container this is a volume, not an image layer |

## What failure looks like

| script | healthy | degraded | how it tells you |
|---|---|---|---|
| `precompute.py` | `health: OK`, exit 0 | dropped source season, `fallback_fixtures > 3`, `< 400` records, `> 3` unmapped teams | prints each problem and **exits 1**. `--allow-degraded` overrides |
| `snapshot.py` | captures, or prints "outside the window" | — | writes one line to `data/raw/snapshot_index.jsonl` per capture |
| `capture_props.py` | `credits: used N, remaining M` | every fixture returns zero bookmakers | **exits 1** and says the market key may be wrong |
| `capture_news.py` | `N items from 20/20 clubs` | a club feed 404s | names the failed clubs; exits 1 only if **all** fail |

**Three unmapped teams is normal, not a fault** — exactly that many clubs are promoted each
season and a promoted club has no top-flight history to map. The check fires above three, which
means the name mapping broke rather than that four teams came up.

## Is the news feed worth anything? — `make eval-news`

Scores what the extractor claims against FPL's own `status`/`news` field, which is a **free
labelled set that exists today**. Needs no API key and no snapshot history.

| number | means | read it as |
|---|---|---|
| precision | of players we flag injured, how many FPL confirms | the dangerous direction — a false "X is out" is worse than silence |
| recall | of players FPL flags, how many the feed mentions | a property of the SOURCE, not the extractor |
| **additive** | rotation cues on players FPL does **not** flag | **the only category worth money** — injury is free, rotation is the whole commercial case |

Two questions were being conflated. *How big is the prize* needs the snapshot residual and waits
for 2026-08-21. *Can our feed claim any of it* needed neither and was answerable all along.

## Checking on it

```bash
wc -l data/raw/snapshot_index.jsonl data/raw/props_index.jsonl data/raw/news_index.jsonl
tail -1 data/raw/snapshot_index.jsonl | python -m json.tool
```

Each index is one line per run: when it fired, which gameweek, how long before the deadline, and
how much it got. "What do we have?" should never mean walking the partition tree.

## Roughly when each starts paying

| | |
|---|---|
| **GW1 (2026-08-21)** | all three captures must be live. `/team/{id}` also meets real manager data for the first time — treat it as a second launch |
| **~GW10 (late Oct)** | enough props to test whether they beat our xP; enough snapshots to measure the availability residual, which prices the €258/month rotation-feed question (§29) |
| **end of season (May)** | one extra snapshot **after** the final gameweek — `average_entry_score` for GW38 only appears afterwards (§27) |
