import asyncio
import hashlib
import json
import time

import httpx
from sqlalchemy import update

from pulse.core.schemas import ActionProposal, State
from pulse.db.models import Audit, Event, Incident, Remediation, Service, uid


class PolicyError(ValueError):
    pass


def action_digest(action):
    return hashlib.sha256(
        json.dumps(
            {
                k: getattr(action, k)
                for k in (
                    "id",
                    "incident_id",
                    "service_id",
                    "container_id",
                    "kind",
                    "reason",
                    "expires_at",
                )
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def authorize(action, service, settings, snapshot, now=None):
    if settings.remediation_disabled:
        raise PolicyError("Emergency disable is active")
    if action.kind not in ("restart", "start"):
        raise PolicyError("This proposal is advisory; no mutation is available")
    if action.expires_at <= (now or time.time()):
        raise PolicyError("Approval proposal expired; investigate again")
    if action.digest != action_digest(action):
        raise PolicyError("Action contents have changed")
    if not service.monitored or not service.remediation_allowed:
        raise PolicyError("Container has no remediation permission")
    if (
        action.container_id != service.container_id
        or snapshot.get("container_id") != action.container_id
    ):
        raise PolicyError("Container identity changed")
    labels = snapshot.get("labels", {})
    if (
        labels.get("pulse.monitor") != "true"
        or labels.get("pulse.remediate") != "true"
        or labels.get("pulse.environment") != "development"
    ):
        raise PolicyError("Gateway labels do not authorize development remediation")
    if action.kind == "start" and snapshot.get("status") not in ("created", "exited"):
        raise PolicyError("Start requires a stopped container")
    if action.kind == "restart" and snapshot.get("status") != "running":
        raise PolicyError("Restart requires a running container")


class Remediator:
    def __init__(self, store, adapter, prometheus, config):
        self.store, self.adapter, self.prometheus, self.config = store, adapter, prometheus, config

    def propose(self, incident, service, proposal: ActionProposal):
        row = Remediation(
            id=uid(),
            incident_id=incident.id,
            service_id=service.id,
            container_id=service.container_id,
            kind=proposal.kind,
            reason=proposal.reason,
            created_at=time.time(),
            expires_at=time.time() + 900,
            status="proposed",
        )
        row.digest = action_digest(row)
        with self.store.session.begin() as db:
            db.add(row)
            db.add(
                Event(
                    incident_id=incident.id,
                    kind="remediation.proposed",
                    payload={"action_id": row.id, "kind": row.kind, "reason": row.reason},
                )
            )
        return row

    async def claim(self, action_id, digest):
        with self.store.session() as db:
            action = db.get(Remediation, action_id)
            if not action:
                raise PolicyError("Unknown action")
            service = db.get(Service, action.service_id)
        snapshot = await self.adapter.inspect(action.container_id)
        authorize(action, service, self.store.settings(), snapshot)
        if digest != action.digest:
            raise PolicyError("Approval does not match the reviewed proposal")
        with self.store.session.begin() as db:
            # Atomic one-time approval, plus atomic lifecycle transition.
            service = db.get(Service, action.service_id)
            authorize(action, service, self.store.settings(), snapshot)
            changed = db.execute(
                update(Remediation)
                .where(Remediation.id == action_id, Remediation.status == "proposed")
                .values(status="approved")
            )
            if changed.rowcount != 1:
                raise PolicyError("Action has already been approved, rejected or invalidated")
            changed = db.execute(
                update(Incident)
                .where(
                    Incident.id == action.incident_id,
                    Incident.state == State.AWAITING_APPROVAL.value,
                )
                .values(state=State.REMEDIATING.value, updated_at=time.time())
            )
            if changed.rowcount != 1:
                raise PolicyError("Incident is not awaiting approval")
            db.add(
                Audit(
                    actor="operator",
                    operation="remediation.approved",
                    resource_id=action.id,
                    details={"digest": digest},
                )
            )
            db.add(
                Event(
                    incident_id=action.incident_id,
                    kind="incident.transition",
                    payload={"from": "AWAITING_APPROVAL", "to": "REMEDIATING"},
                )
            )
        return action

    async def execute(self, action_id):
        with self.store.session() as db:
            action = db.get(Remediation, action_id)
            service = db.get(Service, action.service_id)
        if action.status != "approved":
            self.store.audit(
                "remediation.execution_denied",
                action.id,
                {"reason": "A one-time approval is required"},
                actor="worker",
            )
            return
        try:
            snapshot = await self.adapter.inspect(action.container_id)
            with self.store.session() as db:
                service = db.get(Service, action.service_id)
            authorize(action, service, self.store.settings(), snapshot)
            with self.store.session.begin() as db:
                claimed = db.execute(
                    update(Remediation)
                    .where(Remediation.id == action_id, Remediation.status == "approved")
                    .values(status="executing")
                )
                if claimed.rowcount != 1:
                    return
                db.add(
                    Audit(
                        actor="worker",
                        operation="remediation.executing",
                        resource_id=action.id,
                        details={"kind": action.kind},
                    )
                )
            outcome = await self.adapter.mutate(action.container_id, action.kind, action.id)
            with self.store.session.begin() as db:
                row = db.get(Remediation, action_id)
                row.status, row.outcome = "executed", {"snapshot": outcome}
                db.add(
                    Audit(
                        actor="worker",
                        operation="remediation.executed",
                        resource_id=action.id,
                        details={"kind": action.kind},
                    )
                )
            self.store.transition(action.incident_id, State.VERIFYING)
            await self.verify(action.incident_id, service, outcome)
        except asyncio.CancelledError:
            # Persisted execution claims must never be replayed on restart.
            raise
        except Exception as error:
            with self.store.session.begin() as db:
                row = db.get(Remediation, action_id)
                row.status = "failed"
                row.outcome = {
                    "error": type(error).__name__,
                    "message": str(error)[:300],
                    "automatic_retry": False,
                }
                db.add(
                    Audit(
                        actor="worker",
                        operation="remediation.failed",
                        resource_id=action.id,
                        details=row.outcome,
                    )
                )
            with self.store.session() as db:
                current = db.get(Incident, action.incident_id).state
            if current in ("REMEDIATING", "VERIFYING"):
                self.store.transition(action.incident_id, State.FAILED, {"error": str(error)[:300]})

    async def verify(self, incident_id, service, baseline):
        with self.store.session() as db:
            incident = db.get(Incident, incident_id)
        settings = self.store.settings()
        started = time.monotonic()
        observations = []
        stable_since = None
        stable_samples = 0
        confirmed = False
        inconclusive = False
        max_duration = settings.verification_seconds + settings.recovery_grace_seconds
        if incident.kind in ("latency", "errors"):
            max_duration += settings.window_seconds
        interval = min(settings.interval_seconds, settings.verification_seconds / 2)
        while True:
            evidence = {"at": time.time()}
            try:
                snapshot = await self.adapter.inspect(service.container_id)
                metrics = await self.adapter.metrics(service.container_id)
                evidence.update(snapshot=snapshot, metrics=metrics)
                healthy = snapshot.get("status") == "running" and snapshot.get("health") in (
                    "none",
                    "healthy",
                )
                healthy &= snapshot.get("restart_count", 0) <= baseline.get("restart_count", 0)
                if not metrics.get("available"):
                    healthy = False
                    inconclusive = True
                if incident.kind == "cpu":
                    healthy &= metrics.get("cpu_percent", float("inf")) < settings.cpu_threshold
                if incident.kind == "memory":
                    healthy &= (
                        metrics.get("memory_percent", float("inf")) < settings.memory_threshold
                    )
                if incident.kind in ("latency", "errors"):
                    name = service.snapshot.get("labels", {}).get(
                        "com.docker.compose.service", service.name
                    )
                    value = await self.prometheus.query(
                        "latency" if incident.kind == "latency" else "error_rate",
                        name,
                        settings.window_seconds,
                    )
                    evidence["prometheus"] = value
                    threshold = (
                        settings.latency_threshold_ms
                        if incident.kind == "latency"
                        else settings.error_rate_threshold
                    )
                    if value["value"] is None:
                        healthy, inconclusive = False, True
                    else:
                        healthy &= value["value"] < threshold
                url = self.config.probe_urls.get(
                    service.snapshot.get("labels", {}).get(
                        "com.docker.compose.service", service.name
                    )
                )
                if url:
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    if (
                        parsed.scheme not in ("http", "https")
                        or parsed.hostname not in self.config.probe_allowed_hosts
                        or parsed.username
                        or parsed.password
                    ):
                        raise PolicyError("Configured probe is outside the host allowlist")
                    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                        response = await client.get(url)
                    evidence["http_status"] = response.status_code
                    healthy &= 200 <= response.status_code < 400
                evidence["healthy"] = bool(healthy)
                if healthy:
                    stable_since = stable_since or time.monotonic()
                    stable_samples += 1
                else:
                    stable_since, stable_samples = None, 0
            except Exception as error:
                evidence.update(healthy=False, error=type(error).__name__)
                stable_since, stable_samples, inconclusive = None, 0, True
            observations.append(evidence)
            self.store.event("verification.sample", evidence, incident_id)
            if (
                stable_since
                and time.monotonic() - stable_since >= settings.verification_seconds
                and stable_samples >= 2
            ):
                confirmed = True
                break
            if time.monotonic() - started >= max_duration:
                break
            await asyncio.sleep(interval)
        result = {
            "outcome": "confirmed" if confirmed else "inconclusive" if inconclusive else "failed",
            "observation_seconds": time.monotonic() - started,
            "required_stable_seconds": settings.verification_seconds,
            "baseline": baseline,
            "samples": observations,
            "conditions": "Running, health acceptable, restart stability, metrics available, incident threshold recovered, configured HTTP probe successful",
        }
        with self.store.session.begin() as db:
            db.get(Incident, incident_id).verification = result
        self.store.event("verification.completed", result, incident_id)
        self.store.transition(
            incident_id, State.RESOLVED if result["outcome"] == "confirmed" else State.FAILED
        )
