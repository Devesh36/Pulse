import json
import time
import uuid
from unittest.mock import MagicMock

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from pulse.core.config import get_config
from pulse.project import cli, session, state
from pulse.project.scan import compose_services, scan
from pulse.repl import PulseRepl
from pulse.tools.docker_adapter import SDKAdapter
from pulse.tools.prometheus import UnconfiguredPrometheus

from apps.api.main import create_app


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "My Trading App"
    root.mkdir()
    (root / "compose.yaml").write_text("name: trading\nservices:\n  api:\n    image: example\n")
    monkeypatch.setenv("PULSE_HOME", str(tmp_path / "private"))
    return root


def test_inventory_reads_only_bounded_metadata(project):
    (project / "package.json").write_text(
        json.dumps({"dependencies": {"next": "16"}, "scripts": {"evil": "touch PWNED"}})
    )
    (project / ".env").write_text("PULSE_DATABASE_URL=secret\nAPI_KEY=private-secret")
    (project / "bank.py").write_text("raise RuntimeError('DO NOT IMPORT ME')")
    inventory = scan(project)
    assert inventory["frameworks"] == ["Next.js"]
    assert inventory["services"] == ["api"]
    assert inventory["compose_project"] == "trading"
    assert "private-secret" not in json.dumps(inventory)
    assert "scripts" not in inventory and not (project / "PWNED").exists()
    assert not state.location(project).exists()


def test_inventory_skips_external_symlinks_and_large_metadata(project, tmp_path):
    secret = tmp_path / "other.json"
    secret.write_text('{"dependencies":{"react":"1"}}')
    (project / "package.json").symlink_to(secret)
    (project / "pyproject.toml").write_bytes(b"a" * (1024 * 1024 + 1))
    inventory = scan(project)
    assert inventory["frameworks"] == [] and len(inventory["warnings"]) == 2


@pytest.mark.parametrize(
    "content",
    [
        "services: {api: &x {image: x}, other: *x}",
        "services: {api: !!python/object:os.system {}}",
        "include: ../other.yaml\nservices: {api: {image: x}}",
        "services: {api: {extends: {file: ../other.yaml}}}",
        "services: {../outside: {image: x}}",
        "services: {api: []}",
    ],
)
def test_compose_enrollment_fails_closed(project, content):
    (project / "compose.yaml").write_text(content)
    with pytest.raises((RuntimeError, yaml.YAMLError)):
        compose_services(project / "compose.yaml", project)
    with pytest.raises((RuntimeError, yaml.YAMLError)):
        state.initialize(project)
    assert not (state.location(project) / "profile.json").exists()


def test_init_retains_identity_credentials_history_and_declares_only_selected_recovery(project):
    profile = state.initialize(project, recovery_services=["api"])
    folder = state.location(project)
    tokens = state.credentials(project)
    (folder / "pulse.db").write_bytes(b"preserved database")
    assert state.initialize(project) == profile
    assert state.credentials(project) == tokens
    assert (folder / "pulse.db").read_bytes() == b"preserved database"
    assert (folder / "credentials.json").stat().st_mode & 0o777 == 0o600
    override = json.loads((folder / "monitor.compose.json").read_text())
    assert override["services"]["api"]["labels"] == {
        "pulse.monitor": "true",
        "pulse.remediate": "true",
        "pulse.environment": "development",
    }
    assert (project / "compose.yaml").read_text().endswith("image: example\n")
    with pytest.raises(RuntimeError, match="already exists"):
        state.initialize(project, project="other")


def test_read_only_enrollment_and_scope_change_fail_closed(project):
    state.initialize(project)
    override = json.loads((state.location(project) / "monitor.compose.json").read_text())
    assert override["services"]["api"]["labels"] == {"pulse.monitor": "true"}
    (project / "compose.yaml").write_text("services: {new: {image: x}}")
    with pytest.raises(RuntimeError, match="services changed"):
        state.load(project)


@pytest.mark.parametrize(
    "field,value",
    [
        ("inventory", {}),
        ("root", "/other"),
        ("compose_file", "../other"),
        ("recovery_services", [1]),
        ("prometheus_url", None),
    ],
)
def test_malformed_saved_profiles_do_not_expand_scope(project, field, value):
    profile = state.initialize(project)
    profile[field] = value
    state.atomic_json(state.location(project) / "profile.json", profile)
    with pytest.raises((RuntimeError, OSError)):
        state.load(project)


@pytest.mark.parametrize(
    "url",
    [
        "https://outside.example/health",
        "http://user:secret@localhost/health",
        "http://127.0.0.1/health?token=x",
        "file:///tmp/x",
        "http://localhost:invalid",
        None,
    ],
)
def test_probe_urls_require_explicit_loopback_allowlist(url):
    with pytest.raises(RuntimeError):
        state.endpoint(url)


