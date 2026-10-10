"""Installed assets, consent, scoped commands and non-destructive REPL behavior."""

import io
import os
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest
from pulse.cli import main
from pulse.distribution import materialize
from pulse.repl import PulseRepl, mock_mode


def bundle(files):
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def shell(commands=""):
    result = PulseRepl(stdin=io.StringIO(commands), stdout=io.StringIO())
    result.use_rawinput = False
    return result


def test_bundle_upgrade_preserves_credentials_and_reports(tmp_path):
    root = tmp_path / "project"
    materialize(bundle({"examples/incident-lab/docker-compose.yml": "first"}), root)
    private = root / "examples/incident-lab/.env"
    private.write_text("private user state")
    reports = root / "examples/incident-lab/reports"
    reports.mkdir()
    (reports / "report.json").write_text("measured evidence")
    materialize(bundle({"examples/incident-lab/docker-compose.yml": "upgraded"}), root)
    assert private.read_text() == "private user state"
    assert (reports / "report.json").read_text() == "measured evidence"
    assert (root / "examples/incident-lab/docker-compose.yml").read_text() == "upgraded"


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/escape",
        "a\\escape",
        "examples/incident-lab/.env",
        "examples/incident-lab/reports/old.json",
    ],
)
def test_bundle_rejects_traversal_or_mutable_data_before_writing(tmp_path, name):
    with pytest.raises(RuntimeError, match="Invalid public"):
        materialize(bundle({"public.py": "ok", name: "unsafe"}), tmp_path / "project")
    assert not (tmp_path / "project").exists()


def test_bundle_refuses_to_write_through_outside_symlink(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "apps").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="unsafe symlink"):
        materialize(bundle({"apps/nested/source.py": "unsafe"}), root)
    assert not (outside / "nested").exists()


def test_capitalized_repl_entry_and_help(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("pulse.repl.run", lambda: calls.append("opened") or 0)
    assert main(["Repl"]) == 0
    assert calls == ["opened"]
    assert main([]) == 0
    assert "repl" in capsys.readouterr().out


def test_repl_demo_requires_explicit_consent(monkeypatch):
    terminal = shell("no\n")
    monkeypatch.setattr(
        terminal, "docker_ready", lambda: pytest.fail("Docker called without consent")
    )
    terminal.do_demo("")
    assert "Cancelled" in terminal.stdout.getvalue()


@pytest.mark.parametrize(
    "command,scenario", [("demo", "container-crash"), ("telemetry", "telemetry-loss")]
)
def test_repl_only_authorizes_the_selected_lab_scenario(monkeypatch, command, scenario, tmp_path):
    from pulse.lab import cli

    calls = []
    monkeypatch.setattr(cli, "LAB", tmp_path)
    terminal = shell("yes\n")
    monkeypatch.setattr(terminal, "docker_ready", lambda: True)
    monkeypatch.setattr(terminal, "ensure_lab", lambda: None)
    monkeypatch.setattr(cli, "main", lambda args: calls.append(args) or 0)
    getattr(terminal, "do_" + command)("")
    assert calls == [["lab", "run", scenario, "--approve"]]


def test_mock_model_is_process_scoped_and_restored_on_error(monkeypatch):
    monkeypatch.setenv("PULSE_LLM_MODEL", "original/model")
    monkeypatch.setenv("PULSE_LLM_API_KEY", "existing-key")
    with pytest.raises(ValueError), mock_mode():
        assert os.environ["PULSE_LLM_MODEL"] == "mock/evidence"
        assert os.environ["PULSE_LLM_API_KEY"] == ""
        raise ValueError()
    assert os.environ["PULSE_LLM_MODEL"] == "original/model"
    assert os.environ["PULSE_LLM_API_KEY"] == "existing-key"


def test_repl_stop_retains_data_and_exit_does_not_stop(monkeypatch, tmp_path):
    from pulse.lab import cli

    calls = []
    (tmp_path / ".env").touch()
    monkeypatch.setattr(cli, "LAB", tmp_path)
    monkeypatch.setattr(cli, "main", lambda args: calls.append(args) or 0)
    terminal = shell("yes\n")
    terminal.do_stop("")
    assert calls == [["lab", "stop"]]
    terminal.do_exit("")
    assert len(calls) == 1


def test_missing_docker_has_actionable_message(monkeypatch):
    monkeypatch.setattr("pulse.repl.shutil.which", lambda name: None)
    terminal = shell()
    assert not terminal.docker_ready()
    assert "Install Docker" in terminal.stdout.getvalue()


def test_lab_stop_never_removes_volumes(monkeypatch, capsys):
    from pulse.lab import cli

    calls = []
    monkeypatch.setattr(cli, "compose", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert cli.main(["lab", "stop"]) == 0
    assert calls == [(("stop",), {"dashboard": True})]
    assert "retained" in capsys.readouterr().out


def test_repl_status_does_not_create_credentials(monkeypatch, tmp_path):
    from pulse.lab import cli

    monkeypatch.setattr(cli, "LAB", tmp_path)
    monkeypatch.setattr(
        cli, "credentials", lambda: pytest.fail("Credentials created during status")
    )
    terminal = shell()
    terminal.do_status("")
    assert "not started" in terminal.stdout.getvalue()
    assert not (tmp_path / ".env").exists()


def test_eof_and_numeric_menu_exit_do_not_repeat_commands():
    terminal = shell("help\n\n0\n")
    terminal.cmdloop()
    output = terminal.stdout.getvalue()
    assert "Guided crash" in output and "Goodbye" in output


def test_end_of_input_leaves_the_repl():
    terminal = shell()
    terminal.cmdloop()
    output = terminal.stdout.getvalue()
    assert output.count("Goodbye") == 1
    assert "Unknown command" not in output


def test_failed_lab_does_not_claim_success(monkeypatch, tmp_path):
    from pulse.lab import cli

    terminal = shell("yes\n")
    monkeypatch.setattr(cli, "LAB", tmp_path)
    monkeypatch.setattr(terminal, "docker_ready", lambda: True)
    monkeypatch.setattr(terminal, "ensure_lab", lambda: None)
    monkeypatch.setattr(cli, "main", lambda args: 1)
    terminal.do_demo("")
    assert "Demo complete" not in terminal.stdout.getvalue()


def test_existing_nonmock_lab_is_not_reconfigured(monkeypatch, tmp_path):
    from pulse.lab import cli

    (tmp_path / ".env").touch()
    monkeypatch.setattr(cli, "LAB", tmp_path)
    import httpx

    monkeypatch.setattr(
        cli,
        "client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"model": "live/model"})
            ),
            base_url="http://localhost",
        ),
    )
    with pytest.raises(RuntimeError, match="existing lab uses another model"):
        shell().ensure_lab()


