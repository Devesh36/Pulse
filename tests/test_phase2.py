import time
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pulse.core.detection import evaluate
from pulse.core.remediation import PolicyError, authorize
from pulse.core.schemas import ActionProposal, Settings
from pulse.core.verification import VerificationOutcome, classify_recovery
from pulse.tools.docker_adapter import SDKAdapter
from pulse.tools.prometheus import Prometheus

from apps.api.main import create_app


def test_stale_telemetry_cannot_create_incident():
    assert (
        evaluate(
            [{"status": "exited", "exit_code": 42, "observed_at": time.time() - 120}],
            Settings(min_samples=1),
        )
        == []
    )


def test_http_detection_requires_request_volume():
    sample = {"latency_ms": 2000, "error_rate": 0.8, "request_count": 0}
    settings = Settings(min_samples=1, http_min_requests=5)
    assert evaluate([sample], settings) == []
    sample["request_count"] = 10
    assert {kind for kind, _ in evaluate([sample], settings)} == {"latency", "errors"}


@pytest.mark.parametrize(
    ("confirmed", "observations", "expected"),
    [
        (True, [{"healthy": True}], VerificationOutcome.RECOVERED),
        (False, [{"healthy": False}], VerificationOutcome.NOT_RECOVERED),
        (False, [{"missing_evidence": True}], VerificationOutcome.INCONCLUSIVE),
        (False, [{"error": "PolicyError"}], VerificationOutcome.VERIFICATION_FAILED),
        (False, [], VerificationOutcome.INCONCLUSIVE),
        (
            False,
            [{"missing_evidence": True}, {"healthy": False}],
            VerificationOutcome.NOT_RECOVERED,
        ),
    ],
)
def test_recovery_classification(confirmed, observations, expected):
    assert classify_recovery(confirmed, observations) == expected


@pytest.mark.parametrize(
    "bad_label", ["pulse.lab", "com.docker.compose.project", "com.docker.compose.service"]
)
def test_resets_cannot_target_other_resources(runtime, incident, service, bad_label):
    snapshot = dict(runtime.adapter.snapshot)
    snapshot["labels"] = {
        **snapshot["labels"],
        "pulse.lab": "pulse-lab",
        "com.docker.compose.project": "pulse-lab",
        "com.docker.compose.service": "demo-api",
    }
    action = runtime.remediator.propose(
        incident, service, ActionProposal(kind="reset_memory", reason="Reviewed")
    )
    authorize(action, service, runtime.store.settings(), snapshot)
    snapshot["labels"][bad_label] = "unrelated"
    with pytest.raises(PolicyError):
        authorize(action, service, runtime.store.settings(), snapshot)


def test_gateway_project_scope_rejects_unrelated():
    client = MagicMock()
    client.containers.get.return_value.labels = {
        "pulse.monitor": "true",
        "com.docker.compose.project": "unrelated",
    }
    with pytest.raises(PermissionError):
        SDKAdapter(client, project="pulse-lab").inspect("a" * 64)


def test_events_are_bounded_and_exclude_metadata():
    client = MagicMock()
    client.containers.get.return_value.labels = {"pulse.monitor": "true"}
    stream = MagicMock()
    stream.__iter__.return_value = iter(
        [{"Action": "die", "time": 123, "Actor": {"Attributes": {"secret": "hidden"}}}] * 10
    )
    client.events.return_value = stream
    result = SDKAdapter(client).events("a" * 64, limit=2)
    assert len(result["events"]) == 2 and result["truncated"] and "hidden" not in str(result)
    stream.close.assert_called_once()


async def test_prometheus_stale_scrape_is_unavailable():
    def handle(request):
        value = time.time() - 120 if "timestamp(" in request.url.params["query"] else 2000
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"result": [{"metric": {}, "value": [time.time(), str(value)]}]},
            },
        )

    prom = Prometheus("http://prometheus")
    await prom.client.aclose()
    prom.client = httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(handle)
    )
    result = await prom.query("latency", "demo-api", 10)
    assert result["value"] is None and not result["available"]
    await prom.close()


def test_disabled_lab_requires_authorization(config, store, runtime):
    with TestClient(create_app(config, store, runtime)) as http:
        assert http.get("/api/v1/lab/status").status_code == 401
        headers = {"Authorization": f"Bearer {config.admin_token}"}
        assert http.get("/api/v1/lab/status", headers=headers).json()["enabled"] is False
        assert (
            http.post("/api/v1/lab/faults/container-crash", headers=headers, json={}).status_code
            == 403
        )