def test_state_symlinks_and_duplicate_sessions_are_rejected(project, tmp_path):
    state.initialize(project)
    folder = state.location(project)
    with session.lock(folder), pytest.raises(RuntimeError, match="Another Pulse watch"):
        with session.lock(folder):
            pytest.fail("duplicate session")
    target = folder / "credentials.json"
    target.unlink()
    target.symlink_to(tmp_path / "victim")
    with pytest.raises(RuntimeError):
        state.credentials(project)
    with pytest.raises(RuntimeError):
        state.atomic_json(target, {})
    assert not (tmp_path / "victim").exists()


def test_sdk_repository_service_scope_even_with_shared_project_name(project, tmp_path):
    engine = MagicMock()
    containers = []
    for root, service in [(project, "api"), (tmp_path / "other", "api"), (project, "database")]:
        container = MagicMock()
        container.labels = {
            "pulse.monitor": "true",
            "pulse.remediate": "true",
            "pulse.environment": "development",
            "com.docker.compose.project": "trading",
            "com.docker.compose.project.working_dir": str(root),
            "com.docker.compose.service": service,
        }
        containers.append(container)
    engine.containers.list.return_value = containers
    adapter = SDKAdapter(engine, project="trading", resource_root=str(project), services=["api"])
    adapter.snapshot = lambda item: {"id": id(item)}
    assert adapter.discover() == [{"id": id(containers[0])}]
    for excluded in containers[1:]:
        engine.containers.get.return_value = excluded
        with pytest.raises(PermissionError):
            adapter.container("a" * 64)
        excluded.start.assert_not_called()
        excluded.restart.assert_not_called()


def test_native_children_ignore_target_environment_and_isolate_database(project, monkeypatch):
    state.initialize(project)
    monkeypatch.setenv("PULSE_DATABASE_URL", "postgresql://do-not-use")
    monkeypatch.setenv("PULSE_RESOURCE_PROJECT", "wrong-project")
    monkeypatch.setenv("PULSE_LAB_ENABLED", "true")
    monkeypatch.setenv("PULSE_LLM_API_KEY", "configured-secret")
    api, gateway = session.environment(state.load(project), state.location(project), 8765, "")
    assert api["PULSE_DATABASE_URL"].startswith("sqlite:///")
    assert str(state.location(project)) in api["PULSE_DATABASE_URL"]
    assert gateway["PULSE_RESOURCE_ROOT"] == str(project)
    assert gateway["PULSE_RESOURCE_PROJECT"] == "trading"
    assert json.loads(gateway["PULSE_RESOURCE_SERVICES"]) == ["api"]
    assert api["PULSE_PROMETHEUS_URL"] == ""
    assert api["PULSE_LAB_ENABLED"] == gateway["PULSE_LAB_ENABLED"] == "false"
    assert "PULSE_LLM_API_KEY" not in gateway
    monkeypatch.chdir(project)
    (project / ".env").write_text("PULSE_WEB_ORIGIN=http://untrusted\n")
    monkeypatch.setenv("PULSE_PROJECT_SESSION", "true")
    get_config.cache_clear()
    try:
        assert get_config().web_origin == "http://localhost:3000"
    finally:
        get_config.cache_clear()


