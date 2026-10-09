"""Bounded, authenticated lab workload. No host control or production data."""

import asyncio
import gc
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field

SERVICE = os.environ.get("LAB_SERVICE", "demo-api")
TOKEN = os.environ.get("PULSE_LAB_TOKEN", "")
STICKY = Path("/data/health-fault.json")
TELEMETRY_LOSS = Path("/data/telemetry-loss.json")
requests = Counter(
    "demo_http_requests_total", "Completed lab HTTP requests", ["service", "endpoint", "status"]
)
durations = Histogram(
    "demo_http_duration_seconds",
    "Actual request duration",
    ["service", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1, 1.5, 2, 2.5, 3, 5),
)
active = Gauge("demo_http_active_requests", "In-flight requests", ["service"])
mode = {"errors": 0.0, "delay": 0.005}
allocations = []
allocation_task = None
for endpoint in ("orders", "search"):
    for code in ("200", "500"):
        requests.labels(SERVICE, endpoint, code).inc(0)


def emit(event, **data):
    print(json.dumps({"at": time.time(), "service": SERVICE, "event": event, **data}), flush=True)


async def workload():
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        while True:
            for endpoint in ("orders", "search"):
                try:
                    await client.get(f"http://127.0.0.1:8080/api/demo/{endpoint}")
                except httpx.HTTPError:
                    pass
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(workload())
    emit("worker_started", synthetic_jobs=True)
    yield
    task.cancel()
    if allocation_task:
        allocation_task.cancel()
    await asyncio.gather(
        task, *([allocation_task] if allocation_task else []), return_exceptions=True
    )


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    if await asyncio.to_thread(STICKY.exists):
        return Response("persistent health failure", status_code=503)
    return {"status": "ok", "service": SERVICE}


@app.get("/api/demo/{endpoint}")
async def request(endpoint: str):
    if endpoint not in ("orders", "search"):
        raise HTTPException(404)
    began = time.monotonic()
    active.labels(SERVICE).inc()
    try:
        await asyncio.sleep(mode["delay"] if endpoint == "search" else 0.005)
        code = (
            500
            if endpoint == "orders" and secrets.randbelow(10000) < mode["errors"] * 10000
            else 200
        )
        elapsed = time.monotonic() - began
        requests.labels(SERVICE, endpoint, str(code)).inc()
        durations.labels(SERVICE, endpoint).observe(elapsed)
        emit(
            "request_failed" if code == 500 else "request_completed",
            endpoint=endpoint,
            status=code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return Response(
            json.dumps(
                {"orders": [{"id": 1, "item": "synthetic"}]}
                if endpoint == "orders"
                else {"matches": ["synthetic"]}
            ),
            status_code=code,
            media_type="application/json",
        )
    finally:
        active.labels(SERVICE).dec()


@app.get("/metrics")
async def metrics():
    if await asyncio.to_thread(TELEMETRY_LOSS.exists):
        return Response("lab metrics temporarily unavailable", status_code=503)
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


class Fault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mib: int = Field(default=160, ge=1, le=176)
    delay_seconds: float = Field(default=2, ge=0.1, le=3)
    error_ratio: float = Field(default=1, ge=0, le=1)


async def allocate(mib):
    for _ in range(mib // 8):
        allocations.append(bytearray(8 * 1024 * 1024))
        emit("memory_allocation", allocated_mib=len(allocations) * 8)
        await asyncio.sleep(0.15)


@app.post("/control/{command}")
async def control(command: str, body: Fault, x_lab_token: str | None = Header(default=None)):
    global allocation_task
    if (
        os.environ.get("PULSE_LAB_ENABLED") != "true"
        or len(TOKEN) < 16
        or not x_lab_token
        or not secrets.compare_digest(TOKEN, x_lab_token)
    ):
        raise HTTPException(403, "Authenticated lab access required")
    if command == "crash":
        emit("application_crash", exit_code=42, last_job="synthetic-job")

        async def crash():
            await asyncio.sleep(0.3)
            os._exit(42)

        asyncio.create_task(crash())
    elif command == "memory":
        if allocation_task and not allocation_task.done():
            raise HTTPException(409, "Allocation already running")
        allocations.clear()
        allocation_task = asyncio.create_task(allocate(body.mib))
    elif command == "errors":
        mode["errors"] = body.error_ratio
        emit("error_workload_enabled", ratio=body.error_ratio)
    elif command == "latency":
        mode["delay"] = body.delay_seconds
        emit("delay_enabled", seconds=body.delay_seconds)
    elif command == "sticky":
        await asyncio.to_thread(STICKY.write_text, "{}")
        emit("persistent_health_fault", survives_restart=True)
    elif command == "telemetry_off":
        await asyncio.to_thread(TELEMETRY_LOSS.write_text, "{}")
        emit("telemetry_disabled", path="/metrics", workloads_unchanged=True)
    elif command == "telemetry_on":
        await asyncio.to_thread(TELEMETRY_LOSS.unlink, missing_ok=True)
        emit("telemetry_restored", path="/metrics")
    elif command in ("reset", "reset_memory", "reset_errors", "reset_latency"):
        if command in ("reset", "reset_memory"):
            if allocation_task:
                allocation_task.cancel()
                await asyncio.gather(allocation_task, return_exceptions=True)
            allocation_task = None
            allocations.clear()
            gc.collect()
        if command in ("reset", "reset_errors"):
            mode["errors"] = 0.0
        if command in ("reset", "reset_latency"):
            mode["delay"] = 0.005
        if command == "reset":
            await asyncio.to_thread(STICKY.unlink, missing_ok=True)
            await asyncio.to_thread(TELEMETRY_LOSS.unlink, missing_ok=True)
        emit("lab_reset", control=command)
    elif command != "status":
        raise HTTPException(404, "Unknown control")
    return {"accepted": True, "command": command, "service": SERVICE}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False)
