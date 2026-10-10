"""Interactive commands stay scoped, recover from input errors and own only their processes."""

import io
import json
import os
import subprocess
import sys
import time
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from pulse.project import state
from pulse.repl import PulseRepl, terminal_completion

SID = str(uuid.uuid4())
IID = str(uuid.uuid4())
AID = str(uuid.uuid4())
DIGEST = "d" * 64


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    repo = tmp_path / "Trading App"
    repo.mkdir()
    (repo / "compose.yaml").write_text("name: trading\nservices:\n  api:\n    image: example\n")
    monkeypatch.setenv("PULSE_HOME", str(tmp_path / "private"))
    shell = PulseRepl(repo=str(repo), stdin=io.StringIO(), stdout=io.StringIO())
    shell.use_rawinput = False
    yield shell
    if shell.watch_stream is not None:
        shell.watch_stream.close()


def api(monkeypatch, responses):
    requests = []
    clients = []

    def response(request):
        requests.append(request)
        value = responses[request.url.path]
        return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)

    def client(repo):
        result = httpx.Client(transport=httpx.MockTransport(response), base_url="http://127.0.0.1")
        clients.append(result)
        return result

    monkeypatch.setattr("pulse.project.session.client", client)
    return requests, clients


def service(**extra):
    return {
        "id": SID,
        "name": "api",
        "monitored": True,
        "remediation_allowed": False,
        "snapshot": {"status": "running"},
        "metrics": None,
        **extra,
    }


def test_slash_commands_help_and_case_preserve_arguments(terminal):
    assert terminal.precmd("/ASK Why Is API Slow?") == "ask Why Is API Slow?"
    terminal.onecmd("/help ask")
    assert "read-only" in terminal.stdout.getvalue()
    terminal.onecmd("/help")
    assert "/permissions" in terminal.stdout.getvalue()
    terminal.onecmd("/servics")
    assert "Did you mean /services" in terminal.stdout.getvalue()


@pytest.mark.parametrize(
    "text,line,start,end,expected",
    [
        ("ser", "/ser", 1, 4, "services"),
        ("/ser", "/ser", 0, 4, "/services"),
        ("sta", "sta", 0, 3, "status"),
        ("ask", "/help ask", 6, 9, "ask"),
    ],
)
def test_completion_never_connects_to_api(terminal, monkeypatch, text, line, start, end, expected):
    monkeypatch.setattr(terminal, "request", lambda *a, **k: pytest.fail("API used while typing"))
    assert expected in terminal.completions(text, line, start, end)


@pytest.mark.parametrize(
    "command",
    [
        "/incidents --bad-flag",
        "/approve",
        "/watch --port banana",
        "/watch --help",
        "/scan '",
        "/stop --everything",
    ],
)
def test_bad_arguments_and_help_do_not_close_repl(terminal, command):
    assert not terminal.onecmd(command)
    assert not terminal.onecmd("/context")
    assert "Repository:" in terminal.stdout.getvalue()


def test_empty_line_does_not_repeat_ask_or_approval(terminal, monkeypatch):
    calls = []
    monkeypatch.setattr(terminal, "do_approve", lambda value: calls.append(value))
    terminal.onecmd("/approve " + AID)
    terminal.onecmd("")
    assert calls == [AID]


def test_question_requires_selected_monitored_service_and_never_approves(terminal, monkeypatch):
    requests, clients = api(
        monkeypatch, {"/services": [service()], "/chat": {"incident_id": IID, "accepted": True}}
    )
    terminal.onecmd("/ask Why is API slow?")
    assert not requests
    terminal.onecmd("/use api")
    terminal.onecmd("/ask Why is API slow?")
    assert json.loads(requests[-1].content) == {"message": "Why is API slow?", "service_id": SID}
    assert [r.url.path for r in requests] == ["/services", "/chat"]
    assert all(c.is_closed for c in clients)
    assert f"/inspect {IID}" in terminal.stdout.getvalue()


@pytest.mark.parametrize(
    "rows", [[service(monitored=False)], [service(), service(id=str(uuid.uuid4()))]]
)
def test_use_rejects_unmonitored_and_ambiguous_service(terminal, monkeypatch, rows):
    api(monkeypatch, {"/services": rows})
    terminal.onecmd("/use api")
    assert terminal.service_id is None


