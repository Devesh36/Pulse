"""One-command project setup is read-only, scoped, repeatable and honest about readiness."""

import io
import time
import uuid
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pulse.core.runtime import Runtime
from pulse.project import cli, demo, session, state
from pulse.repl import PulseRepl
from pulse.tools.docker_adapter import SDKAdapter

from apps.api.main import create_app


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    repo = tmp_path / "My Trading App"
    repo.mkdir()
    (repo / "compose.yaml").write_text("services:\n  api:\n    image: example\n")
    monkeypatch.setenv("PULSE_HOME", str(tmp_path / "private"))
    shell = PulseRepl(repo=str(repo), stdin=io.StringIO(), stdout=io.StringIO())
    shell.use_rawinput = False
    monkeypatch.setattr(shell, "docker_ready", lambda: True)
    yield shell
    if shell.watch_stream is not None:
        shell.watch_stream.close()


def scoped_container(root, project="trading", service="api", **labels):
    container = MagicMock()
    container.labels = {
        "com.docker.compose.project": project,
        "com.docker.compose.project.working_dir": str(root),
        "com.docker.compose.service": service,
        **labels,
    }
    return container


def test_read_only_enrollment_requires_complete_scope():
    for scope in (
        {},
        {"project": "trading"},
        {"project": "trading", "resource_root": "/tmp", "services": []},
    ):
        with pytest.raises(ValueError, match="nonempty service allowlist"):
            SDKAdapter(MagicMock(), read_only=True, **scope)


def test_read_only_discovery_and_inspection_preserve_scope_and_opt_out(terminal):
    engine = MagicMock()
    selected = scoped_container(terminal.project_path)
    others = [
        scoped_container("/another/root"),
        scoped_container(terminal.project_path, project="other"),
        scoped_container(terminal.project_path, service="bank"),
        scoped_container(terminal.project_path, **{"pulse.lab": "pulse-lab"}),
        scoped_container(terminal.project_path, **{"pulse.monitor": "false"}),
    ]
    engine.containers.list.return_value = [selected, *others]
    adapter = SDKAdapter(
        engine,
        project="trading",
        resource_root=terminal.project_path,
        services=["api"],
        read_only=True,
    )
    adapter.snapshot = lambda c: {"id": id(c)}
    assert adapter.discover() == [{"id": id(selected)}]
    assert engine.containers.list.call_args.kwargs["filters"] == {
        "label": ["com.docker.compose.project=trading"]
    }
    engine.containers.get.return_value = selected
    assert adapter.container("a" * 64) is selected
    for excluded in others:
        engine.containers.get.return_value = excluded
        with pytest.raises(PermissionError):
            adapter.container("a" * 64)
    normal = SDKAdapter(
        engine, project="trading", resource_root=terminal.project_path, services=["api"]
    )
    engine.containers.get.return_value = selected
    with pytest.raises(PermissionError):
        normal.container("a" * 64)


@pytest.mark.parametrize(
    "operation", ["start", "restart", "reset_memory", "reset_errors", "reset_latency"]
)
def test_read_only_gateway_denies_even_development_labeled_actions(terminal, operation):
    engine = MagicMock()
    engine.containers.get.return_value = scoped_container(
        terminal.project_path,
        **{"pulse.monitor": "true", "pulse.remediate": "true", "pulse.environment": "development"},
    )
    adapter = SDKAdapter(
        engine,
        project="trading",
        resource_root=terminal.project_path,
        services=["api"],
        read_only=True,
    )
    with pytest.raises(PermissionError, match="read-only"):
        adapter.mutate("a" * 64, operation)
    with pytest.raises(PermissionError, match="read-only"):
        adapter.lab_control("a" * 64, "crash")
    engine.containers.get.assert_not_called()


def test_demo_creates_profile_adopts_existing_project_selects_service_and_reuses(
    terminal, monkeypatch
):
    engine = MagicMock()
    engine.containers.list.return_value = [
        scoped_container(terminal.project_path, project="custom")
    ]
    monkeypatch.setattr(demo.docker, "from_env", lambda **kwargs: engine)
    started = []
    sid = str(uuid.uuid4())
    row = {
        "id": sid,
        "name": "custom-api-1",
        "monitored": True,
        "remediation_allowed": False,
        "snapshot": {},
        "metrics": None,
    }
    active = False
    requests = []

    def request(method, path, **kwargs):
        requests.append((method, path))
        if path == "/project":
            if not active:
                raise RuntimeError("No active project session")
            return {"read_only": True}
        return {
            "/health": {"docker": "connected", "last_poll": time.time()},
            "/settings": {"runtime": {"telemetry_max_age_seconds": 15}},
            "/services": [row],
            "/incidents": [],
        }[path]

    def start(flags):
        nonlocal active
        started.append(flags)
        active = True

    monkeypatch.setattr(terminal, "request", request)
    monkeypatch.setattr(terminal, "start_watch", start)
    terminal.onecmd("/demo --no-browser --port 9456")
    profile = state.load(terminal.project_path)
    credentials = state.credentials(terminal.project_path)
    assert profile["compose_project"] == "custom"
    assert started == ["--read-only --port 9456 --no-browser"]
    assert terminal.service_id == sid and "[4/4]" in terminal.stdout.getvalue()
    with session.lock(state.location(terminal.project_path)):
        terminal.onecmd("/demo --no-browser")
    assert len(started) == 1 and state.credentials(terminal.project_path) == credentials
    assert state.load(terminal.project_path) == profile
    assert all(method == "GET" for method, path in requests)
    engine.close.assert_called_once()


