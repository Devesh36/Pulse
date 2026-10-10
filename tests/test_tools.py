import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from pulse.core.redaction import redact
from pulse.core.schemas import ToolArgs, ToolCall
from pulse.db.models import ToolExecution
from pulse.tools.docker_adapter import AdapterError, DockerAdapter, SDKAdapter
from pydantic import ValidationError


def test_schemas_reject_shell_and_malicious_resource():
    for data in [
        {"container_id": "../../etc/passwd"},
        {"limit": 10000},
        {"query": "up"},
        {"since": -1},
    ]:
        with pytest.raises(ValidationError):
            ToolArgs(**data)
    with pytest.raises(ValidationError):
        ToolCall(name="execute_shell", args={})


async def test_resource_scope_audited(runtime, service, incident):
    call = ToolCall(name="inspect_container", args=ToolArgs(container_id="b" * 64))
    result = await runtime.tools.execute(call, service.id, incident.id)
    assert not result["success"] and "PermissionError" in result["result"]["error"]
    assert runtime.adapter.calls == []
    with runtime.store.session() as db:
        assert db.get(ToolExecution, result["id"]).success is False


async def test_redacted_logs_persisted(runtime, service, incident):
    result = await runtime.tools.execute(
        ToolCall(name="get_container_logs", args=ToolArgs()), service.id, incident.id
    )
    assert result["success"]
    assert "private-key" not in str(result)
    assert "[REDACTED]" in str(result)


async def test_timeout_is_audited(runtime, service, incident):
    async def slow(*args, **kwargs):
        await asyncio.sleep(0.1)

    runtime.adapter.logs = slow
    runtime.config.tool_timeout = 0.01
    result = await runtime.tools.execute(
        ToolCall(name="get_container_logs", args=ToolArgs()), service.id, incident.id
    )
    assert not result["success"] and "TimeoutError" in result["result"]["error"]


@pytest.mark.parametrize(
    "name",
    [
        "list_containers",
        "inspect_container",
        "get_container_logs",
        "get_container_metrics",
        "get_container_health",
        "get_container_restart_history",
        "query_prometheus",
        "get_service_dependencies",
        "get_recent_service_events",
        "get_incident_history",
    ],
)
async def test_all_tools_return_structured_evidence(name, runtime, service, incident):
    result = await runtime.tools.execute(
        ToolCall(name=name, args=ToolArgs()), service.id, incident.id
    )
    assert result["success"] and isinstance(result["result"], dict) and result["id"]


def test_docker_allowlist_and_snapshot_no_secrets():
    client = MagicMock()
    container = client.containers.get.return_value
    container.id = "a" * 64
    container.name = "demo"
    container.labels = {"pulse.monitor": "true", "secret": "dont-expose"}
    container.attrs = {
        "State": {"Status": "exited", "ExitCode": 42},
        "Config": {"Env": ["API_KEY=secret"], "Image": "demo"},
    }
    adapter = SDKAdapter(client)
    snapshot = adapter.inspect(container.id)
    assert (
        snapshot["exit_code"] == 42
        and "dont-expose" not in str(snapshot)
        and "API_KEY" not in str(snapshot)
    )
    container.labels = {}
    with pytest.raises(PermissionError):
        adapter.inspect(container.id)


def test_docker_cpu_memory_computation():
    client = MagicMock()
    c = client.containers.get.return_value
    c.labels = {"pulse.monitor": "true"}
    c.status = "running"
    c.stats.return_value = {
        "read": "2026-10-09T14:00:00.000000000Z",
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 1000,
            "online_cpus": 2,
        },
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 500},
        "memory_stats": {"usage": 600, "limit": 1000, "stats": {"inactive_file": 100}},
    }
    metrics = SDKAdapter(client).metrics("a" * 64)
    assert metrics["cpu_percent"] == 40 and metrics["memory_percent"] == 50


def test_sdk_mutation_requires_development_label():
    client = MagicMock()
    c = client.containers.get.return_value
    c.labels = {
        "pulse.monitor": "true",
        "pulse.remediate": "true",
        "pulse.environment": "production",
    }
    with pytest.raises(PermissionError):
        SDKAdapter(client).mutate("a" * 64, "start")
    c.start.assert_not_called()


async def test_http_adapter_timeout_error_is_safe(config):
    adapter = DockerAdapter(config)
    adapter.client = httpx.AsyncClient(
        base_url="http://adapter",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    with pytest.raises(AdapterError):
        await adapter.inspect("a" * 64)
    await adapter.close()


def test_secret_redaction():
    value = redact(
        "password=hunter2 Authorization: Bearer abc123 https://alice:password@local sk-abcdefghijklmnop"
    )
    assert all(
        secret not in value
        for secret in ["hunter2", "abc123", "alice:password", "sk-abcdefghijklmnop"]
    )
    assert redact({"api_key": "abc", "lines": ["token=xyz"]}) == {
        "api_key": "[REDACTED]",
        "lines": ["token=[REDACTED]"],
    }


def test_logs_are_bounded_and_stream_closed():
    client = MagicMock()
    c = client.containers.get.return_value
    c.labels = {"pulse.monitor": "true"}
    stream = MagicMock()
    stream.__iter__.return_value = iter([b"x" * 100000])
    c.logs.return_value = stream
    result = SDKAdapter(client).logs("a" * 64)
    assert result["truncated"] and len(result["lines"][0]) == 65536
    assert c.logs.call_args.kwargs["follow"] is False
    stream.close.assert_called_once()
