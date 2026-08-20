# Deploying

Four values and a container. The advisor stays **off** — no `ANTHROPIC_API_KEY` means `/advise`
reports itself unavailable and the UI says so, which is a supported and tested state (§6).

## 1. The four values that block a deploy

These have been the blocking list since 2026-08-03. Three need a human decision, not a commit.

| what | where | needs |
|---|---|---|
| `NEXT_PUBLIC_SITE_URL` | env for the web app | **the domain**, once chosen. Everything currently emits `http://localhost:3000` into canonical URLs, OG tags, `robots.txt` and `sitemap.xml` |
| Contact email | `web/src/app/privacy/page.tsx`, `terms/page.tsx` | **an address you will read.** Both say `[ADD CONTACT EMAIL BEFORE DEPLOY]` |
| Governing jurisdiction | `web/src/app/terms/page.tsx` | **a jurisdiction.** Says `[ADD GOVERNING JURISDICTION BEFORE DEPLOY]` |
| `FPLEDGE_CORS_ORIGINS` | env for the API | the web app's origin. Defaults to `*` |

**And a fifth, which is not a config value: the name.** "FPL Edge" uses FPL's own abbreviation
and the Premier League word mark. Free to change today; expensive once a shared `?s=` squad code
is in circulation — and shareable squads are the only growth mechanism the product has.

## 2. Two services

| | |
|---|---|
| **API** | this repo's `Dockerfile`. FastAPI on 8000, reads `data/serving/gw{N}.json`, never fits a model |
| **Web** | `web/`, Next.js 16. Vercel is the path of least resistance; it needs `NEXT_PUBLIC_SITE_URL` and `NEXT_PUBLIC_API_URL` |

```bash
docker build -t fpledge-api .
docker run -p 8000:8000 \
  -e FPLEDGE_CORS_ORIGINS=https://your-domain \
  -v fpledge-data:/app/data \
  fpledge-api
```

> **`data/` must be a named volume, not a container layer.** The captures write there and their
> contents are irreplaceable — the FPL API, the odds API and news feeds all serve only the
> present. A deploy that recreates the container without a volume discards a season of snapshots
> and there is no way to get them back. See `docs/OPERATIONS.md`.

> **The image builds and serves — verified in CI, 2026-08-19 (linux/amd64).** The `docker` job
> in `.github/workflows/ci.yml` builds it, starts it, and polls `/health` until it answers:
> `healthy after 2s`, `{"status":"ok","available_gws":[]}`. It boots with **no data mounted**,
> which is the case that matters on a first deploy — `available_gws()` returns `[]` rather than
> raising, so the container is healthy before the first precompute has ever run.
>
> Still unverified: **the volume**. CI proves the image runs, not that `data/` survives a
> redeploy — and that is the failure that costs a season of captures. Mount it, redeploy once,
> and confirm the snapshots are still there before trusting the deployment.

## 3. One worker, on purpose

The advisor's rate limiter is in-process, so a second worker doubles the ceiling (§6). Run a
single process until quota lives in a database. This costs nothing today — every route except
`/advise` is a read from a JSON file.

## 4. Order of operations

1. **Name it.** Everything else bakes the choice in.
2. Point a domain at it; set `NEXT_PUBLIC_SITE_URL` and `FPLEDGE_CORS_ORIGINS`.
3. Fill the contact email and jurisdiction.
4. Deploy both services. Confirm `/health`, then `/`, `/squad`, `/model`.
5. **Only then** schedule anything — `docs/OPERATIONS.md`. The precompute now exits non-zero on a
   degraded fit, which is what makes scheduling safe.

## 5. Preseason reality

Until the **2026-08-21** deadline the FPL API exposes no manager squads, so every real
`/team/{id}` 404s and `/team/0` is the only working squad demo. **`/squad` is the front door** —
it needs no team id, works today, and is why launching before the season starts is viable at all.

On 21 August `/team/{id}` meets real manager data for the first time ever. Treat that as a second
launch, not a milestone that passes on its own.
