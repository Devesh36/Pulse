import asyncio
import logging
import time

from sqlalchemy import delete, select, update

from pulse.agents.investigator import Investigator
from pulse.core.detection import detect
from pulse.core.remediation import Remediator
from pulse.core.schemas import ActionProposal, State
from pulse.db.models import Audit, Checkpoint, Event, Incident, Remediation, Sample, Service
from pulse.tools.docker_adapter import DockerAdapter
from pulse.tools.prometheus import Prometheus
from pulse.tools.registry import ToolRegistry

log = logging.getLogger("pulse")


class Runtime:
    def __init__(self, store, config, adapter=None, model=None):
        self.store, self.config = store, config
        self.adapter = adapter or DockerAdapter(config)
        self.prometheus = Prometheus(config.prometheus_url)
        self.tools = ToolRegistry(store, self.adapter, self.prometheus, config)
        self.investigator = Investigator(store, self.tools, config, model)
        self.remediator = Remediator(store, self.adapter, self.prometheus, config)
        self.tasks = {}
        self.monitor_task = None
        self.adapter_status = "not_connected"
        self.last_poll = None

    def spawn(self, key, coro):
        if key in self.tasks and not self.tasks[key].done():
            coro.close()
            return
        task = asyncio.create_task(coro, name=key)
        self.tasks[key] = task

        def complete(done):
            if self.tasks.get(key) is done:
                self.tasks.pop(key, None)
            if not done.cancelled() and done.exception():
                log.error(
                    "Background operation failed",
                    extra={"operation": key, "error_type": type(done.exception()).__name__},
                )

        task.add_done_callback(complete)

    async def start(self):
        # A crash around a Docker mutation has an unknown outcome. Never re-execute it.
        with self.store.session.begin() as db:
            interrupted = db.scalars(select(Incident).where(Incident.state == "REMEDIATING")).all()
            for incident in interrupted:
                # This startup-only transition is equivalent to Store.transition,
                # performed atomically with the interrupted action updates below.
                incident.state = "FAILED"
                incident.updated_at = time.time()
                db.add(
                    Event(
                        incident_id=incident.id,
                        kind="incident.transition",
                        payload={
                            "from": "REMEDIATING",
                            "to": "FAILED",
                            "reason": "Worker interrupted",
                        },
                    )
                )
                db.add(
                    Audit(
                        actor="worker",
                        operation="remediation.interrupted",
                        resource_id=incident.id,
                        details={"automatic_retry": False},
                    )
                )
                incident.verification = {
                    "outcome": "inconclusive",
                    "reason": "Worker interrupted during execution; inspect actual container state before a new proposal",
                }
            db.execute(
                update(Remediation)
                .where(Remediation.status.in_(["approved", "executing"]))
                .values(status="interrupted")
            )
            resuming = db.scalars(select(Incident).where(Incident.state == "INVESTIGATING")).all()
            verifying = db.scalars(select(Incident).where(Incident.state == "VERIFYING")).all()
        for incident in resuming:
            self.spawn(f"investigate:{incident.id}", self.investigate(incident.id, resume=True))
        for incident in verifying:
            with self.store.session() as db:
                service = db.get(Service, incident.service_id)
                action = db.scalar(
                    select(Remediation)
                    .where(Remediation.incident_id == incident.id, Remediation.status == "executed")
                    .order_by(Remediation.created_at.desc())
                )
            if action and action.outcome:
                self.spawn(
                    f"verify:{incident.id}",
                    self.remediator.verify(incident.id, service, action.outcome["snapshot"]),
                )
            else:
                self.store.transition(
                    incident.id, State.FAILED, {"reason": "Missing verification baseline"}
                )
        if self.config.monitor_enabled:
            self.monitor_task = asyncio.create_task(self.monitor(), name="monitor")

    async def stop(self):
        tasks = list(self.tasks.values()) + ([self.monitor_task] if self.monitor_task else [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.adapter.close()
        await self.prometheus.close()

    async def monitor(self):
        while True:
            try:
                await self.poll()
                self.adapter_status = "connected"
                self.last_poll = time.time()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self.adapter_status != "unavailable":
                    log.warning("Telemetry poll failed", extra={"error_type": type(error).__name__})
                self.adapter_status = "unavailable"
            await asyncio.sleep(self.store.settings().interval_seconds)

    async def poll(self):
        snapshots = await self.adapter.discover()
        settings = self.store.settings()
        for snapshot in snapshots:
            with self.store.session.begin() as db:
                service = db.scalar(
                    select(Service).where(Service.container_id == snapshot["container_id"])
                )
                if not service:
                    service = Service(
                        container_id=snapshot["container_id"], name=snapshot["name"], monitored=True
                    )
                    db.add(service)
                service.snapshot, service.last_seen = snapshot, time.time()
                db.flush()
            if not service.monitored:
                continue
            try:
                data = {**snapshot, **await self.adapter.metrics(service.container_id)}
            except Exception:
                data = {**snapshot, "available": False}
            name = snapshot.get("labels", {}).get("com.docker.compose.service", service.name)
            for metric, key in [("latency", "latency_ms"), ("error_rate", "error_rate")]:
                try:
                    data[key] = (
                        await self.prometheus.query(metric, name, settings.window_seconds)
                    )["value"]
                except Exception:
                    data[key] = None
            with self.store.session.begin() as db:
                db.add(Sample(service_id=service.id, data=data))
                db.flush()
                rows = db.scalars(
                    select(Sample)
                    .where(
                        Sample.service_id == service.id,
                        Sample.at >= time.time() - settings.window_seconds,
                    )
                    .order_by(Sample.at)
                ).all()
            for iid in detect(self.store, service, [r.data for r in rows], settings):
                self.spawn(f"investigate:{iid}", self.investigate(iid))
        with self.store.session.begin() as db:
            db.execute(delete(Sample).where(Sample.at < time.time() - 86400))
        self.store.event("telemetry.updated", {"services": len(snapshots), "at": time.time()})

    async def investigate(self, incident_id, question="", resume=False):
        try:
            with self.store.session() as db:
                incident = db.get(Incident, incident_id)
                service = db.get(Service, incident.service_id)
                checkpoint = db.scalar(
                    select(Checkpoint).where(Checkpoint.thread_id == incident_id).limit(1)
                )
            if not resume:
                self.store.transition(incident_id, State.INVESTIGATING)
            result = await self.investigator.run(
                incident, service, question, resume=resume and bool(checkpoint)
            )
            with self.store.session.begin() as db:
                db.get(Incident, incident_id).diagnosis = result["diagnosis"]
            self.store.transition(incident_id, State.DIAGNOSED)
            self.store.event(
                "investigation.diagnosed",
                {"diagnosis": result["diagnosis"], "tokens_used": result["tokens_used"]},
                incident_id,
            )
            if result.get("action") and incident.kind != "question":
                action = self.remediator.propose(
                    incident, service, ActionProposal.model_validate(result["action"])
                )
                if action.kind in ("start", "restart"):
                    self.store.transition(incident_id, State.AWAITING_APPROVAL)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.store.session() as db:
                current = db.get(Incident, incident_id)
            if current and current.state == "INVESTIGATING":
                self.store.transition(incident_id, State.FAILED, {"error": type(error).__name__})
            raise
