"""Opt-in integrations; no cloud model calls. Every resource is isolated and cleaned up."""

import os
import uuid

import pytest
from conftest import FakeAdapter, FakePrometheus
from pulse.core.runtime import Runtime
from pulse.db.models import Base, Incident, Service, Setting
from pulse.db.store import Store
from pulse.tools.docker_adapter import SDKAdapter
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker


@pytest.mark.skipif(
    not os.getenv("PULSE_TEST_POSTGRES_URL"),
    reason="Set PULSE_TEST_POSTGRES_URL for real PostgreSQL tests",
)
async def test_postgres_incident_memory_checkpoints_and_recovery(config):
    url = os.environ["PULSE_TEST_POSTGRES_URL"]
    schema = "pulse_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    store = Store.__new__(Store)
    store.engine, store.session = engine, sessionmaker(engine, expire_on_commit=False)
    runtime = None
    try:
        Base.metadata.create_all(engine)
        settings = store.settings().model_copy(
            update={
                "interval_seconds": 2,
                "verification_seconds": 2,
                "recovery_grace_seconds": 2,
                "min_samples": 1,
            }
        )
        with store.session.begin() as db:
            db.add(Setting(key="runtime", value=settings.model_dump()))
        adapter = FakeAdapter()
        adapter.snapshot.update(status="exited", exit_code=42)
        runtime = Runtime(store, config, adapter)
        runtime.prometheus = FakePrometheus()
        runtime.tools.prometheus = runtime.prometheus
        runtime.remediator.prometheus = runtime.prometheus
        await runtime.poll()
        import asyncio

        await asyncio.gather(*list(runtime.tasks.values()))
        with store.session() as db:
            incident = db.scalars(select(Incident)).one()
            service = db.get(Service, incident.service_id)
            assert incident.state == "AWAITING_APPROVAL" and incident.diagnosis
        with store.session.begin() as db:
            db.get(Service, service.id).remediation_allowed = True
        assert store.similar(service.id, "stopped", "stopped")[0].id == incident.id
        from pulse.agents.checkpoints import DatabaseSaver

        assert (
            await DatabaseSaver(store).aget_tuple({"configurable": {"thread_id": incident.id}})
        ).checkpoint
        from pulse.db.models import Remediation

        with store.session() as db:
            action = db.scalars(select(Remediation)).one()
        await runtime.remediator.claim(action.id, action.digest)
        await runtime.remediator.execute(action.id)
        with store.session() as db:
            assert db.get(Incident, incident.id).state == "RESOLVED"
    finally:
        if runtime:
            await runtime.stop()
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.mark.skipif(
    os.getenv("PULSE_TEST_DOCKER") != "1",
    reason="Set PULSE_TEST_DOCKER=1 with a working Docker daemon",
)
def test_real_docker_fault_inspection_and_start():
    import docker

    client = docker.from_env()
    client.images.pull("alpine:3.21")
    container = client.containers.create(
        "alpine:3.21",
        ["sh", "-c", "echo application_crash; exit 42"],
        name="pulse-test-" + uuid.uuid4().hex[:12],
        labels={
            "pulse.monitor": "true",
            "pulse.remediate": "true",
            "pulse.environment": "development",
        },
    )
    try:
        container.start()
        assert container.wait(timeout=30)["StatusCode"] == 42
        adapter = SDKAdapter(client)
        observed = adapter.inspect(container.id)
        assert observed["status"] == "exited" and observed["exit_code"] == 42
        assert "application_crash" in str(adapter.logs(container.id))
        assert any(c["container_id"] == container.id for c in adapter.discover())
        assert not adapter.metrics(container.id)["available"]
        # Starting this test's disposable development container is safe and specifically scoped.
        adapter.mutate(container.id, "start")
        container.wait(timeout=30)
    finally:
        container.remove(force=True)
        client.close()


@pytest.mark.skipif(
    not os.getenv("PULSE_TEST_PROMETHEUS_URL"),
    reason="Set PULSE_TEST_PROMETHEUS_URL to the isolated incident lab Prometheus",
)
async def test_real_prometheus_lab_request_volume_and_latency():
    from pulse.tools.prometheus import Prometheus

    prom = Prometheus(os.environ["PULSE_TEST_PROMETHEUS_URL"])
    try:
        count = await prom.query("request_count", "demo-api", 10)
        latency = await prom.query("latency", "demo-api", 10)
        errors = await prom.query("error_rate", "demo-api", 10)
        assert count["available"] and count["value"] >= 5
        assert latency["available"] and 0 < latency["value"] < 200
        assert errors["available"] and errors["value"] == 0
        assert count["source"] == "prometheus" and count["sample_at"] is not None
    finally:
        await prom.close()
