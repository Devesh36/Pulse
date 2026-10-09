import time

import pytest
from pulse.core.detection import detect, evaluate
from pulse.core.schemas import Settings, State
from pulse.db.models import Incident
from sqlalchemy import select


@pytest.mark.parametrize(
    ("sample", "kind"),
    [
        ({"status": "exited", "exit_code": 42}, "stopped"),
        ({"status": "restarting", "restart_count": 2}, "restarting"),
        ({"health": "unhealthy"}, "unhealthy"),
        ({"available": True, "cpu_percent": 90}, "cpu"),
        ({"available": True, "memory_percent": 95}, "memory"),
        ({"latency_ms": 1000}, "latency"),
        ({"error_rate": 0.5}, "errors"),
    ],
)
def test_each_threshold(sample, kind):
    assert kind in dict(evaluate([sample] * 3, Settings()))


def test_insufficient_samples_and_missing_metrics():
    assert evaluate([{"available": True, "cpu_percent": 90}], Settings()) == []
    assert evaluate([{"available": False, "memory_percent": 99}] * 5, Settings()) == []
    assert evaluate([{"latency_ms": None}] * 5, Settings()) == []


def test_consecutive_samples():
    assert evaluate([{"available": True, "cpu_percent": n} for n in [95, 95, 12]], Settings()) == []


def test_expected_stopped_container_not_alerted():
    assert evaluate([{"status": "exited", "exit_code": 0}], Settings()) == []
    assert dict(
        evaluate([{"status": "running"}, {"status": "exited", "exit_code": 0}], Settings())
    )["stopped"]


def test_restart_delta():
    assert "restarting" in dict(evaluate([{"restart_count": 8}, {"restart_count": 11}], Settings()))
    assert evaluate([{"restart_count": 100}, {"restart_count": 100}], Settings()) == []


def test_deduplication_and_cooldown(store, service):
    settings = Settings()
    samples = [{"status": "exited", "exit_code": 42}]
    now = time.time()
    ids = detect(store, service, samples, settings, now)
    assert len(ids) == 1
    assert detect(store, service, samples, settings, now + 1) == []
    store.transition(ids[0], State.DISMISSED)
    assert detect(store, service, samples, settings, now + 20) == []
    assert len(detect(store, service, samples, settings, now + 500)) == 1
    with store.session() as db:
        assert len(db.scalars(select(Incident)).all()) == 2


def test_lifecycle(store, incident):
    with pytest.raises(ValueError, match="Invalid transition"):
        store.transition(incident.id, State.RESOLVED)
    for state in [
        State.INVESTIGATING,
        State.DIAGNOSED,
        State.AWAITING_APPROVAL,
        State.REMEDIATING,
        State.VERIFYING,
        State.RESOLVED,
    ]:
        store.transition(incident.id, state)
    with store.session() as db:
        row = db.get(Incident, incident.id)
        assert row.state == "RESOLVED" and row.active_key is None
    with pytest.raises(ValueError):
        store.transition(incident.id, State.INVESTIGATING)


def test_missing_latest_sample_breaks_sustained_violation():
    cpu = [{"available": True, "cpu_percent": 99}] * 3 + [{"available": False}]
    latency = [{"latency_ms": 9999}] * 3 + [{"latency_ms": None}]
    assert evaluate(cpu, Settings()) == []
    assert evaluate(latency, Settings()) == []
