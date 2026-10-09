import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from apps.api import gateway


def test_gateway_auth_allowlist_and_durable_one_time_actions(monkeypatch, tmp_path):
    client = MagicMock()
    container = client.containers.get.return_value
    container.id = "a" * 64
    container.name = "demo"
    container.status = "exited"
    container.labels = {
        "pulse.monitor": "true",
        "pulse.remediate": "true",
        "pulse.environment": "development",
    }
    container.attrs = {"State": {"Status": "exited", "ExitCode": 42}, "Config": {"Image": "demo"}}
    client.containers.list.return_value = [container]
    monkeypatch.setattr(gateway.docker, "from_env", lambda **kwargs: client)
    monkeypatch.setattr(gateway, "TOKEN", "gateway-test-token-12345")
    monkeypatch.setattr(gateway, "JOURNAL", str(tmp_path / "journal.db"))
    headers = {"Authorization": "Bearer gateway-test-token-12345"}
    action_id = str(uuid.uuid4())
    with TestClient(gateway.app) as http:
        assert http.get("/containers").status_code == 401
        assert http.get("/containers", headers=headers).status_code == 200
        assert (
            http.post(
                f"/containers/{container.id}/start", headers=headers, json={"action_id": action_id}
            ).status_code
            == 200
        )
        assert (
            http.post(
                f"/containers/{container.id}/start", headers=headers, json={"action_id": action_id}
            ).status_code
            == 409
        )
        container.start.assert_called_once()
        assert (
            http.post(
                f"/containers/{container.id}/exec",
                headers=headers,
                json={"action_id": str(uuid.uuid4())},
            ).status_code
            == 422
        )
        assert http.get("/containers/../../etc/passwd", headers=headers).status_code in (404, 422)
        monkeypatch.setenv("PULSE_GATEWAY_DISABLED", "true")
        assert (
            http.post(
                f"/containers/{container.id}/start",
                headers=headers,
                json={"action_id": str(uuid.uuid4())},
            ).status_code
            == 403
        )
    # Simulated gateway process restart retains the consumed action identifier.
    monkeypatch.setenv("PULSE_GATEWAY_DISABLED", "false")
    with TestClient(gateway.app) as http:
        assert (
            http.post(
                f"/containers/{container.id}/start", headers=headers, json={"action_id": action_id}
            ).status_code
            == 409
        )
        container.start.assert_called_once()