def test_wrong_project_port_receives_no_credentials(project, monkeypatch):
    state.initialize(project)
    state.atomic_json(state.location(project) / "active.json", {"port": 8765})
    requests = []
    original = httpx.Client

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"project_id": "different"})

    monkeypatch.setattr(
        session.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(RuntimeError, match="another project"):
        session.client(project)
    assert len(requests) == 1 and "authorization" not in requests[0].headers


def test_terminal_command_reuses_handshaken_client_and_closes_it(project, monkeypatch, capsys):
    state.initialize(project)
    state.atomic_json(state.location(project) / "active.json", {"port": 8765})
    requests = []
    clients = []
    original = httpx.Client

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("identity"):
            assert "authorization" not in request.headers
            return httpx.Response(200, json={"project_id": scan(project)["id"]})
        assert (
            request.headers["authorization"]
            == "Bearer " + state.credentials(project)["admin_token"]
        )
        return httpx.Response(200, json=[])

    def connection(**kwargs):
        client = original(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(client)
        return client

    monkeypatch.setattr(session.httpx, "Client", connection)
    assert cli.main(["incidents", str(project)]) == 0
    assert "No recorded incidents" in capsys.readouterr().out
    assert len(requests) == 2 and clients[0].is_closed


def test_project_dashboard_is_authenticated_and_lab_mutations_disabled(
    config, store, runtime, project
):
    config.project_context = {"inventory": scan(project), "root": str(project)}
    with TestClient(create_app(config, store, runtime)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/_pulse/dashboard.js").status_code == 200
        assert client.get("/api/v1/project/identity").json() == {"project_id": scan(project)["id"]}
        assert client.get("/api/v1/project").status_code == 401
        auth = {"Authorization": f"Bearer {config.admin_token}"}
        assert client.get("/api/v1/project", headers=auth).json()["root"] == str(project)
        assert client.post("/api/v1/lab/reset", headers=auth).status_code == 403
        assert config.admin_token not in client.get("/", headers=auth).text
        assert "project_id" not in client.get("/api/v1/health").json()


@pytest.mark.parametrize(
    "mode",
    [
        "decline",
        "end_of_input",
        "bad_digest",
        "expired",
        "replay",
        "no_permission",
        "unbound_yes",
        "approve",
    ],
)
def test_terminal_approves_only_reviewed_current_digest(mode):
    aid = str(uuid.uuid4())
    action = {
        "id": aid,
        "status": "proposed",
        "expires_at": time.time() + 100,
        "incident_state": "AWAITING_APPROVAL",
        "remediation_allowed": True,
        "digest": "reviewed-digest",
        "service_name": "api",
        "service_id": str(uuid.uuid4()),
        "container_id": "a" * 64,
        "kind": "start",
        "reason": "stopped",
    }
    if mode == "expired":
        action["expires_at"] = 0
    if mode == "replay":
        action["status"] = "executed"
    if mode == "no_permission":
        action["remediation_allowed"] = False
    mutations = []

    def answer(_):
        if mode == "end_of_input":
            raise EOFError
        return "yes" if mode == "approve" else ""

    def respond(request):
        if request.method == "POST":
            mutations.append(json.loads(request.content))
        return httpx.Response(200, json=action)

    with httpx.Client(
        base_url="http://127.0.0.1/api/v1/", transport=httpx.MockTransport(respond)
    ) as http:
        if mode in {"bad_digest", "expired", "replay", "no_permission", "unbound_yes"}:
            with pytest.raises(RuntimeError):
                cli.approval(
                    http, aid, "wrong" if mode == "bad_digest" else None, mode == "unbound_yes"
                )
        else:
            assert cli.approval(http, aid, prompt=answer) == (mode == "approve")
    assert mutations == ([{"action_digest": "reviewed-digest"}] if mode == "approve" else [])


def test_repl_preserves_case_and_spaces(project):
    shell = PulseRepl(repo=str(project))
    assert shell.project_path == str(project)
    assert shell.precmd(f"SCAN '{project}'") == f"scan '{project}'"


def test_saved_report_available_without_live_runtime(project, monkeypatch, capsys):
    state.initialize(project)
    iid = str(uuid.uuid4())
    report = {
        "id": iid,
        "title": "Real observation",
        "state": "FAILED",
        "verification": {"result": "INCONCLUSIVE", "reason": "Missing evidence"},
        "tools": [],
        "timeline": [],
        "secret": "token=private-value",
    }
    state.atomic_json(state.location(project) / "reports" / f"incident-{iid}.json", report)
    monkeypatch.setattr(
        session, "client", lambda *_: pytest.fail("offline report made a live request")
    )
    assert cli.main(["report", "--repo", str(project), "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert "INCONCLUSIVE" in output and "private-value" not in output


async def test_missing_prometheus_is_explicit_not_a_zero_sample():
    result = await UnconfiguredPrometheus().query("latency", "api")
    assert result["available"] is False and result["value"] is None
    assert result["sample_at"] is None and "not configured" in result["reason"]


async def test_provider_receives_only_known_inventory_facts(config, monkeypatch):
    import litellm
    from pulse.agents.investigator import Model

    config.llm_model = "test/provider"
    config.project_context = {
        "root": "/private/banking-project",
        "inventory": {
            "languages": ["Python"],
            "frameworks": ["FastAPI"],
            "raw_source": "DO NOT SEND",
            "metadata_files": ["private-name"],
        },
        "services": ["api"],
    }
    captured = {}

    async def provider(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("mocked provider failure")

    monkeypatch.setattr(litellm, "token_counter", lambda **_: 100)
    monkeypatch.setattr(litellm, "acompletion", provider)
    with pytest.raises(RuntimeError, match="mocked provider"):
        await Model(config).decide(
            {
                "service_name": "api",
                "container_id": "a" * 64,
                "kind": "stopped",
                "question": "",
                "evidence": [],
                "limitations": [],
                "iteration": 1,
                "token_budget": 12000,
                "tokens_used": 0,
            }
        )
    context = json.loads(captured["messages"][1]["content"])
    assert context["project_inventory"]["frameworks"] == ["FastAPI"]
    assert context["project_inventory"]["declared_services"] == ["api"]
    assert "DO NOT SEND" not in json.dumps(context) and "banking-project" not in json.dumps(context)
    assert captured["num_retries"] == 0 and captured["max_tokens"] <= 1800
