"""Evidence integrity, durable deadlines, and read-only recovery rechecks."""

import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pulse.core.runtime import Runtime
from pulse.core.schemas import Settings
from pulse.core.verification import VerificationOutcome, assess_observation, new_progress, verdict
from pulse.db.models import Event, Incident, Remediation, Service
from pulse.db.store import Store
from pulse.tools.prometheus import Prometheus
from sqlalchemy import select

from apps.api.main import create_app

CID = "a" * 64


def test_lab_readiness_excludes_stale_resources_without_deleting_history(config, store):
    config.lab_enabled = True
    labels = {"pulse.lab": "pulse-lab", "com.docker.compose.project": "pulse-lab"}
    with store.session.begin() as db:
        db.add_all(
            [
                Service(
                    container_id="old",
                    name="old",
                    snapshot={"labels": labels},
                    last_seen=time.time() - 60,
                ),
                Service(
                    container_id="current",
                    name="current",
                    snapshot={"labels": labels},
                    last_seen=time.time(),
                ),
            ]
        )
    with TestClient(create_app(config, store)) as http:
        result = http.get(
            "/api/v1/lab/status", headers={"Authorization": "Bearer " + config.admin_token}
        )
        assert result.status_code == 200
        assert [s["container_id"] for s in result.json()["services"]] == ["current"]
    with store.session() as db:
        assert len(db.scalars(select(Service)).all()) == 2


def progress(kind="memory", probe=True):
    policy = Settings(verification_seconds=4, interval_seconds=2, window_seconds=10)
    result = new_progress(
        kind, {"action_completed_at": 99, "restart_count": 0}, policy, probe, now=100
    )
    result["service_name"] = "demo-api"
    return result


def received(at=100):
    return {
        "docker_state": {
            "at": at,
            "container_id": CID,
            "status": "running",
            "health": "healthy",
            "restart_count": 0,
        },
        "docker_metrics": {
            "at": at,
            "container_id": CID,
            "available": True,
            "cpu_percent": 10,
            "memory_percent": 20,
        },
        "http_health": {"at": at, "status": 200},
    }


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "stale",
        "duplicate",
        "out_of_order",
        "partial_failure",
        "wrong_resource",
        "future",
        "incomplete",
    ],
)
def test_unreliable_evidence_breaks_healthy_window(case):
    state = progress()
    assess_observation(state, "memory", CID, received(), now=100)
    data = received(102)
    if case == "missing":
        del data["docker_state"]
    elif case == "stale":
        data["docker_state"]["at"] = 20
    elif case in ("duplicate", "out_of_order"):
        data["docker_state"]["at"] = 100 if case == "duplicate" else 99.5
    elif case == "partial_failure":
        data["docker_metrics"] = {"error": "TimeoutError"}
    elif case == "wrong_resource":
        data["docker_state"]["container_id"] = "b" * 64
    elif case == "future":
        data["docker_state"]["at"] = 110
    else:
        del data["docker_state"]["health"]
    sample = assess_observation(state, "memory", CID, data, now=102)
    assert sample["missing_evidence"] and not sample["healthy"]
    assert state["stable_since"] is None and state["stable_samples"] == 0
    assert verdict(state, now=104)[0] == VerificationOutcome.INCONCLUSIVE
    assert (
        sample["required_evidence"] and sample["received_evidence"] and sample["rejected_evidence"]
    )


def test_fresh_recovery_requires_complete_continuous_window():
    state = progress()
    for stamp in (100, 102, 104):
        assess_observation(state, "memory", CID, received(stamp), now=stamp)
    assert verdict(state, now=104)[0] == VerificationOutcome.RECOVERED
    assert verdict(state, now=120)[0] == VerificationOutcome.INCONCLUSIVE


def test_gap_does_not_count_downtime_as_recovery():
    state = progress()
    assess_observation(state, "memory", CID, received(), now=100)
    sample = assess_observation(state, "memory", CID, received(110), now=110)
    assert sample["rejected_evidence"]["continuity"] == "telemetry_gap"
    assert verdict(state, now=110)[0] == VerificationOutcome.INCONCLUSIVE
    for stamp in (112, 114, 116):
        assess_observation(state, "memory", CID, received(stamp), now=stamp)
    assert verdict(state, now=116)[0] == VerificationOutcome.RECOVERED


