import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from pulse.core.config import Config, get_config
from pulse.core.redaction import redact
from pulse.core.remediation import PolicyError
from pulse.core.runtime import Runtime
from pulse.core.schemas import Approval, ChatRequest, Dismissal, Login, ServicePermission, Settings
from pulse.db.models import (
    Audit,
    Event,
    Incident,
    LabEvaluation,
    Remediation,
    Sample,
    Service,
    Setting,
    ToolExecution,
)
from pulse.db.store import Store, serialize
from pulse.lab.catalog import SCENARIOS
from pulse.lab.quality import quality_review
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult


class JsonLog(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "at": time.time(),
                "level": record.levelname,
                "message": record.getMessage(),
                **{
                    k: getattr(record, k) for k in ("operation", "error_type") if hasattr(record, k)
                },
            }
        )


class HealthView(BaseModel):
    status: str
    docker: str
    last_poll: float | None
    llm_configured: bool


class OverviewView(BaseModel):
    monitored_services: int
    healthy_services: int
    active_incidents: int
    awaiting_approval: int
    resolved_last_24h: int


class ServiceView(BaseModel):
    id: str
    container_id: str
    name: str
    monitored: bool
    remediation_allowed: bool
    snapshot: dict
    last_seen: float
    metrics: dict | None = None


class IncidentView(BaseModel):
    id: str
    service_id: str
    kind: str
    title: str
    severity: str
    state: str
    created_at: float
    updated_at: float
    detection: dict
    diagnosis: dict | None
    verification: dict | None


class SettingsView(BaseModel):
    runtime: Settings
    model: str
    provider_configured: bool
    api_base: str | None
    provider_note: str