def test_new_installation_does_not_replace_existing_lab_credentials(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from pulse.lab import cli

    monkeypatch.setattr(cli, "LAB", tmp_path)
    monkeypatch.setattr(
        "pulse.repl.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="existing-lab-resource"),
    )
    monkeypatch.setattr(cli, "main", lambda args: pytest.fail("Existing lab was replaced"))
    with pytest.raises(RuntimeError, match="original installation and credentials"):
        shell().ensure_lab()
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("problem", ["none", "dirty", "wrong_remote"])
def test_homebrew_bootstrap_preserves_existing_taps(tmp_path, problem):
    tap = tmp_path / "tap"
    tap.mkdir()
    log = tmp_path / "calls"
    (tmp_path / "brew").write_text(
        '#!/bin/sh\nprintf "brew %s\\n" "$*" >> "$MOCK_LOG"\nif [ "$1" = "--repository" ]; then printf "%s\\n" "$MOCK_TAP"; fi\n'
    )
    (tmp_path / "git").write_text(
        '#!/bin/sh\nprintf "git %s\\n" "$*" >> "$MOCK_LOG"\ncase "$*" in\n *"remote get-url origin") printf "%s\\n" "$MOCK_REMOTE";;\n *"status --porcelain") printf "%s" "$MOCK_DIRTY";;\nesac\n'
    )
    for name in ("git", "brew"):
        (tmp_path / name).chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "MOCK_LOG": str(log),
        "MOCK_TAP": str(tap),
        "MOCK_REMOTE": "https://example.invalid/other.git"
        if problem == "wrong_remote"
        else "https://github.com/Devesh36/Pulse.git",
        "MOCK_DIRTY": "M Formula/pulse.rb" if problem == "dirty" else "",
    }
    result = subprocess.run(
        ["bash", str(Path(__file__).parents[1] / "scripts/install-homebrew.sh")],
        env=env,
        capture_output=True,
    )
    if problem == "none":
        assert result.returncode == 0
        assert "fetch origin work:refs/remotes/origin/work" in log.read_text()
        assert "install --HEAD devesh36/pulse/pulse" in log.read_text()
    else:
        assert result.returncode == 1
        assert "install --HEAD" not in log.read_text()
