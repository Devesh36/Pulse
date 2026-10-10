import asyncio
import hashlib
import json
import time

import httpx
from sqlalchemy import update

from pulse.core.redaction import redact
from pulse.core.schemas import ActionProposal, Settings, State
from pulse.core.verification import (
    VerificationOutcome,
    assess_observation,
    finite,
    new_progress,
    verdict,
)
from pulse.db.models import Audit, Event, Incident, Remediation, Service, uid


class PolicyError(ValueError):
    pass


MUTATING_ACTIONS = {"start", "restart", "reset_memory", "reset_errors", "reset_latency"}


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
    if action.kind not in MUTATING_ACTIONS:
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
    if action.kind.startswith("reset_") and (
        labels.get("pulse.lab") != "pulse-lab"
        or labels.get("com.docker.compose.project") != "pulse-lab"
        or labels.get("com.docker.compose.service") != "demo-api"
        or snapshot.get("status") != "running"
    ):
        raise PolicyError("Fault reset is restricted to the running lab API")


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

    async def claim(self, action_id, digest, actor="operator"):
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
                    actor=actor,
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
            before = {"snapshot": snapshot, "at": time.time()}
            outcome = await self.adapter.mutate(action.container_id, action.kind, action.id)
            outcome["action_completed_at"] = time.time()
            with self.store.session.begin() as db:
                row = db.get(Remediation, action_id)
                row.status, row.outcome = "executed", {"snapshot": outcome, "pre_action": before}
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

    def probe_url(self, service):
        name = service.snapshot.get("labels", {}).get("com.docker.compose.service", service.name)
        return self.config.probe_urls.get(name)

    def missing_baseline(self, incident_id):
        progress = new_progress("unknown", {}, self.store.settings(), False)
        progress.update(
            result="INCONCLUSIVE",
            outcome="inconclusive",
            required_evidence=["executed_action_baseline"],
            reason="Recorded action baseline is missing. Inspect execution history and actual resource state; the action will not be replayed.",
        )
        self.checkpoint(incident_id, progress, "verification.completed", progress)

    def checkpoint(self, incident_id, progress, kind, sample):
        # Progress and its supporting event are one transaction, including final
        # result/lifecycle transition. Restart cannot lose an accepted observation.
        with self.store.session.begin() as db:
            incident = db.get(Incident, incident_id)
            if incident.state != "VERIFYING":
                raise PolicyError("Incident is no longer verifying")
            incident.verification = redact(progress)
            incident.updated_at = time.time()
            db.add(Event(incident_id=incident_id, kind=kind, payload=redact(sample)))
            if progress["result"]:
                state = "RESOLVED" if progress["result"] == "RECOVERED" else "FAILED"
                incident.state = state
                if state == "RESOLVED":
                    incident.active_key = None
                db.add(
                    Event(
                        incident_id=incident_id,
                        kind="incident.transition",
                        payload={"from": "VERIFYING", "to": state, "reason": progress["reason"]},
                    )
                )

    def recheck(self, incident_id, actor="operator"):
        from sqlalchemy import select

        with self.store.session.begin() as db:
            incident = db.get(Incident, incident_id)
            if (
                not incident
                or incident.state != "FAILED"
                or (incident.verification or {}).get("result") != "INCONCLUSIVE"
            ):
                raise PolicyError(
                    "Read-only re-verification requires a failed inconclusive incident"
                )
            service = db.get(Service, incident.service_id)
            if not service or not service.monitored:
                raise PolicyError("Service is outside the monitoring allowlist")
            action = db.scalar(
                select(Remediation)
                .where(Remediation.incident_id == incident_id, Remediation.status == "executed")
                .order_by(Remediation.created_at.desc())
            )
            if (
                not action
                or not action.outcome
                or action.digest != action_digest(action)
                or action.container_id != service.container_id
            ):
                raise PolicyError(
                    "A recorded executed action and matching resource are required; mutation will not be replayed"
                )
            baseline = action.outcome["snapshot"]
            old = incident.verification
            progress = new_progress(
                incident.kind,
                {**baseline, "action_completed_at": time.time()},
                self.store.settings(),
                bool(self.probe_url(service)),
            )
            # Rechecks still measure after the ORIGINAL action. Only this explicitly
            # requested read-only observation deadline is new.
            progress["baseline"] = baseline
            progress["history"] = old.get("history", []) + [
                {key: value for key, value in old.items() if key != "history"}
            ]
            progress["service_name"] = service.snapshot.get("labels", {}).get(
                "com.docker.compose.service", service.name
            )
            changed = db.execute(
                update(Incident)
                .where(Incident.id == incident_id, Incident.state == "FAILED")
                .values(state="VERIFYING", verification=redact(progress), updated_at=time.time())
            )
            if changed.rowcount != 1:
                raise PolicyError("Verification was already requested")
            db.add(
                Audit(
                    actor=actor,
                    operation="verification.recheck_requested",
                    resource_id=incident_id,
                    details={"action_id": action.id, "read_only": True},
                )
            )
            db.add(
                Event(
                    incident_id=incident_id,
                    kind="incident.transition",
                    payload={
                        "from": "FAILED",
                        "to": "VERIFYING",
                        "reason": "Explicit read-only re-verification of an inconclusive outcome",
                    },
                )
            )
        return service, baseline

    async def collect(self, incident, service, progress):
        from urllib.parse import urlparse

        now = time.time()
        completed_at = progress["baseline"].get("action_completed_at", now)
        settings = Settings.model_validate(progress["policy"])
        name = progress["service_name"]
        tasks = {
            "docker_state": self.adapter.inspect(service.container_id),
            "docker_metrics": self.adapter.metrics(service.container_id),
        }
        if incident.kind in ("latency", "errors"):
            window = max(2, min(settings.window_seconds, int(now - completed_at)))
            tasks.update(
                prometheus=self.prometheus.query(
                    "latency" if incident.kind == "latency" else "error_rate", name, window
                ),
                request_count=self.prometheus.query("request_count", name, window),
            )
        url = self.probe_url(service)

        async def probe():
            parsed = urlparse(url)
            if (
                parsed.scheme not in ("http", "https")
                or parsed.hostname not in self.config.probe_allowed_hosts
                or parsed.username
                or parsed.password
            ):
                raise PolicyError("Configured probe is outside the host allowlist")
            async with httpx.AsyncClient(
                timeout=5, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.get(url)
            return {"status": response.status_code, "at": time.time(), "source": "http_health"}

        if url:
            tasks["http_health"] = probe()
        results = await asyncio.gather(
            *(asyncio.wait_for(task, self.config.tool_timeout) for task in tasks.values()),
            return_exceptions=True,
        )
        received = {}
        for key, result in zip(tasks, results, strict=True):
            if isinstance(result, BaseException):
                received[key] = {
                    "error": type(result).__name__,
                    "at": time.time(),
                    "available": False,
                }
            elif isinstance(result, dict):
                received[key] = {**result}
                if key == "docker_state":
                    received[key]["at"] = result.get("observed_at")
            else:
                received[key] = {"error": "InvalidResponse", "available": False}
        return redact(received)

    async def verify(self, incident_id, service, baseline, resume=False):
        from copy import deepcopy

        with self.store.session() as db:
            incident = db.get(Incident, incident_id)
        if incident.state != "VERIFYING":
            return
        if not finite(baseline.get("action_completed_at")):
            self.missing_baseline(incident_id)
            return
        if incident.verification and incident.verification.get("version") == 2:
            progress = deepcopy(incident.verification)
        else:
            progress = new_progress(
                incident.kind, baseline, self.store.settings(), bool(self.probe_url(service))
            )
            progress["service_name"] = service.snapshot.get("labels", {}).get(
                "com.docker.compose.service", service.name
            )
            self.checkpoint(
                incident_id,
                progress,
                "verification.started",
                {
                    "required_evidence": progress["required_evidence"],
                    "deadline_at": progress["deadline_at"],
                },
            )
        if resume:
            progress["stable_since"], progress["stable_samples"] = None, 0
            progress["stable_source_starts"] = {}
            progress["resume_count"] = progress.get("resume_count", 0) + 1
            progress["reason"] = (
                "API restarted: unobserved time cannot count toward recovery. Resuming the original deadline without replaying the action."
            )
            marker = {
                "at": time.time(),
                "healthy": False,
                "missing_evidence": True,
                "rejected_evidence": {"continuity": "api_restart_gap"},
                "failures": [],
            }
            progress["samples"] = (progress["samples"] + [marker])[-300:]
            self.checkpoint(incident_id, progress, "verification.resumed", marker)
        settings = Settings.model_validate(progress["policy"])
        self.prometheus.max_age_seconds = settings.telemetry_max_age_seconds
        interval = min(settings.interval_seconds, settings.verification_seconds / 2)
        while time.time() < progress["deadline_at"]:
            received = await self.collect(incident, service, progress)
            sample = assess_observation(progress, incident.kind, service.container_id, received)
            if any(item.get("error") == "PolicyError" for item in received.values()):
                sample["error"] = "PolicyError"
            # No collection or sleep may extend the original observation deadline.
            code, reason = verdict(progress)
            self.checkpoint(incident_id, progress, "verification.sample", sample)
            if code == VerificationOutcome.VERIFICATION_FAILED or (
                code == VerificationOutcome.RECOVERED and time.time() <= progress["deadline_at"]
            ):
                break
            remaining = progress["deadline_at"] - time.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval, remaining))
        code, reason = verdict(progress)
        if (
            code == VerificationOutcome.RECOVERED
            and progress["updated_at"] > progress["deadline_at"]
        ):
            code, reason = (
                VerificationOutcome.INCONCLUSIVE,
                "Required recovery observations arrived after the original deadline. Restore reliable telemetry and request read-only re-verification.",
            )
        progress.update(
            result=code.value,
            reason=reason,
            outcome="confirmed"
            if code == VerificationOutcome.RECOVERED
            else "inconclusive"
            if code == VerificationOutcome.INCONCLUSIVE
            else "failed",
            observation_seconds=time.time() - progress["started_at"],
            completed_at=time.time(),
        )
        self.checkpoint(incident_id, progress, "verification.completed", progress)