def create_app(config: Config | None = None, store=None, runtime=None):
    config = config or get_config()
    store = store or Store(config.database_url)
    runtime = runtime or Runtime(store, config)
    limiter = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        if len(config.admin_token) < 16 or len(config.adapter_token) < 16:
            raise RuntimeError(
                "Set unique PULSE_ADMIN_TOKEN and PULSE_ADAPTER_TOKEN (at least 16 characters); run scripts/setup-env.py"
            )
        if secrets.compare_digest(config.admin_token, config.adapter_token):
            raise RuntimeError("Admin and gateway tokens must be different")
        with store.session() as db:
            db.execute(select(Setting).limit(1))  # Require migrations before boot.
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLog())
        logger = logging.getLogger("pulse")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        await runtime.start()
        yield
        await runtime.stop()
        logger.removeHandler(handler)

    app = FastAPI(title="Pulse API", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.runtime = store, runtime
    app.state.draining = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def rate_limit(request, call_next):
        ip = request.client.host if request.client else "unknown"
        key = (
            ip,
            "login"
            if request.url.path.endswith("/session") and request.method == "POST"
            else "api",
        )
        now = time.monotonic()
        entries = limiter[key]
        while entries and entries[0] < now - 60:
            entries.popleft()
        if len(entries) >= (5 if key[1] == "login" else 180):
            return Response(
                status_code=429,
                content='{"detail":"Rate limit exceeded"}',
                media_type="application/json",
                headers={"Retry-After": "60"},
            )
        entries.append(now)
        return await call_next(request)

    async def authorized(request: Request, authorization: Annotated[str | None, Header()] = None):
        bearer = authorization and secrets.compare_digest(
            authorization, f"Bearer {config.admin_token}"
        )
        test_principal = (
            config.lab_enabled
            and len(config.lab_test_token) >= 16
            and authorization
            and secrets.compare_digest(authorization, f"Bearer {config.lab_test_token}")
        )
        if test_principal:
            parts = request.url.path.strip("/").split("/")
            allowed = {
                "lab",
                "services",
                "incidents",
                "remediations",
                "settings",
                "health",
                "audit",
            }
            if len(parts) < 3 or parts[2] not in allowed:
                raise HTTPException(403, "Lab test principal cannot access this endpoint")
            if len(parts) >= 4 and parts[2] in {"services", "incidents", "remediations"}:
                with store.session() as db:
                    model = {
                        "services": Service,
                        "incidents": Incident,
                        "remediations": Remediation,
                    }[parts[2]]
                    resource = db.get(model, parts[3])
                    scoped = (
                        resource
                        if parts[2] == "services"
                        else db.get(Service, resource.service_id)
                        if resource
                        else None
                    )
                    labels = scoped.snapshot.get("labels", {}) if scoped else {}
                    if (
                        labels.get("pulse.lab") != "pulse-lab"
                        or labels.get("com.docker.compose.project") != config.lab_project
                    ):
                        raise HTTPException(
                            403, "Lab test principal is restricted to lab resources"
                        )
            bearer = True
        request.state.actor = "lab-test" if test_principal else "operator"
        session = request.cookies.get("pulse_session", "")
        cookie_ok = False
        try:
            timestamp, signature = session.split(".", 1)
            expected = hmac.new(
                config.admin_token.encode(), timestamp.encode(), hashlib.sha256
            ).hexdigest()
            cookie_ok = 0 <= time.time() - int(timestamp) < 43200 and secrets.compare_digest(
                signature, expected
            )
        except (ValueError, TypeError):
            pass
        if not bearer and not cookie_ok:
            raise HTTPException(401, "Sign in with the local administrator token")
        if (
            not bearer
            and request.method in ("POST", "PATCH", "DELETE")
            and request.headers.get("origin") != config.web_origin
        ):
            raise HTTPException(403, "Origin check failed")

    def require_service(sid, monitored=False):
        with store.session() as db:
            row = db.get(Service, sid)
        if not row:
            raise HTTPException(404, "Service not found")
        if monitored and not row.monitored:
            raise HTTPException(403, "Service monitoring is disabled")
        return row

    def require_incident(iid):
        with store.session() as db:
            row = db.get(Incident, iid)
        if not row:
            raise HTTPException(404, "Incident not found")
        require_service(row.service_id)
        return row

    @app.get("/api/v1/health", response_model=HealthView)
    async def health():
        return {
            "status": "ok",
            "docker": runtime.adapter_status,
            "last_poll": runtime.last_poll,
            "llm_configured": bool(config.llm_model) and config.llm_model != "mock/evidence",
        }

    @app.post("/api/v1/session")
    async def login(body: Login, request: Request, response: Response):
        origin = request.headers.get("origin")
        if origin and origin != config.web_origin:
            raise HTTPException(403, "Origin check failed")
        if not secrets.compare_digest(body.token, config.admin_token):
            raise HTTPException(401, "Invalid administrator token")
        stamp = str(int(time.time()))
        signature = hmac.new(
            config.admin_token.encode(), stamp.encode(), hashlib.sha256
        ).hexdigest()
        response.set_cookie(
            "pulse_session",
            f"{stamp}.{signature}",
            httponly=True,
            samesite="strict",
            max_age=43200,
            secure=config.web_origin.startswith("https://"),
            path="/",
        )
        return {"authenticated": True}

    @app.delete("/api/v1/session", dependencies=[Depends(authorized)])
    async def logout(response: Response):
        response.delete_cookie("pulse_session", path="/")
        return {"authenticated": False}

    auth = [Depends(authorized)]

    if config.project_context:
        from pulse.project.web import attach

        attach(app, config, auth)

    def lab_service(name):
        if not config.lab_enabled:
            raise HTTPException(403, "Incident lab is disabled; start the isolated lab stack")
        with store.session() as db:
            rows = db.scalars(select(Service)).all()
        for row in rows:
            labels = row.snapshot.get("labels", {})
            if (
                labels.get("pulse.lab") == "pulse-lab"
                and labels.get("com.docker.compose.project") == config.lab_project
                and labels.get("com.docker.compose.service") == name
                and time.time() - row.last_seen < 30
            ):
                return row
        raise HTTPException(503, "Lab service has not been freshly discovered")

    @app.get("/api/v1/lab/status", dependencies=auth)
    async def lab_status():
        with store.session() as db:
            rows = [
                serialize(s)
                for s in db.scalars(select(Service))
                if s.snapshot.get("labels", {}).get("pulse.lab") == "pulse-lab"
                and s.snapshot.get("labels", {}).get("com.docker.compose.project")
                == config.lab_project
                and time.time() - s.last_seen < 30
            ]
        return {
            "enabled": config.lab_enabled,
            "project": config.lab_project,
            "services": rows,
            "scenarios": [{"id": k, **v} for k, v in SCENARIOS.items()],
            "docker": runtime.adapter_status,
            "at": time.time(),
        }

    from apps.api.gateway import LabFault

    @app.post("/api/v1/lab/faults/{scenario}", dependencies=auth)
    async def lab_fault(scenario: str, body: LabFault):
        if scenario not in SCENARIOS:
            raise HTTPException(404, "Unknown lab scenario")
        spec = SCENARIOS[scenario]
        row = lab_service(spec["service"])
        try:
            result = await runtime.adapter.lab_control(
                row.container_id, spec["control"], body.model_dump()
            )
        except Exception as error:
            raise HTTPException(
                503, "Lab control failed; inspect the isolated lab service"
            ) from error
        store.audit(
            "lab.fault_injected", row.id, {"scenario": scenario, "parameters": body.model_dump()}
        )
        store.event("lab.fault_injected", {"scenario": scenario, "service_id": row.id})
        return {**result, "service_id": row.id, "injected_at": time.time()}

    @app.post("/api/v1/lab/reset", dependencies=auth)
    async def lab_reset():
        if not config.lab_enabled:
            raise HTTPException(403, "Incident lab is disabled")
        with store.session() as db:
            active = db.scalar(
                select(Incident.id).where(
                    Incident.kind != "question",
                    Incident.state.in_(
                        [
                            "DETECTED",
                            "INVESTIGATING",
                            "DIAGNOSED",
                            "AWAITING_APPROVAL",
                            "REMEDIATING",
                            "VERIFYING",
                        ]
                    ),
                )
            )
        if active:
            raise HTTPException(
                409,
                "Review, cancel, or dismiss active lab incidents before an explicit cleanup reset",
            )
        for name in ("demo-api", "demo-worker"):
            row = lab_service(name)
            try:
                await runtime.adapter.lab_control(row.container_id, "reset")
            except Exception as error:
                raise HTTPException(
                    503, "Reset requires running lab services; use pulse lab reset"
                ) from error
            store.audit("lab.reset", row.id, {})
        return {"reset": True}

    class EvaluationInput(BaseModel):
        scenario: str = Field(max_length=80)
        report: dict = Field(max_length=100)

    class TelemetryControl(BaseModel):
        model_config = {"extra": "forbid"}
        enabled: bool

    @app.post("/api/v1/lab/telemetry/{sid}", dependencies=auth)
    async def lab_telemetry(sid: str, body: TelemetryControl, request: Request):
        row = require_service(sid, monitored=True)
        labels = row.snapshot.get("labels", {})
        if (
            not config.lab_enabled
            or labels.get("pulse.lab") != "pulse-lab"
            or labels.get("com.docker.compose.project") != config.lab_project
            or labels.get("com.docker.compose.service") not in ("demo-api", "demo-worker")
        ):
            raise HTTPException(
                403, "Telemetry controls require the selected authorized lab resource"
            )
        command = "telemetry_on" if body.enabled else "telemetry_off"
        try:
            result = await runtime.adapter.lab_control(row.container_id, command)
        except Exception as error:
            raise HTTPException(503, "Selected lab metrics control failed") from error
        store.audit(
            "lab.telemetry_restored" if body.enabled else "lab.telemetry_interrupted",
            row.id,
            {"path": "/metrics", "enabled": body.enabled},
            actor=request.state.actor,
        )
        store.event(
            "lab.telemetry_changed",
            {"service_id": sid, "enabled": body.enabled, "path": "/metrics"},
        )
        return {**result, "service_id": sid, "enabled": body.enabled}

    @app.get("/api/v1/lab/evaluations", dependencies=auth)
    async def lab_evaluations():
        with store.session() as db:
            return [
                serialize(r)
                for r in db.scalars(
                    select(LabEvaluation).order_by(LabEvaluation.at.desc()).limit(50)
                )
            ]

    @app.post("/api/v1/lab/evaluations", dependencies=auth)
    async def lab_evaluation(body: EvaluationInput):
        if not config.lab_enabled or body.scenario not in SCENARIOS:
            raise HTTPException(403, "Evaluation records require a known lab scenario")
        if len(json.dumps(body.report)) > 500000:
            raise HTTPException(413, "Evaluation report is too large")
        with store.session.begin() as db:
            row = LabEvaluation(scenario=body.scenario, report=redact(body.report))
            db.add(row)
            db.flush()
        store.audit("lab.evaluation_recorded", row.id, {"scenario": body.scenario})
        return serialize(row)

    @app.get("/api/v1/lab/quality", dependencies=auth)
    async def lab_quality():
        # Bound each scenario independently so a busy scenario cannot hide others.
        with store.session() as db:
            records = [
                serialize(row)
                for scenario in SCENARIOS
                for row in db.scalars(
                    select(LabEvaluation)
                    .where(LabEvaluation.scenario == scenario)
                    .order_by(LabEvaluation.at.desc(), LabEvaluation.id.desc())
                    .limit(2)
                )
            ]
        return quality_review(records)

    @app.post("/api/v1/incidents/{iid}/cancel", dependencies=auth)
    async def cancel_investigation(iid: str):
        row = require_incident(iid)
        if row.state != "INVESTIGATING":
            raise HTTPException(409, "No running investigation to cancel")
        task = runtime.tasks.get(f"investigate:{iid}")
        if task:
            task.cancel()
            import asyncio

            await asyncio.gather(task, return_exceptions=True)
        from pulse.core.schemas import State

        store.transition(iid, State.FAILED, {"reason": "Operator cancelled investigation"})
        store.audit("investigation.cancelled", iid, {})
        return {"cancelled": True}

    @app.get("/api/v1/overview", dependencies=auth, response_model=OverviewView)
    async def overview():
        with store.session() as db:
            monitored = db.scalars(select(Service).where(Service.monitored.is_(True))).all()
            fresh_window = store.settings().interval_seconds * 3
            healthy = sum(
                s.snapshot.get("status") == "running"
                and s.snapshot.get("health", "none") in ("none", "healthy")
                and time.time() - s.last_seen < fresh_window
                for s in monitored
            )
            active_filter = (
                Incident.kind != "question",
                Incident.state.not_in(["RESOLVED", "DISMISSED"]),
            )
            return {
                "monitored_services": len(monitored),
                "healthy_services": healthy,
                "active_incidents": db.scalar(
                    select(func.count()).select_from(Incident).where(*active_filter)
                ),
                "awaiting_approval": db.scalar(
                    select(func.count())
                    .select_from(Incident)
                    .where(*active_filter, Incident.state == "AWAITING_APPROVAL")
                ),
                "resolved_last_24h": db.scalar(
                    select(func.count())
                    .select_from(Incident)
                    .where(Incident.state == "RESOLVED", Incident.updated_at >= time.time() - 86400)
                ),
            }

    @app.get("/api/v1/services", dependencies=auth, response_model=list[ServiceView])
    async def services():
        with store.session() as db:
            result = []
            for service in db.scalars(select(Service).order_by(Service.name)):
                latest = db.scalar(
                    select(Sample)
                    .where(Sample.service_id == service.id)
                    .order_by(Sample.at.desc())
                    .limit(1)
                )
                fresh = (
                    latest is not None
                    and time.time() - latest.at <= store.settings().telemetry_max_age_seconds
                )
                result.append(
                    {
                        **serialize(service),
                        "remediation_allowed": service.remediation_allowed
                        and not config.project_context.get("read_only", False),
                        "metrics": latest.data if latest is not None and fresh else None,
                    }
                )
            return result

    @app.get("/api/v1/services/{sid}", dependencies=auth, response_model=ServiceView)
    async def service(sid: str):
        row = require_service(sid)
        return {
            **serialize(row),
            "remediation_allowed": row.remediation_allowed
            and not config.project_context.get("read_only", False),
        }

    @app.patch("/api/v1/services/{sid}/permissions", dependencies=auth, response_model=ServiceView)
    async def permissions(sid: str, body: ServicePermission):
        require_service(sid)
        if body.remediation_allowed and config.project_context.get("read_only"):
            raise HTTPException(
                403,
                "Project demo is read-only. Stop it and use normal monitoring to review recovery permissions.",
            )
        with store.session.begin() as db:
            row = db.get(Service, sid)
            if row is None:
                raise HTTPException(404, "Service no longer exists")
            row.monitored, row.remediation_allowed = body.monitored, body.remediation_allowed
            db.add(
                Audit(
                    actor="operator",
                    operation="service.permissions",
                    resource_id=sid,
                    details=body.model_dump(),
                )
            )
            db.add(
                Event(kind="service.permissions", payload={"service_id": sid, **body.model_dump()})
            )
        return serialize(row)

    @app.get("/api/v1/services/{sid}/metrics", dependencies=auth)
    async def metrics(sid: str, limit: int = Query(120, ge=1, le=360)):
        require_service(sid, True)
        with store.session() as db:
            return [
                serialize(s)
                for s in reversed(
                    db.scalars(
                        select(Sample)
                        .where(Sample.service_id == sid)
                        .order_by(Sample.at.desc())
                        .limit(limit)
                    ).all()
                )
            ]

    @app.get("/api/v1/services/{sid}/logs", dependencies=auth)
    async def logs(sid: str, limit: int = Query(100, ge=1, le=300)):
        row = require_service(sid, True)
        from pulse.core.schemas import ToolArgs, ToolCall

        evidence = await runtime.tools.execute(
            ToolCall(
                name="get_container_logs", args=ToolArgs(container_id=row.container_id, limit=limit)
            ),
            sid,
            None,
        )
        if not evidence["success"]:
            raise HTTPException(503, "Container logs unavailable; check gateway connectivity")
        return evidence["result"]

    @app.get("/api/v1/incidents", dependencies=auth, response_model=list[IncidentView])
    async def incidents():
        with store.session() as db:
            return [
                serialize(i)
                for i in db.scalars(
                    select(Incident).order_by(Incident.created_at.desc()).limit(100)
                )
            ]

    @app.get("/api/v1/incidents/{iid}", dependencies=auth)
    async def incident(iid: str):
        row = require_incident(iid)
        with store.session() as db:
            return {
                **serialize(row),
                "actions": [
                    serialize(a)
                    for a in db.scalars(
                        select(Remediation)
                        .where(Remediation.incident_id == iid)
                        .order_by(Remediation.created_at.desc())
                    )
                ],
                "tools": [
                    serialize(t)
                    for t in db.scalars(
                        select(ToolExecution)
                        .where(ToolExecution.incident_id == iid)
                        .order_by(ToolExecution.at)
                    )
                ],
            }

    @app.get("/api/v1/incidents/{iid}/timeline", dependencies=auth)
    async def timeline(iid: str):
        require_incident(iid)
        with store.session() as db:
            return [
                serialize(e)
                for e in db.scalars(
                    select(Event).where(Event.incident_id == iid).order_by(Event.id)
                )
            ]

    @app.get("/api/v1/incidents/{iid}/similar", dependencies=auth)
    async def similar(iid: str, q: str = Query("", max_length=200)):
        row = require_incident(iid)
        return [serialize(i) for i in store.similar(row.service_id, row.kind, q) if i.id != iid]

    @app.post("/api/v1/incidents/{iid}/investigate", dependencies=auth, status_code=202)
    async def investigate(iid: str):
        row = require_incident(iid)
        require_service(row.service_id, True)
        if (
            row.state not in ("DETECTED", "FAILED", "DIAGNOSED", "AWAITING_APPROVAL")
            or f"investigate:{iid}" in runtime.tasks
        ):
            raise HTTPException(409, "Incident cannot be investigated in its current state")
        with store.session.begin() as db:
            db.execute(
                update(Remediation)
                .where(Remediation.incident_id == iid, Remediation.status == "proposed")
                .values(status="invalidated")
            )
        runtime.spawn(f"investigate:{iid}", runtime.investigate(iid))
        return {"accepted": True, "incident_id": iid}

    @app.post("/api/v1/incidents/{iid}/dismiss", dependencies=auth)
    async def dismiss(iid: str, body: Dismissal):
        row = require_incident(iid)
        if row.state not in ("DETECTED", "DIAGNOSED", "AWAITING_APPROVAL", "FAILED"):
            raise HTTPException(409, "Cannot dismiss an active execution")
        from pulse.core.schemas import State

        store.transition(iid, State.DISMISSED, {"reason": body.reason})
        with store.session.begin() as db:
            db.execute(
                update(Remediation)
                .where(Remediation.incident_id == iid, Remediation.status == "proposed")
                .values(status="rejected")
            )
        store.audit("incident.dismissed", iid, body.model_dump())
        return {"dismissed": True}

    @app.get("/api/v1/remediations/{aid}", dependencies=auth)
    async def action_details(aid: str):
        with store.session() as db:
            action = db.get(Remediation, aid)
            if not action:
                raise HTTPException(404, "Action not found")
            service = db.get(Service, action.service_id)
            incident = db.get(Incident, action.incident_id)
            if service is None or incident is None:
                raise HTTPException(409, "Action context is unavailable; no approval can be issued")
            return redact(
                {
                    **serialize(action),
                    "service_name": service.name,
                    "read_only": bool(config.project_context.get("read_only")),
                    "remediation_allowed": service.remediation_allowed
                    and not config.project_context.get("read_only", False),
                    "incident_state": incident.state,
                }
            )

    @app.post("/api/v1/remediations/{aid}/approve", dependencies=auth, status_code=202)
    async def approve(aid: str, body: Approval, request: Request):
        if config.project_context.get("read_only"):
            store.audit("remediation.approval_denied", aid, {"reason": "Project demo is read-only"})
            raise HTTPException(409, "Project demo is read-only; no approval was issued")
        try:
            await runtime.remediator.claim(aid, body.action_digest, actor=request.state.actor)
        except PolicyError as e:
            store.audit("remediation.approval_denied", aid, {"reason": str(e)})
            raise HTTPException(409, str(e)) from e
        except Exception as e:
            raise HTTPException(
                503, "Resource could not be revalidated; no approval was issued"
            ) from e
        runtime.spawn(f"execute:{aid}", runtime.remediator.execute(aid))
        return {"accepted": True, "action_id": aid}

    @app.post("/api/v1/incidents/{iid}/verification/recheck", dependencies=auth, status_code=202)
    async def recheck_verification(iid: str, request: Request):
        require_incident(iid)
        try:
            service, baseline = runtime.remediator.recheck(iid, actor=request.state.actor)
        except PolicyError as error:
            raise HTTPException(409, str(error)) from error
        runtime.spawn(f"verify:{iid}", runtime.remediator.verify(iid, service, baseline))
        return {"accepted": True, "incident_id": iid, "read_only": True}

    @app.post("/api/v1/remediations/{aid}/reject", dependencies=auth)
    async def reject(aid: str):
        with store.session.begin() as db:
            action = db.get(Remediation, aid)
            if not action:
                raise HTTPException(404, "Action not found")
            changed = db.execute(
                update(Remediation)
                .where(Remediation.id == aid, Remediation.status == "proposed")
                .values(status="rejected")
            )
            if cast(CursorResult, changed).rowcount != 1:
                raise HTTPException(409, "Action is no longer pending")
            db.add(
                Audit(
                    actor="operator", operation="remediation.rejected", resource_id=aid, details={}
                )
            )
            db.add(
                Event(
                    incident_id=action.incident_id,
                    kind="remediation.rejected",
                    payload={"action_id": aid},
                )
            )
        return {"rejected": True}

    @app.post("/api/v1/chat", dependencies=auth)
    async def chat(body: ChatRequest):
        service = require_service(body.service_id, True)
        with store.session.begin() as db:
            row = Incident(
                service_id=service.id, kind="question", title=redact(body.message), severity="info"
            )
            db.add(row)
            db.flush()
            db.add(
                Event(
                    incident_id=row.id,
                    kind="investigation.requested",
                    payload={"question": redact(body.message)},
                )
            )
        runtime.spawn(
            f"investigate:{row.id}", runtime.investigate(row.id, question=redact(body.message))
        )
        return {"incident_id": row.id, "accepted": True}

    @app.get("/api/v1/settings", dependencies=auth, response_model=SettingsView)
    async def settings():
        return {
            "runtime": store.settings(),
            "model": config.llm_model,
            "provider_configured": bool(config.llm_model) and config.llm_model != "mock/evidence",
            "api_base": redact(config.llm_api_base),
            "provider_note": "Configure PULSE_LLM_MODEL, PULSE_LLM_API_KEY and PULSE_LLM_API_BASE in .env and restart the API. Provider secrets are never returned.",
        }

    @app.patch("/api/v1/settings", dependencies=auth, response_model=Settings)
    async def save_settings(body: Settings):
        body = Settings.model_validate(
            {**store.settings().model_dump(), **body.model_dump(exclude_unset=True)}
        )
        with store.session.begin() as db:
            db.merge(Setting(key="runtime", value=body.model_dump()))
            db.add(
                Audit(
                    actor="operator",
                    operation="settings.updated",
                    resource_id="runtime",
                    details=body.model_dump(),
                )
            )
            db.add(Event(kind="settings.updated", payload=body.model_dump()))
        return body

    @app.get("/api/v1/activity", dependencies=auth)
    async def activity():
        with store.session() as db:
            return [
                serialize(e)
                for e in db.scalars(
                    select(Event)
                    .where(Event.kind != "telemetry.updated")
                    .order_by(Event.id.desc())
                    .limit(30)
                )
            ]

    @app.get("/api/v1/audit", dependencies=auth)
    async def audit():
        with store.session() as db:
            return [
                serialize(a) for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))
            ]

    @app.get("/api/v1/events", dependencies=auth)
    async def events(
        request: Request,
        after: int = Query(0, ge=0),
        last_event_id: Annotated[str | None, Header()] = None,
    ):
        try:
            cursor = max(after, int(last_event_id or "0"))
        except ValueError as e:
            raise HTTPException(422, "Invalid Last-Event-ID") from e

        async def stream():
            import asyncio

            nonlocal cursor
            yield "event: sync\ndata: {}\n\n"
            while not app.state.draining and not await request.is_disconnected():
                try:
                    await authorized(request, request.headers.get("authorization"))
                except HTTPException:
                    break
                with store.session() as db:
                    rows = db.scalars(
                        select(Event).where(Event.id > cursor).order_by(Event.id).limit(100)
                    ).all()
                for row in rows:
                    cursor = row.id
                    yield f"id: {row.id}\nevent: pulse\ndata: {json.dumps(serialize(row))}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/metrics", dependencies=auth, include_in_schema=False)
    async def exported_metrics():
        registry = CollectorRegistry()
        cpu = Gauge(
            "pulse_container_cpu_percent",
            "Docker CPU percent, 100% per core",
            ["service"],
            registry=registry,
        )
        mem = Gauge(
            "pulse_container_memory_percent",
            "Working set percent of container memory limit",
            ["service"],
            registry=registry,
        )
        with store.session() as db:
            for row in db.scalars(select(Service).where(Service.monitored.is_(True))):
                latest = db.scalar(
                    select(Sample)
                    .where(Sample.service_id == row.id)
                    .order_by(Sample.at.desc())
                    .limit(1)
                )
                if (
                    latest
                    and latest.data.get("available")
                    and time.time() - latest.at < store.settings().interval_seconds * 3
                ):
                    name = row.snapshot.get("labels", {}).get(
                        "com.docker.compose.service", row.name
                    )
                    cpu.labels(name).set(latest.data["cpu_percent"])
                    mem.labels(name).set(latest.data["memory_percent"])
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    return app


app = create_app()
