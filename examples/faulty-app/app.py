import asyncio
import gc
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

requests = Counter("demo_http_requests_total", "Real work requests", ["service", "status"])
latency = Histogram(
    "demo_http_duration_seconds",
    "Real work latency",
    ["service"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10),
)
for status in ("200", "500"):
    requests.labels("faulty-app", status).inc(0)
mode = {"delay": 0.01, "errors": False}
allocations = []


async def workload():
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                await client.get("http://127.0.0.1:8080/work")
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(workload())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/work")
async def work():
    started = time.monotonic()
    await asyncio.sleep(mode["delay"])
    code = 500 if mode["errors"] else 200
    requests.labels("faulty-app", str(code)).inc()
    latency.labels("faulty-app").observe(time.monotonic() - started)
    return Response("intentional error" if code == 500 else "ok", status_code=code)


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


def authorize(token):
    expected = os.getenv("PULSE_DEMO_TOKEN", "")
    if (
        os.getenv("PULSE_DEMO_ENABLED") != "true"
        or len(expected) < 16
        or not token
        or not secrets.compare_digest(token, expected)
    ):
        raise HTTPException(
            403, "Fault injection is restricted to the authenticated demo environment"
        )


class Fault(BaseModel):
    mib: int = Field(default=160, ge=1, le=192)
    delay_seconds: float = Field(default=2, ge=0.1, le=5)


@app.post("/fault/{kind}")
async def fault(kind: str, body: Fault, x_demo_token: str | None = Header(default=None)):
    authorize(x_demo_token)
    if kind == "crash":
        logging.error("fault_injected=application_crash: application will exit with code 42")

        async def crash():
            await asyncio.sleep(0.3)
            os._exit(42)

        asyncio.create_task(crash())
    elif kind == "memory":
        allocations.clear()
        allocations.append(bytearray(body.mib * 1024 * 1024))
        logging.warning("fault_injected=memory_pressure: allocated %s MiB", body.mib)
    elif kind == "latency":
        mode["delay"] = body.delay_seconds
        logging.warning("fault_injected=api_latency: delay=%ss", body.delay_seconds)
    elif kind == "errors":
        mode["errors"] = True
    else:
        raise HTTPException(404, "Unknown scenario")
    return {"triggered": kind}


@app.post("/reset")
async def reset(x_demo_token: str | None = Header(default=None)):
    authorize(x_demo_token)
    mode.update(delay=0.01, errors=False)
    allocations.clear()
    gc.collect()
    logging.warning("demo_reset: fault state cleared")
    return {"reset": True}
