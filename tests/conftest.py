from copy import deepcopy

import pytest
from pulse.core.config import Config
from pulse.core.runtime import Runtime
from pulse.db.models import Base, Incident, Service, Setting
from pulse.db.store import Store


class FakeAdapter:
    def __init__(self):
        self.snapshot = {
            "container_id": "a" * 64,
            "name": "test-api",
            "status": "running",
            "health": "healthy",
            "restart_count": 0,
            "exit_code": 0,
            "oom_killed": False,
            "labels": {
                "pulse.monitor": "true",
                "pulse.remediate": "true",
                "pulse.environment": "development",
                "com.docker.compose.service": "test-api",
            },
        }
        self.measurement = {
            "available": True,
            "cpu_percent": 12.5,
            "memory_percent": 25,
            "memory_bytes": 1024,
            "memory_limit_bytes": 4096,
        }
        self.calls = []
        self.mutations = []
        self.fail = False
        self.recover = True

    async def discover(self):
        return [deepcopy(self.snapshot)]

    async def inspect(self, cid):
        self.calls.append(("inspect", cid))
        if self.fail:
            raise RuntimeError("offline")
        return deepcopy(self.snapshot)

    async def metrics(self, cid):
        if self.fail:
            raise RuntimeError("offline")
        return deepcopy(self.measurement)

    async def logs(self, cid, since=1800, limit=100):
        self.calls.append(("logs", cid))
        return {"lines": ["2026-10-09 ERROR application exception; token=private-key"]}

    async def mutate(self, cid, kind, action_id):
        self.mutations.append((cid, kind, action_id))
        if self.fail:
            raise RuntimeError("offline")
        if self.recover:
            self.snapshot.update(status="running", health="healthy", exit_code=0)
        return deepcopy(self.snapshot)

    async def close(self):
        pass


class FakePrometheus:
    async def query(self, metric, name, window=60):
        return {"value": None, "query": metric, "source": "test-double"}

    async def close(self):
        pass


@pytest.fixture
def config(tmp_path, monkeypatch):
    for key in ("PULSE_PROBE_URLS", "PULSE_LLM_MODEL", "PULSE_LLM_API_KEY", "PULSE_LLM_API_BASE"):
        monkeypatch.delenv(key, raising=False)
    return Config(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/test.db",
        admin_token="admin-" + "x" * 32,
        adapter_token="adapter-" + "y" * 32,
        monitor_enabled=False,
        probe_urls={},
    )


@pytest.fixture
def store(config):
    s = Store(config.database_url)
    Base.metadata.create_all(s.engine)
    yield s
    s.engine.dispose()


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def service(store, adapter):
    with store.session.begin() as db:
        row = Service(
            container_id=adapter.snapshot["container_id"],
            name="test-api",
            monitored=True,
            remediation_allowed=True,
            snapshot=adapter.snapshot,
        )
        db.add(row)
        db.flush()
    return row


@pytest.fixture
def incident(store, service):
    with store.session.begin() as db:
        row = Incident(
            service_id=service.id,
            kind="stopped",
            title="test-api stopped",
            active_key=f"{service.id}:stopped",
        )
        db.add(row)
        db.flush()
    return row


@pytest.fixture
def runtime(store, config, adapter):
    r = Runtime(store, config, adapter)
    r.prometheus = FakePrometheus()
    r.tools.prometheus = r.prometheus
    r.remediator.prometheus = r.prometheus
    with store.session.begin() as db:
        settings = store.settings().model_copy(
            update={
                "verification_seconds": 2,
                "recovery_grace_seconds": 0,
                "interval_seconds": 2,
                "min_samples": 1,
            }
        )
        db.add(Setting(key="runtime", value=settings.model_dump()))
    return r