def test_demo_fails_closed_for_ambiguous_compose_project(terminal, monkeypatch):
    engine = MagicMock()
    engine.containers.list.return_value = [
        scoped_container(terminal.project_path, project="one"),
        scoped_container(terminal.project_path, project="two"),
    ]
    monkeypatch.setattr(demo.docker, "from_env", lambda **kwargs: engine)
    terminal.onecmd("/demo")
    assert "Multiple Compose projects" in terminal.stdout.getvalue()
    assert not (state.location(terminal.project_path) / "profile.json").exists()


def test_demo_without_compose_is_honest_and_never_starts_scripts(terminal, monkeypatch):
    from pathlib import Path

    (Path(terminal.project_path) / "compose.yaml").unlink()
    monkeypatch.setattr(
        terminal,
        "docker_ready",
        lambda: pytest.fail("Docker called for unsupported source-only repo"),
    )
    terminal.onecmd("/demo")
    assert (
        "Inventory complete" in terminal.stdout.getvalue()
        and "/lab demo" in terminal.stdout.getvalue()
    )


def test_demo_does_not_take_over_normal_session(terminal, monkeypatch):
    state.initialize(terminal.project_path)
    monkeypatch.setattr(terminal, "request", lambda *a, **k: {"read_only": False})
    monkeypatch.setattr(
        terminal, "start_watch", lambda *a: pytest.fail("External session taken over")
    )
    terminal.onecmd("/demo")
    assert "owning terminal" in terminal.stdout.getvalue()


@pytest.mark.parametrize("offset", [None, -60, 60, float("nan")])
def test_demo_rejects_missing_stale_future_or_invalid_poll_and_preserves_external_session(
    terminal, monkeypatch, offset
):
    state.initialize(terminal.project_path)
    times = iter([0, 0, 41])
    monkeypatch.setattr(demo.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(demo.time, "sleep", lambda seconds: None)
    at = None if offset is None else time.time() + offset

    def request(method, path):
        return {
            "/project": {"read_only": True},
            "/health": {"docker": "connected", "last_poll": at},
            "/settings": {"runtime": {"telemetry_max_age_seconds": 15}},
        }[path]

    monkeypatch.setattr(terminal, "request", request)
    monkeypatch.setattr(terminal, "start_watch", lambda *a: pytest.fail("Duplicate started"))
    monkeypatch.setattr(terminal, "stop_watch", lambda *a: pytest.fail("External monitor stopped"))
    terminal.onecmd("/demo --no-browser")
    assert "timed out" in terminal.stdout.getvalue() and "[4/4]" not in terminal.stdout.getvalue()


def test_demo_timeout_stops_only_its_owned_worker_and_does_not_claim_ready(terminal, monkeypatch):
    state.initialize(terminal.project_path)
    times = iter([0, 0, 41])
    monkeypatch.setattr(demo.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(demo.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        terminal,
        "request",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("No active project session")),
    )
    started = []
    stopped = []
    monkeypatch.setattr(terminal, "start_watch", lambda flags: started.append(flags))
    monkeypatch.setattr(terminal, "stop_watch", lambda: stopped.append(True))
    terminal.onecmd("/demo --no-browser")
    assert len(started) == 1 and stopped == [True]
    assert "timed out" in terminal.stdout.getvalue() and "[4/4]" not in terminal.stdout.getvalue()


def test_read_only_api_masks_permission_without_changing_persisted_choice_and_audits_denial(
    config, store, adapter, service
):
    config.project_context = {"read_only": True}
    with store.session.begin() as db:
        db.get(type(service), service.id).remediation_allowed = True
    app = create_app(config, store=store, runtime=Runtime(store, config, adapter=adapter))
    auth = {"Authorization": "Bearer " + config.admin_token}
    with TestClient(app) as http:
        assert http.get("/api/v1/services", headers=auth).json()[0]["remediation_allowed"] is False
        assert (
            http.get(f"/api/v1/services/{service.id}", headers=auth).json()["remediation_allowed"]
            is False
        )
        assert (
            http.patch(
                f"/api/v1/services/{service.id}/permissions",
                headers=auth,
                json={"monitored": True, "remediation_allowed": True},
            ).status_code
            == 403
        )
        aid = str(uuid.uuid4())
        assert (
            http.post(
                f"/api/v1/remediations/{aid}/approve",
                headers=auth,
                json={"action_digest": "a" * 64},
            ).status_code
            == 409
        )
        assert any(
            r["operation"] == "remediation.approval_denied"
            for r in http.get("/api/v1/audit", headers=auth).json()
        )
    with store.session() as db:
        assert db.get(type(service), service.id).remediation_allowed is True
    assert adapter.mutations == []


def test_cli_rejects_read_only_proposal_even_with_valid_digest_and_explicit_yes():
    aid = str(uuid.uuid4())
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": aid,
                "read_only": True,
                "status": "proposed",
                "incident_state": "AWAITING_APPROVAL",
                "remediation_allowed": True,
                "expires_at": time.time() + 60,
                "digest": "a" * 64,
            },
        )

    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(RuntimeError, match="normal monitoring"):
            cli.approval(http, aid, digest="a" * 64, yes=True)
    assert [r.method for r in requests] == ["GET"]
