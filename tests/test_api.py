import pytest
from fastapi.testclient import TestClient
from pulse.db.models import Incident, Sample
from sqlalchemy import select

from apps.api.main import create_app


@pytest.fixture
def client(config, store, runtime):
    with TestClient(create_app(config, store, runtime)) as c:
        yield c


def headers(config):
    return {"Authorization": f"Bearer {config.admin_token}"}


def test_auth_and_secret_safety(client, config, service):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/services").status_code == 401
    response = client.get("/api/v1/settings", headers=headers(config))
    assert (
        response.status_code == 200
        and config.admin_token not in response.text
        and config.adapter_token not in response.text
    )
    assert "llm_api_key" not in response.text


def test_cookie_login_and_csrf(client, config, service):
    response = client.post(
        "/api/v1/session", json={"token": config.admin_token}, headers={"Origin": config.web_origin}
    )
    assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/api/v1/services").status_code == 200
    path = f"/api/v1/services/{service.id}/permissions"
    body = {"monitored": True, "remediation_allowed": False}
    assert client.patch(path, json=body).status_code == 403
    assert (
        client.patch(path, json=body, headers={"Origin": "http://evil.invalid"}).status_code == 403
    )
    assert client.patch(path, json=body, headers={"Origin": config.web_origin}).status_code == 200


def test_resource_permissions_and_logs(client, config, service):
    auth = headers(config)
    assert client.get(f"/api/v1/services/{service.id}/logs", headers=auth).status_code == 200
    response = client.patch(
        f"/api/v1/services/{service.id}/permissions",
        headers=auth,
        json={"monitored": False, "remediation_allowed": False},
    )
    assert response.status_code == 200
    assert client.get(f"/api/v1/services/{service.id}/logs", headers=auth).status_code == 403
    assert (
        client.patch(
            f"/api/v1/services/{service.id}/permissions",
            headers=auth,
            json={"monitored": False, "remediation_allowed": True},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/services/not-found", headers=auth).status_code == 404


def test_settings_persist(client, config, store):
    settings = store.settings().model_dump()
    settings["cpu_threshold"] = 72
    response = client.patch("/api/v1/settings", json=settings, headers=headers(config))
    assert response.status_code == 200 and store.settings().cpu_threshold == 72
    settings["cpu_threshold"] = -1
    assert (
        client.patch("/api/v1/settings", json=settings, headers=headers(config)).status_code == 422
    )


def test_incident_detail_and_missing(client, config, incident):
    auth = headers(config)
    assert client.get(f"/api/v1/incidents/{incident.id}", headers=auth).json()["id"] == incident.id
    assert client.get(f"/api/v1/incidents/{incident.id}/timeline", headers=auth).status_code == 200
    assert client.get("/api/v1/incidents/missing", headers=auth).status_code == 404
    assert (
        client.post(
            "/api/v1/remediations/missing/approve", headers=auth, json={"action_digest": "a" * 64}
        ).status_code
        == 409
    )


async def test_core_vertical_slice(runtime, store, service, adapter):
    """Fault-adapter acceptance test, explicitly NOT the real-Docker demonstration."""
    adapter.snapshot.update(status="exited", exit_code=42)
    await runtime.poll()
    tasks = list(runtime.tasks.values())
    import asyncio

    await asyncio.gather(*tasks)
    with store.session() as db:
        row = db.scalar(select(Incident).where(Incident.kind == "stopped"))
        assert row.state == "AWAITING_APPROVAL"
        assert row.diagnosis["root_causes"][0]["evidence_ids"]
        from pulse.db.models import Remediation

        action = db.scalar(select(Remediation).where(Remediation.incident_id == row.id))
    await runtime.remediator.claim(action.id, action.digest)
    await runtime.remediator.execute(action.id)
    with store.session() as db:
        assert db.get(Incident, row.id).state == "RESOLVED"
        assert len(db.scalars(select(Sample)).all()) == 1


def test_session_rate_limit(client):
    for _ in range(5):
        assert (
            client.post("/api/v1/session", json={"token": "invalid-but-long-token"}).status_code
            == 401
        )
    assert (
        client.post("/api/v1/session", json={"token": "invalid-but-long-token"}).status_code == 429
    )


def test_settings_partial_patch_preserves_stored_values(client, config, store):
    auth = headers(config)
    assert (
        client.patch("/api/v1/settings", json={"cpu_threshold": 72}, headers=auth).status_code
        == 200
    )
    response = client.patch("/api/v1/settings", json={"remediation_disabled": True}, headers=auth)
    assert response.status_code == 200
    assert response.json()["cpu_threshold"] == 72 and store.settings().remediation_disabled
    assert (
        client.patch("/api/v1/settings", json={"unknown_setting": 5}, headers=auth).status_code
        == 422
    )


def test_overview_counts_are_not_limited_to_recent_incidents(client, config, store, service):
    with store.session.begin() as db:
        db.add_all(
            Incident(service_id=service.id, kind="stopped", title=f"Historical active {i}")
            for i in range(105)
        )
        db.add(Incident(service_id=service.id, kind="question", title="Operational question"))
    response = client.get("/api/v1/overview", headers=headers(config))
    assert response.status_code == 200
    assert response.json()["active_incidents"] == 105
    assert response.json()["monitored_services"] == 1 and response.json()["healthy_services"] == 1
    assert len(client.get("/api/v1/incidents", headers=headers(config)).json()) == 100