def test_contradictory_health_is_inconclusive():
    state = progress("unhealthy")
    data = received()
    data["http_health"]["status"] = 503
    sample = assess_observation(state, "unhealthy", CID, data, now=100)
    assert sample["contradictions"] and not sample["healthy"]
    assert verdict(state, now=100)[0] == VerificationOutcome.INCONCLUSIVE


@pytest.mark.parametrize("independent_failure", [False, True])
def test_new_contradiction_invalidates_only_disputed_failure(independent_failure):
    state = progress()
    data = received()
    data["docker_state"]["health"] = "unhealthy"
    data["http_health"]["status"] = 503
    if independent_failure:
        data["docker_metrics"]["memory_percent"] = 90
    assess_observation(state, "memory", CID, data, now=100)
    assert verdict(state, now=100)[0] == VerificationOutcome.NOT_RECOVERED
    data = received(102)
    data["http_health"]["status"] = 503
    if independent_failure:
        del data["docker_metrics"]
    sample = assess_observation(state, "memory", CID, data, now=102)
    assert sample["contradictions"]
    assert "docker_health_unhealthy" not in state["condition_evidence"]
    assert "http_health_failed" not in state["condition_evidence"]
    assert verdict(state, now=102)[0] == (
        VerificationOutcome.NOT_RECOVERED
        if independent_failure
        else VerificationOutcome.INCONCLUSIVE
    )


def test_missing_evidence_cannot_hide_observed_continuing_failure():
    state = progress()
    data = received()
    data["docker_metrics"]["memory_percent"] = 90
    assess_observation(state, "memory", CID, data, now=100)
    unknown = received(102)
    unknown["docker_metrics"] = {"available": False}
    assess_observation(state, "memory", CID, unknown, now=102)
    assert verdict(state, now=102)[0] == VerificationOutcome.NOT_RECOVERED
    # A later genuine recovery supersedes earlier transient failure, but needs a
    # full recovery window before resolution.
    assess_observation(state, "memory", CID, received(104), now=104)
    assert verdict(state, now=104)[0] == VerificationOutcome.INCONCLUSIVE


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "stale",
        "duplicate",
        "wrong_service",
        "wrong_metric",
        "pre_action",
        "low_volume",
        "partial_failure",
        "time_disagreement",
    ],
)
def test_http_evidence_integrity(case):
    state = progress("errors")
    data = received(112)
    for name, metric, value in [
        ("prometheus", "error_rate", 0),
        ("request_count", "request_count", 20),
    ]:
        data[name] = {
            "available": True,
            "value": value,
            "sample_at": 112,
            "window_started_at": 102,
            "service": "demo-api",
            "metric": metric,
        }
    if case == "missing":
        del data["prometheus"]
    elif case == "stale":
        data["prometheus"]["sample_at"] = 40
    elif case == "duplicate":
        state["source_watermarks"]["prometheus"] = 112
    elif case == "wrong_service":
        data["prometheus"]["service"] = "unrelated"
    elif case == "wrong_metric":
        data["prometheus"]["metric"] = "latency"
    elif case == "pre_action":
        data["prometheus"]["window_started_at"] = 90
    elif case == "low_volume":
        data["request_count"]["value"] = 0
    elif case == "partial_failure":
        data["request_count"] = {"error": "ReadTimeout"}
    else:
        data["request_count"]["sample_at"] = 111
    sample = assess_observation(state, "errors", CID, data, now=112)
    assert not sample["healthy"] and sample["missing_evidence"]
    assert verdict(state, now=112)[0] == VerificationOutcome.INCONCLUSIVE


