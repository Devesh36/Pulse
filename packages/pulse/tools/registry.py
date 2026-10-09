import asyncio
import json
import time

from sqlalchemy import select

from pulse.core.redaction import redact
from pulse.core.schemas import ToolCall
from pulse.db.models import Event, Incident, Sample, Service, ToolExecution
from pulse.db.store import serialize


class ToolRegistry:
    def __init__(self, store, adapter, prometheus, config):
        self.store, self.adapter, self.prometheus, self.config = store, adapter, prometheus, config

    async def execute(self, call: ToolCall, service_id: str, incident_id: str | None):
        began = time.monotonic()
        cancelled = False
        try:
            result = await asyncio.wait_for(
                self.dispatch(call, service_id), self.config.tool_timeout
            )
            success = True
        except asyncio.CancelledError:
            result, success, cancelled = {"error": "CancelledError"}, False, True
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
            success = False
        result = redact(result)
        output_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        if output_bytes > self.config.tool_max_output_bytes:
            result, success = (
                {
                    "error": "ToolOutputLimitExceeded",
                    "available": False,
                    "truncated": True,
                    "original_bytes": output_bytes,
                    "limit_bytes": self.config.tool_max_output_bytes,
                },
                False,
            )
        with self.store.session.begin() as db:
            row = ToolExecution(
                incident_id=incident_id,
                service_id=service_id,
                name=call.name,
                args=call.args.model_dump(),
                result=result,
                success=success,
                duration_ms=round((time.monotonic() - began) * 1000, 2),
            )
            db.add(row)
            db.flush()
            evidence = {
                "id": row.id,
                "tool": call.name,
                "success": success,
                "result": result,
                "at": row.at,
            }
            db.add(Event(incident_id=incident_id, kind="tool.completed", payload=evidence))
        if cancelled:
            raise asyncio.CancelledError
        return evidence

    async def dispatch(self, call, service_id):
        with self.store.session() as db:
            service = db.get(Service, service_id)
            if not service or not service.monitored:
                raise PermissionError("Service is outside the monitoring allowlist")
            if call.args.container_id and call.args.container_id != service.container_id:
                raise PermissionError("Tool is scoped to the affected container")
            if call.args.service_id and call.args.service_id != service_id:
                raise PermissionError("Tool is scoped to the affected service")
            if call.name == "list_containers":
                return {
                    "containers": [
                        s.snapshot
                        for s in db.scalars(select(Service).where(Service.monitored.is_(True)))
                    ]
                }
            if call.name == "get_incident_history":
                return {
                    "incidents": [
                        serialize(i)
                        for i in db.scalars(
                            select(Incident)
                            .where(Incident.service_id == service_id)
                            .order_by(Incident.created_at.desc())
                            .limit(10)
                        )
                    ]
                }
            if call.name == "get_recent_service_events":
                if service.snapshot.get("labels", {}).get("pulse.lab") == "pulse-lab":
                    return await self.adapter.events(
                        service.container_id, call.args.since, call.args.limit
                    )
                ids = select(Incident.id).where(Incident.service_id == service_id)
                return {
                    "events": [
                        serialize(e)
                        for e in db.scalars(
                            select(Event)
                            .where(Event.incident_id.in_(ids))
                            .order_by(Event.id.desc())
                            .limit(30)
                        )
                    ]
                }
            if call.name == "get_service_dependencies":
                names = service.snapshot.get("labels", {}).get("pulse.dependencies", "").split(",")
                return {
                    "dependencies": [
                        s.snapshot
                        for s in db.scalars(
                            select(Service).where(
                                Service.monitored.is_(True), Service.name.in_(names)
                            )
                        )
                    ],
                    "source": "explicit pulse.dependencies label; unavailable when absent",
                }
            if call.name == "get_container_restart_history":
                rows = db.scalars(
                    select(Sample)
                    .where(Sample.service_id == service_id)
                    .order_by(Sample.at.desc())
                    .limit(100)
                ).all()
                return {
                    "samples": [
                        {
                            "at": s.at,
                            "restart_count": s.data.get("restart_count"),
                            "status": s.data.get("status"),
                            "started_at": s.data.get("started_at"),
                            "finished_at": s.data.get("finished_at"),
                        }
                        for s in rows
                    ],
                    "source": "observed samples, not a complete Docker event history",
                }
        cid = service.container_id
        if call.name == "get_container_logs":
            return await self.adapter.logs(cid, call.args.since, call.args.limit)
        if call.name == "get_container_metrics":
            current = await self.adapter.metrics(cid)
            with self.store.session() as db:
                rows = db.scalars(
                    select(Sample)
                    .where(
                        Sample.service_id == service_id, Sample.at >= time.time() - call.args.since
                    )
                    .order_by(Sample.at.desc())
                    .limit(call.args.limit)
                ).all()
            return {
                **current,
                "history": [
                    {
                        "at": s.at,
                        "available": s.data.get("available"),
                        "memory_percent": s.data.get("memory_percent"),
                        "cpu_percent": s.data.get("cpu_percent"),
                        "source": "persisted_docker_sample",
                    }
                    for s in reversed(rows)
                ],
            }
        if call.name in ("inspect_container", "get_container_health"):
            return await self.adapter.inspect(cid)
        if call.name == "query_prometheus":
            name = service.snapshot.get("labels", {}).get(
                "com.docker.compose.service", service.name
            )
            return await self.prometheus.query(
                call.args.query, name, self.store.settings().window_seconds
            )
        raise ValueError("Unknown tool")
