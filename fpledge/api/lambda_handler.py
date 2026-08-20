"""Lambda entrypoint: the same FastAPI app, behind a Function URL.

WHY LAMBDA AND NOT A CONTAINER. The API is genuinely light — importing it pulls in fastapi,
starlette and pydantic and nothing else. Every heavy dependency in this project (numpy, scipy,
duckdb, lightgbm, mlflow) belongs to the PRECOMPUTE, which runs on a schedule and writes an
artifact; the API only ever reads that artifact. So the serving path fits in a zip well under
Lambda's limit, cold-starts in a fraction of a second, and costs nothing at rest — where an
always-on container would bill by the hour to serve a site with no traffic yet.

boto3 is deliberately NOT bundled: the Lambda Python runtime provides it.

WHAT MANGUM DOES. Lambda speaks events; FastAPI speaks ASGI. Mangum translates one into the
other, so there are two entrypoints to one application rather than two applications — `uvicorn`
locally and in the Docker image, this handler in Lambda, both serving the identical `app`. If
those ever diverge, the thing tested is not the thing deployed.

`lifespan="off"` because the app registers no startup or shutdown hooks. Left on, Mangum runs
the ASGI lifespan protocol on every cold start for no benefit, and any future hook that assumed
a long-lived process would run per-invocation instead — which is worth failing loudly on rather
than half-supporting.
"""

from __future__ import annotations

from mangum import Mangum

from .main import app

handler = Mangum(app, lifespan="off")