async def test_failed_scrape_rejects_retained_prometheus_values():
    def handle(request):
        expression = request.url.params["query"]
        if "timestamp(" in expression:
            assert "min(up and on(job, instance)" in expression
            rows = []
        else:
            rows = [{"value": [time.time(), "0"]}]
        assert "time" in request.url.params
        return httpx.Response(200, json={"status": "success", "data": {"result": rows}})

    prom = Prometheus("http://prometheus")
    await prom.client.aclose()
    prom.client = httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(handle)
    )
    try:
        result = await prom.query("error_rate", "demo-api", 10)
        assert result["value"] is None and not result["available"]
    finally:
        await prom.close()


async def test_restart_preserves_deadline_samples_and_never_replays(
    runtime, config, service, incident
):
    from conftest import FakePrometheus

    now = time.time()
    baseline = {"action_completed_at": now - 10, "restart_count": 0}
    state = new_progress(
        "stopped", baseline, Settings(verification_seconds=2, recovery_grace_seconds=0), False
    )
    state.update(
        service_name="test-api",
        stable_since=now - 3,
        stable_samples=3,
        samples=[{"at": now - 3, "healthy": True}],
        sample_count=3,
    )
    with runtime.store.session.begin() as db:
        row = db.get(Incident, incident.id)
        row.state = "VERIFYING"
        row.verification = state
        db.add(
            Remediation(
                incident_id=incident.id,
                service_id=service.id,
                container_id=CID,
                kind="start",
                reason="Previously approved",
                digest="recorded",
                status="executed",
                expires_at=now - 1,
                outcome={"snapshot": baseline},
            )
        )
    reopened = Store(config.database_url)
    restarted = Runtime(reopened, config, runtime.adapter)
    await restarted.prometheus.close()
    restarted.prometheus = FakePrometheus()
    restarted.remediator.prometheus = restarted.prometheus
    try:
        await restarted.start()
        await asyncio.gather(*list(restarted.tasks.values()))
        with reopened.session() as db:
            result = db.get(Incident, incident.id)
            assert result.state == "FAILED" and result.verification["result"] == "INCONCLUSIVE"
            assert result.verification["deadline_at"] == state["deadline_at"]
            assert (
                result.verification["sample_count"] == 3
                and result.verification["resume_count"] == 1
            )
            assert result.verification["samples"][0] == state["samples"][0]
            assert db.scalar(select(Event).where(Event.kind == "verification.resumed"))
        assert runtime.adapter.mutations == []
    finally:
        await restarted.stop()
        reopened.engine.dispose()


async def test_progress_is_committed_before_cancellation(runtime, service, incident):
    with runtime.store.session.begin() as db:
        db.get(Incident, incident.id).state = "VERIFYING"
    task = asyncio.create_task(
        runtime.remediator.verify(
            incident.id, service, {"action_completed_at": time.time(), "restart_count": 0}
        )
    )
    for _ in range(100):
        with runtime.store.session() as db:
            result = db.get(Incident, incident.id).verification
        if result and result["sample_count"]:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with runtime.store.session() as db:
        result = db.get(Incident, incident.id)
        assert result.state == "VERIFYING" and result.verification["samples"]
        assert db.scalar(select(Event).where(Event.kind == "verification.sample"))


def test_telemetry_controls_cannot_target_development_resource(config, store, runtime, service):
    config.lab_enabled = True
    with TestClient(create_app(config, store, runtime)) as http:
        headers = {"Authorization": f"Bearer {config.admin_token}"}
        assert (
            http.post(
                f"/api/v1/lab/telemetry/{service.id}", headers=headers, json={"enabled": False}
            ).status_code
            == 403
        )
        assert runtime.adapter.mutations == []


def test_recheck_cannot_hide_known_failure(config, store, runtime, incident):
    with store.session.begin() as db:
        row = db.get(Incident, incident.id)
        row.state = "FAILED"
        row.verification = {"result": "NOT_RECOVERED"}
    with TestClient(create_app(config, store, runtime)) as http:
        response = http.post(
            f"/api/v1/incidents/{incident.id}/verification/recheck",
            headers={"Authorization": f"Bearer {config.admin_token}"},
        )
        assert response.status_code == 409
        assert runtime.adapter.mutations == []