def test_test_principal_cannot_change_nonlab(config, store, runtime, service):
    config.lab_enabled = True
    config.lab_test_token = "separate-lab-test-principal-token"
    with TestClient(create_app(config, store, runtime)) as http:
        headers = {"Authorization": f"Bearer {config.lab_test_token}"}
        assert (
            http.patch(
                f"/api/v1/services/{service.id}/permissions",
                headers=headers,
                json={"monitored": True, "remediation_allowed": True},
            ).status_code
            == 403
        )
        assert (
            http.post(
                "/api/v1/chat", headers=headers, json={"service_id": service.id, "message": "x"}
            ).status_code
            == 403
        )


def test_evaluation_history_persists(config, store, runtime):
    from pulse.db.models import LabEvaluation
    from pulse.db.store import Store

    config.lab_enabled = True
    with TestClient(create_app(config, store, runtime)) as http:
        response = http.post(
            "/api/v1/lab/evaluations",
            headers={"Authorization": f"Bearer {config.admin_token}"},
            json={
                "scenario": "container-crash",
                "report": {"status": "FAIL", "error": "unit fixture"},
            },
        )
        assert response.status_code == 200
        record_id = response.json()["id"]
    reopened = Store(config.database_url)
    with reopened.session() as db:
        assert db.get(LabEvaluation, record_id).report["status"] == "FAIL"
    reopened.engine.dispose()


async def test_cancelled_tool_is_recorded(runtime, service, incident):
    import asyncio

    from pulse.core.schemas import ToolArgs, ToolCall
    from pulse.db.models import ToolExecution
    from sqlalchemy import select

    started = asyncio.Event()

    async def blocking(*args):
        started.set()
        await asyncio.Event().wait()

    runtime.adapter.logs = blocking
    task = asyncio.create_task(
        runtime.tools.execute(
            ToolCall(name="get_container_logs", args=ToolArgs()), service.id, incident.id
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with runtime.store.session() as db:
        record = db.scalars(select(ToolExecution)).one()
        assert not record.success and record.result["error"] == "CancelledError"


async def test_mock_model_is_labeled_and_uses_real_tool_evidence(
    runtime, config, service, incident
):
    from pulse.agents.investigator import Investigator

    config.lab_enabled = True
    config.llm_model = "mock/evidence"
    investigator = Investigator(runtime.store, runtime.tools, config)
    result = await investigator.run(incident, service)
    assert result["tokens_used"] == 0 and len(result["evidence"]) == 4
    assert "Mock model" in result["diagnosis"]["uncertainty"]
    assert any(f["evidence_ids"] for f in result["diagnosis"]["root_causes"])


def test_cleanup_cannot_bypass_pending_incident(config, store, runtime, incident):
    config.lab_enabled = True
    with TestClient(create_app(config, store, runtime)) as http:
        response = http.post(
            "/api/v1/lab/reset", headers={"Authorization": f"Bearer {config.admin_token}"}
        )
        assert response.status_code == 409
        assert runtime.adapter.mutations == []


def test_default_gateway_does_not_monitor_lab():
    client = MagicMock()
    client.containers.get.return_value.labels = {"pulse.monitor": "true", "pulse.lab": "pulse-lab"}
    client.containers.list.return_value = [client.containers.get.return_value]
    assert SDKAdapter(client).discover() == []
    with pytest.raises(PermissionError):
        SDKAdapter(client).inspect("a" * 64)


async def test_oversized_tool_evidence_is_audited_as_unavailable(runtime, service, incident):
    from pulse.core.schemas import ToolArgs, ToolCall
    from pulse.db.models import ToolExecution
    from sqlalchemy import select

    runtime.config.tool_max_output_bytes = 1024

    async def large_logs(*args):
        return {"lines": ["observation " * 1000]}

    runtime.adapter.logs = large_logs
    evidence = await runtime.tools.execute(
        ToolCall(name="get_container_logs", args=ToolArgs()), service.id, incident.id
    )
    assert not evidence["success"] and not evidence["result"]["available"]
    assert evidence["result"]["error"] == "ToolOutputLimitExceeded"
    with runtime.store.session() as db:
        record = db.scalars(select(ToolExecution)).one()
        assert record.result == evidence["result"] and not record.success