@pytest.mark.parametrize(
    "command",
    [
        "/ask ",
        "/ask " + "x" * 2001,
        "/logs 301",
        "/logs 0",
        "/logs nope",
        "/inspect ../../outside",
        "/timeline invalid",
    ],
)
def test_invalid_evidence_requests_do_not_touch_api(terminal, monkeypatch, command):
    terminal.service_id = SID
    monkeypatch.setattr(terminal, "request", lambda *a, **k: pytest.fail("Invalid request sent"))
    terminal.onecmd(command)


def test_evidence_output_is_redacted_and_missing_metrics_not_called_healthy(terminal, monkeypatch):
    api(
        monkeypatch,
        {
            "/services": [service()],
            f"/incidents/{IID}": {
                "reason": "token=private-value",
                "result": "INCONCLUSIVE",
                "log": "\u001b[2J",
            },
        },
    )
    terminal.onecmd("/services")
    terminal.onecmd("/inspect " + IID)
    output = terminal.stdout.getvalue()
    assert "metrics=unavailable" in output and "INCONCLUSIVE" in output
    assert "private-value" not in output and "\u001b" not in output


def test_reinvestigation_is_default_deny(terminal, monkeypatch):
    requests, _ = api(monkeypatch, {f"/incidents/{IID}/investigate": {"accepted": True}})
    terminal.onecmd("/investigate " + IID)
    assert not requests
    terminal.stdin = io.StringIO("yes\n")
    terminal.onecmd("/investigate " + IID)
    assert len(requests) == 1 and requests[0].method == "POST"


def test_approval_uses_repl_input_and_existing_exact_digest_gate(terminal, monkeypatch):
    action = {
        "id": AID,
        "status": "proposed",
        "incident_state": "AWAITING_APPROVAL",
        "remediation_allowed": True,
        "expires_at": time.time() + 60,
        "digest": DIGEST,
        "service_id": SID,
        "service_name": "api",
        "container_id": "selected",
        "kind": "start",
        "reason": "observed exit",
    }
    requests, _ = api(
        monkeypatch,
        {f"/remediations/{AID}": action, f"/remediations/{AID}/approve": {"accepted": True}},
    )
    terminal.onecmd("/approve " + AID)
    assert len(requests) == 1
    terminal.stdin = io.StringIO("yes\n")
    terminal.onecmd("/approve " + AID)
    assert len(requests) == 3
    assert json.loads(requests[-1].content) == {"action_digest": DIGEST}