async def test_partial_collection_retains_successful_evidence(runtime, service, incident):
    async def missing_metrics(*args):
        raise TimeoutError("not available")

    runtime.adapter.metrics = missing_metrics
    policy = new_progress(
        "stopped",
        {"action_completed_at": time.time() - 1, "restart_count": 0},
        runtime.store.settings(),
        False,
    )
    policy["service_name"] = "test-api"
    result = await runtime.remediator.collect(incident, service, policy)
    assert result["docker_state"]["container_id"] == service.container_id
    assert result["docker_metrics"]["error"] == "TimeoutError"
    sample = assess_observation(policy, "stopped", service.container_id, result)
    assert not sample["healthy"] and sample["missing_evidence"]


async def test_missing_baseline_has_explicit_durable_inconclusive_verdict(runtime, incident):
    with runtime.store.session.begin() as db:
        db.get(Incident, incident.id).state = "VERIFYING"
    await runtime.start()
    try:
        with runtime.store.session() as db:
            result = db.get(Incident, incident.id)
            assert result.state == "FAILED" and result.verification["result"] == "INCONCLUSIVE"
            assert result.verification["required_evidence"] == ["executed_action_baseline"]
        assert runtime.adapter.mutations == []
    finally:
        await runtime.stop()


async def test_restart_after_recorded_execution_resumes_observations_only(
    runtime, service, incident
):
    with runtime.store.session.begin() as db:
        row = db.get(Incident, incident.id)
        row.state = "REMEDIATING"
        db.add(
            Remediation(
                incident_id=incident.id,
                service_id=service.id,
                container_id=CID,
                kind="start",
                reason="Recorded execution",
                digest="recorded",
                status="executed",
                expires_at=time.time() - 1,
                outcome={
                    "snapshot": {"action_completed_at": time.time() - 100, "restart_count": 0}
                },
            )
        )
    await runtime.start()
    try:
        await asyncio.gather(*list(runtime.tasks.values()))
        with runtime.store.session() as db:
            result = db.get(Incident, incident.id)
            assert result.state == "FAILED" and result.verification["result"] == "INCONCLUSIVE"
            assert db.scalar(select(Remediation)).status == "executed"
        assert runtime.adapter.mutations == []
    finally:
        await runtime.stop()


async def test_read_only_recheck_preserves_expiry_digest_and_does_not_mutate(
    runtime, service, incident
):
    from pulse.core.remediation import PolicyError, action_digest
    from test_remediation import proposed

    action = proposed(runtime, incident, service)
    with runtime.store.session.begin() as db:
        row = db.get(Remediation, action.id)
        row.expires_at = time.time() + 0.5
        row.digest = action_digest(row)
        digest = row.digest
    runtime.adapter.measurement["available"] = False
    await runtime.remediator.claim(action.id, digest)
    await runtime.remediator.execute(action.id)
    assert runtime.adapter.mutations == [(service.container_id, "start", action.id)]
    runtime.adapter.measurement["available"] = True
    target, baseline = runtime.remediator.recheck(incident.id)
    with pytest.raises(PolicyError):
        runtime.remediator.recheck(incident.id)
    with pytest.raises(PolicyError, match="expired"):
        await runtime.remediator.claim(action.id, digest)
    await runtime.remediator.verify(incident.id, target, baseline)
    with runtime.store.session() as db:
        row = db.get(Incident, incident.id)
        assert row.state == "RESOLVED" and row.verification["result"] == "RECOVERED"
        assert row.verification["history"][-1]["result"] == "INCONCLUSIVE"
        assert db.get(Remediation, action.id).digest == digest
        assert db.get(Remediation, action.id).expires_at < time.time()
    assert len(runtime.adapter.mutations) == 1


def test_after_deadline_observations_cannot_confirm_recovery():
    state = progress()
    state["deadline_at"] = 103
    for stamp in (100, 102, 104):
        sample = assess_observation(state, "memory", CID, received(stamp), now=stamp)
    assert sample["rejected_evidence"]["deadline"] == "observation_after_deadline"
    assert verdict(state, now=104)[0] == VerificationOutcome.INCONCLUSIVE


