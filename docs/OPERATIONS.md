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

### Where the raw zone lives

Local disk by default. Set `FPLEDGE_RAW_URI` and every capture writes to S3 instead, with no
change to any capture script:

```sh
export FPLEDGE_RAW_URI=s3://fpledge-data-546712138633/raw
pip install -e ".[aws]"                    # boto3 is only needed for this path
python scripts/verify_landing.py           # write → exists → read → list, against the real bucket
```

**Run the verifier before pointing a capture at a new backend.** It writes a throwaway object
under `source=_verify`, reads it back, compares it byte for byte and lists it — the four
operations every capture depends on. The first time a backend is exercised should not be at
06:00 on a deadline morning, unattended, on the one run that mattered.

Turn on **S3 versioning** on the bucket. The raw zone is irreplaceable and a bad sync would
otherwise be unrecoverable.

### IN THE CLOUD (2026-08-20): Lambda + EventBridge — the laptop is no longer load-bearing

The captures now run on AWS, writing straight to S3 through the same code paths that run
locally (`main(argv)` driven by `scripts/lambda_captures.py` — one implementation, two
schedulers; a parallel "cloud version" would drift from the tested one within a month).

| function | schedule (UTC) | handler | verified |
|---|---|---|---|
| `fpledge-snapshot` | `rate(3 hours)` | `scripts.lambda_captures.snapshot_handler` | gated skip in 133ms; forced capture landed bootstrap+fixtures+index in S3 in 1.7s |
| `fpledge-news` | `cron(0 6,12,18 * * ? *)` | `scripts.lambda_captures.news_handler` | full 4-source run in 76s; live `/news` served the new digest minutes later |

Both: python3.13 / **arm64** / 512MB, role `fpledge-captures-lambda` (logs + read/write on the
data bucket only), env `FPLEDGE_RAW_URI` + `FPLEDGE_SERVING_URI`. Deploy an update:

```bash
./scripts/build_lambda.sh     # builds fpledge-captures.zip (and the API zip)
AWS_PROFILE=fpledge aws lambda update-function-code --function-name fpledge-snapshot \
  --zip-file fileb://build/fpledge-captures.zip
AWS_PROFILE=fpledge aws lambda update-function-code --function-name fpledge-news \
  --zip-file fileb://build/fpledge-captures.zip
```

Smoke-test without waiting for a schedule or a deadline window:

```bash
AWS_PROFILE=fpledge aws lambda invoke --function-name fpledge-snapshot \
  --payload '{"force":true}' --cli-binary-format raw-in-base64-out /tmp/out.json
```

The full pre-cloud history was published to S3 with locators a Lambda can resolve
(`scripts/migrate_index_to_s3.py`, after an `aws s3 sync data/raw`). Verified the way it has to
be verified — with **no local files at all**: 14 news captures, the full 2,421-item corpus and
568 availability entries all resolved from S3 alone.

**The launchd agents below stay loaded through GW1 as belt-and-braces** — cloud and local
captures dedupe by ingest timestamp, and the eval picks the best pre-deadline snapshot, so
running both costs nothing. After GW1 lands:

1. `aws s3 sync data/raw s3://fpledge-data-546712138633/raw` and re-run
   `migrate_index_to_s3.py` once, so any launchd-only capture reaches S3.
2. `launchctl bootout gui/$UID/com.fpledge.snapshot` and same for `.news`, delete the plists.
3. `FPLEDGE_RAW_URI` in the shell profile if local runs should also write to S3 from then on.

### Alerting (2026-08-20): a dead schedule must not look like a quiet day

Four CloudWatch alarms notify `fpledge-alerts` (SNS -> email; the subscription needed a manual
confirmation click):

| alarm | fires when | why this shape |
|---|---|---|
| `fpledge-{snapshot,news}-errors` | any run fails (Sum(Errors) > 0 over 1h) | captures are unrepeatable; waiting for a pattern means losing data while waiting |
| `fpledge-{snapshot,news}-not-running` | zero invocations in 24h | a broken EventBridge permission produces no errors and no logs — absence is the only signal, and Lambda emits NO metric when never invoked, so the alarm treats missing data as breaching |

Born from a real near-miss: a timezone misread suggested the snapshot schedule had silently
failed, and the honest answer to "would anything have told us?" was no.

### Installed on macOS via launchd, not cron (2026-08-20)

`snapshot` and `capture_news` are **live** as user LaunchAgents. Both were verified by
`launchctl kickstart`: snapshot found the GW1 deadline and skipped correctly (outside its 12h
window, exit 0); news captured all 20 clubs and wrote the index.

```sh
~/Library/LaunchAgents/com.fpledge.snapshot.plist   # 00:00, 06:00, 12:00, 18:00
~/Library/LaunchAgents/com.fpledge.news.plist       # 07:00, 13:00, 19:00

launchctl list | grep fpledge                       # loaded? second column is last exit code
launchctl kickstart -k gui/$UID/com.fpledge.news    # run one now
tail -f data/logs/news.log                          # both agents log to data/logs/
```

**Two reasons it is launchd rather than the cron block above.** First, macOS refuses
`crontab` edits without Full Disk Access — the install fails with `Operation not permitted`.
Second, and the one that actually matters: **if the machine is asleep at the scheduled time,
cron silently skips the run and launchd executes it on wake.** On a laptop, with data that
cannot be back-filled at any price, a silent skip is the expensive failure mode.

It is still a laptop. A machine that is shut down over a deadline misses that gameweek
permanently, and no scheduler fixes that — only moving the captures to a host that stays up
does. Until then, check `data/logs/` after each deadline rather than assuming.

`capture_props` is deliberately **not** installed: it has no API key and its live path has never
executed. Prove it manually once before scheduling code that has never run.

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