def test_api_failure_and_ctrl_c_do_not_exit_or_retry(terminal, monkeypatch):
    requests, _ = api(
        monkeypatch, {"/services": httpx.Response(503, json={"detail": "token=private"})}
    )
    assert not terminal.onecmd("/services")
    assert len(requests) == 1 and "503" in terminal.stdout.getvalue()
    monkeypatch.setattr(
        terminal, "do_services", lambda arg: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    assert not terminal.onecmd("/services")
    assert "Cancelled" in terminal.stdout.getvalue()


@pytest.mark.parametrize(
    "backend,binding",
    [("libedit readline", "bind ^I rl_complete"), ("GNU readline", "tab: complete")],
)
def test_readline_backend_binding_restores_completer_and_does_not_save_history(
    terminal, monkeypatch, backend, binding
):
    editor = SimpleNamespace(
        __doc__=backend,
        set_auto_history=MagicMock(),
        get_completer=MagicMock(return_value="previous"),
        set_completer=MagicMock(),
        parse_and_bind=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "readline", editor)
    restore = terminal_completion(terminal)
    editor.set_auto_history.assert_called_once_with(False)
    editor.parse_and_bind.assert_called_once_with(binding)
    assert terminal.completekey is None
    restore()
    assert editor.set_completer.call_args.args == ("previous",)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="PTY acceptance requires POSIX; command completion has backend-independent unit coverage",
)
def test_actual_terminal_tab_completion_and_slash_help():
    pytest.importorskip("readline")
    import pty
    import select

    master, slave = pty.openpty()
    process = subprocess.Popen(
        [sys.executable, "-m", "pulse.cli", "repl"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    transcript = b""

    def collect(predicate):
        nonlocal transcript
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if predicate():
                return
            if select.select([master], [], [], 0.1)[0]:
                try:
                    transcript += os.read(master, 65536)
                except OSError:
                    break
        assert predicate(), transcript.decode(errors="replace")

    try:
        collect(lambda: b"pulse [" in transcript and b"\xe2\x80\xba " in transcript)
        os.write(master, b"/hel\t\n")
        collect(lambda: transcript.count(b"Project\r\n") >= 2)
        os.write(master, b"/help ask\n/exit\n")
        collect(lambda: b"Goodbye." in transcript)
        process.wait(timeout=5)
        assert process.returncode == 0
        assert b"Request a bounded read-only investigation" in transcript
        assert b"Unknown command" not in transcript
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)


def fake_watch(terminal, monkeypatch):
    state.initialize(terminal.project_path)
    process = MagicMock()
    process.poll.return_value = None
    calls = []

    def launch(args, **kwargs):
        calls.append((args, kwargs))
        return process

    monkeypatch.setattr("pulse.repl_project.subprocess.Popen", launch)
    terminal.onecmd("/watch --no-browser --port 9345")
    return process, calls


def test_watch_background_is_owned_and_keeps_commands_available(terminal, monkeypatch):
    process, calls = fake_watch(terminal, monkeypatch)
    assert calls[0][0][:3] == [os.sys.executable, "-m", "pulse.project.repl_worker"]
    assert calls[0][1]["env"]["PULSE_SESSION_OWNER"] == str(os.getpid())
    assert calls[0][1]["stdin"] == subprocess.DEVNULL
    assert calls[0][1]["start_new_session"] is True
    assert os.stat(terminal.watch_log).st_mode & 0o777 == 0o600
    terminal.onecmd("/context")
    terminal.onecmd("/watch")
    assert len(calls) == 1 and terminal.watch_process is process


def test_switching_project_requires_stopping_owned_watch(terminal, monkeypatch, tmp_path):
    fake_watch(terminal, monkeypatch)
    other = tmp_path / "Other"
    other.mkdir()
    before = terminal.project_path
    terminal.onecmd(f'/open "{other}"')
    assert terminal.project_path == before
    terminal.watch_process.poll.return_value = 0
    terminal.service_id = SID
    terminal.onecmd(f'/open "{other}"')
    assert terminal.project_path == str(other) and terminal.service_id is None


def test_stop_and_exit_target_only_owned_watch(terminal, monkeypatch):
    process, _ = fake_watch(terminal, monkeypatch)
    stopped = []

    def stop(child):
        stopped.append(child)
        child.poll.return_value = 0
        child.returncode = 0

    monkeypatch.setattr("pulse.project.session.stop", stop)
    assert terminal.onecmd("/exit")
    terminal.onecmd("/stop")
    assert stopped == [process] and terminal.watch_process is None
    assert (state.location(terminal.project_path) / "profile.json").exists()


def test_watch_notifications_do_not_follow_replaced_log_path(terminal, monkeypatch, tmp_path):
    fake_watch(terminal, monkeypatch)
    log = terminal.watch_log
    with open(log, "a") as output:
        output.write("Observed incident; no recovery approved\n")
    os.unlink(log)
    secret = tmp_path / "secret"
    secret.write_text("DO NOT READ")
    os.symlink(secret, log)
    terminal.postcmd(False, "/context")
    assert "Observed incident" in terminal.stdout.getvalue()
    assert "DO NOT READ" not in terminal.stdout.getvalue()


def test_clear_retains_context_and_model_inspection_excludes_credentials(terminal, monkeypatch):
    api(
        monkeypatch,
        {
            "/settings": {
                "model": "",
                "runtime": {"max_iterations": 4},
                "api_key": "DO NOT PRINT",
                "api_base": "DO NOT PRINT",
            }
        },
    )
    terminal.service_id = SID
    terminal.onecmd("/clear")
    terminal.onecmd("/model")
    assert terminal.service_id == SID
    assert "deterministic evidence" in terminal.stdout.getvalue()
    assert "DO NOT PRINT" not in terminal.stdout.getvalue()