@pytest.mark.parametrize("read", [None, "2020-01-01T00:00:00Z"])
def test_docker_source_time_is_not_replaced_by_receipt_time(read):
    from datetime import datetime
    from unittest.mock import MagicMock

    from pulse.tools.docker_adapter import SDKAdapter

    docker = MagicMock()
    container = docker.containers.get.return_value
    container.labels = {"pulse.monitor": "true"}
    container.status = "running"
    container.stats.return_value = {"read": read, "memory_stats": {"usage": 20, "limit": 100}}
    measured = SDKAdapter(docker).metrics(CID)
    if read is None:
        assert not measured["available"] and measured["at"] is None
    else:
        assert measured["at"] == datetime.fromisoformat(read.replace("Z", "+00:00")).timestamp()
        assert measured["observed_at"] > measured["at"] + 30


def test_fresh_primary_recovery_supersedes_failure_even_if_other_evidence_missing():
    state = progress()
    data = received()
    data["docker_metrics"]["memory_percent"] = 90
    assess_observation(state, "memory", CID, data, now=100)
    data = received(102)
    del data["http_health"]
    assess_observation(state, "memory", CID, data, now=102)
    assert verdict(state, now=102)[0] == VerificationOutcome.INCONCLUSIVE


def test_old_failure_evidence_expires_instead_of_claiming_current_failure():
    state = progress()
    data = received()
    data["docker_metrics"]["memory_percent"] = 90
    assess_observation(state, "memory", CID, data, now=100)
    data = received(140)
    del data["docker_metrics"]
    assess_observation(state, "memory", CID, data, now=140)
    assert verdict(state, now=140)[0] == VerificationOutcome.INCONCLUSIVE
    assert state["condition_evidence"]["memory_percent_above_recovery_threshold"]["failing"]


def test_buffered_advancing_samples_do_not_cover_real_recovery_window():
    state = progress()
    for received_at, source_at in [(100, 100), (102, 101), (104, 102)]:
        assess_observation(state, "memory", CID, received(source_at), now=received_at)
    assert state["stable_samples"] == 3
    assert verdict(state, now=104)[0] == VerificationOutcome.INCONCLUSIVE


async def test_invalid_recorded_action_timestamp_is_immediately_inconclusive(
    runtime, service, incident
):
    with runtime.store.session.begin() as db:
        row = db.get(Incident, incident.id)
        row.kind = "errors"
        row.state = "VERIFYING"
    await runtime.remediator.verify(incident.id, service, {"action_completed_at": None})
    with runtime.store.session() as db:
        result = db.get(Incident, incident.id).verification
        assert result["result"] == "INCONCLUSIVE" and "baseline is missing" in result["reason"]
    assert runtime.adapter.calls == []


@pytest.mark.parametrize(
    "sample",
    [
        {"healthy": True, "missing_evidence": True},
        {"healthy": True, "contradictions": ["disagreement"]},
    ],
)
def test_confirmation_flag_cannot_override_missing_or_contradictory_evidence(sample):
    from pulse.core.verification import classify_recovery

    assert classify_recovery(True, [sample]) == VerificationOutcome.INCONCLUSIVE


@pytest.mark.parametrize("missing", ["cpu", "memory_limit"])
def test_partial_docker_stats_are_unavailable_instead_of_measured_zero(missing):
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from pulse.tools.docker_adapter import SDKAdapter

    docker = MagicMock()
    c = docker.containers.get.return_value
    c.labels = {"pulse.monitor": "true"}
    c.status = "running"
    stats = {
        "read": datetime.now(UTC).isoformat(),
        "cpu_stats": {"system_cpu_usage": 1000, "cpu_usage": {"total_usage": 200}},
        "precpu_stats": {"system_cpu_usage": 500, "cpu_usage": {"total_usage": 100}},
        "memory_stats": {"usage": 50, "limit": 100},
    }
    if missing == "cpu":
        stats.pop("cpu_stats")
        stats.pop("precpu_stats")
    else:
        stats["memory_stats"].pop("limit")
    c.stats.return_value = stats
    result = SDKAdapter(docker).metrics(CID)
    assert not result["available"]
    assert result["cpu_percent" if missing == "cpu" else "memory_percent"] is None
