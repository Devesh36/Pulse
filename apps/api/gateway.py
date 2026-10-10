"""Private Docker capability gateway. Never publish this port or expose its token to a model."""

import asyncio
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import docker
from docker.errors import DockerException, NotFound
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from pulse.core.redaction import redact
from pulse.project.guard import parent_guard
from pulse.tools.docker_adapter import SDKAdapter, run_sdk
from pydantic import BaseModel, Field

TOKEN = os.getenv("PULSE_ADAPTER_TOKEN", "")
JOURNAL = os.getenv("PULSE_GATEWAY_JOURNAL", "/data/gateway.db")
adapter: SDKAdapter | None = None
mutation_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    global adapter
    if len(TOKEN) < 16:
        raise RuntimeError("PULSE_ADAPTER_TOKEN must contain at least 16 characters")
    await asyncio.to_thread(os.makedirs, os.path.dirname(JOURNAL) or ".", exist_ok=True)
    with sqlite3.connect(JOURNAL) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, container TEXT, kind TEXT, status TEXT, at REAL)"
        )
    client = docker.from_env(timeout=10)
    await asyncio.to_thread(client.ping)
    adapter = SDKAdapter(
        client,
        os.getenv("PULSE_RESOURCE_PROJECT"),
        os.getenv("PULSE_LAB_TOKEN", ""),
        resource_root=os.getenv("PULSE_RESOURCE_ROOT"),
        services=json.loads(os.environ["PULSE_RESOURCE_SERVICES"])
        if "PULSE_RESOURCE_SERVICES" in os.environ
        else None,
    )
    try:
        with parent_guard():
            yield
    finally:
        client.close()


async def auth(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(401, "Gateway authentication required")


app = FastAPI(
    lifespan=lifespan, dependencies=[Depends(auth)], docs_url=None, redoc_url=None, openapi_url=None
)
CID = Annotated[str, Path(pattern=r"^[a-f0-9]{12,64}$")]


def get_adapter() -> SDKAdapter:
    if adapter is None:
        raise HTTPException(503, "Gateway is not initialized")
    return adapter


async def call(fn, *args):
    try:
        return redact(await asyncio.wait_for(run_sdk(fn, *args), timeout=12))
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except NotFound as e:
        raise HTTPException(404, "Container no longer exists") from e
    except (DockerException, TimeoutError) as e:
        raise HTTPException(503, "Docker operation failed or timed out") from e


@app.get("/containers")
async def containers():
    return await call(get_adapter().discover)


@app.get("/containers/{cid}")
async def inspect(cid: CID):
    return await call(get_adapter().inspect, cid)


@app.get("/containers/{cid}/logs")
async def logs(
    cid: CID, since: int = Query(1800, ge=1, le=86400), limit: int = Query(100, ge=1, le=300)
):
    return await call(get_adapter().logs, cid, since, limit)


@app.get("/containers/{cid}/metrics")
async def metrics(cid: CID):
    return await call(get_adapter().metrics, cid)


@app.get("/containers/{cid}/events")
async def events(
    cid: CID, since: int = Query(1800, ge=1, le=86400), limit: int = Query(100, ge=1, le=300)
):
    return await call(get_adapter().events, cid, since, limit)


class LabFault(BaseModel):
    model_config = {"extra": "forbid"}
    mib: int = Field(default=160, ge=1, le=176)
    delay_seconds: float = Field(default=2, ge=0.1, le=3)
    error_ratio: float = Field(default=1, ge=0, le=1)


@app.post("/lab/{cid}/{command}")
async def lab_control(
    cid: CID,
    command: Literal[
        "crash",
        "memory",
        "errors",
        "latency",
        "sticky",
        "reset",
        "status",
        "telemetry_off",
        "telemetry_on",
    ],
    body: LabFault,
):
    if (
        os.getenv("PULSE_LAB_ENABLED") != "true"
        or os.getenv("PULSE_GATEWAY_DISABLED", "false").lower() == "true"
    ):
        raise HTTPException(403, "Lab controls disabled")
    return await call(get_adapter().lab_control, cid, command, body.model_dump())


class Mutation(BaseModel):
    action_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


@app.post("/containers/{cid}/{kind}")
async def mutate(
    cid: CID,
    kind: Literal["start", "restart", "reset_memory", "reset_errors", "reset_latency"],
    body: Mutation,
):
    if os.getenv("PULSE_GATEWAY_DISABLED", "false").lower() == "true":
        raise HTTPException(403, "Gateway emergency disable is active")
    async with mutation_lock:
        with sqlite3.connect(JOURNAL) as db:
            try:
                db.execute(
                    "INSERT INTO actions VALUES (?, ?, ?, 'claimed', ?)",
                    (body.action_id, cid, kind, time.time()),
                )
            except sqlite3.IntegrityError as e:
                raise HTTPException(
                    409, "Action was already claimed; inspect outcome before proposing a new action"
                ) from e
        # Claim persists before execution. Timeout/crash has an uncertain outcome and is never retried.
        result = await call(get_adapter().mutate, cid, kind)
        with sqlite3.connect(JOURNAL) as db:
            db.execute("UPDATE actions SET status='executed' WHERE id=?", (body.action_id,))
        return result
