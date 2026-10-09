import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location(
    "pulse_demo", Path(__file__).resolve().parents[1] / "examples/faulty-app/app.py"
)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def demo_client(monkeypatch):
    monkeypatch.setenv("PULSE_DEMO_ENABLED", "true")
    monkeypatch.setenv("PULSE_DEMO_TOKEN", "disposable-demo-test-token")
    demo.mode.update(delay=0.01, errors=False)
    demo.allocations.clear()
    with TestClient(demo.app) as client:
        yield client
    demo.allocations.clear()


DEMO_HEADERS = {"X-Demo-Token": "disposable-demo-test-token"}


def test_demo_real_latency_measurements_and_reset(demo_client):
    assert demo_client.post("/fault/latency", json={}).status_code == 403
    assert (
        demo_client.post(
            "/fault/latency", json={"delay_seconds": 0.1}, headers=DEMO_HEADERS
        ).status_code
        == 200
    )
    assert demo_client.get("/work").status_code == 200
    metrics = demo_client.get("/metrics").text
    assert 'demo_http_duration_seconds_count{service="faulty-app"}' in metrics
    assert 'demo_http_requests_total{service="faulty-app",status="200"}' in metrics
    assert demo_client.post("/reset", headers=DEMO_HEADERS).status_code == 200
    assert demo.mode["delay"] == 0.01


def test_demo_bounded_memory_and_genuine_errors(demo_client):
    assert (
        demo_client.post("/fault/memory", json={"mib": 193}, headers=DEMO_HEADERS).status_code
        == 422
    )
    assert (
        demo_client.post("/fault/memory", json={"mib": 1}, headers=DEMO_HEADERS).status_code == 200
    )
    assert len(demo.allocations[0]) == 1024 * 1024
    assert demo_client.post("/fault/errors", json={}, headers=DEMO_HEADERS).status_code == 200
    assert demo_client.get("/work").status_code == 500
    assert demo_client.post("/reset", headers=DEMO_HEADERS).status_code == 200
    assert not demo.allocations and demo_client.get("/work").status_code == 200
