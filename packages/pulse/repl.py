"""Project-aware interactive commands and consent-based incident lab demonstrations."""

import difflib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager, redirect_stderr, redirect_stdout

import httpx
import yaml

from pulse.repl_project import ProjectCommands


@contextmanager
def mock_mode():
    names = ("PULSE_LLM_MODEL", "PULSE_LLM_API_KEY", "PULSE_LLM_API_BASE")
    before = {key: os.environ.get(key) for key in names}
    os.environ.update(PULSE_LLM_MODEL="mock/evidence", PULSE_LLM_API_KEY="", PULSE_LLM_API_BASE="")
    try:
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class PulseRepl(ProjectCommands):
    prompt = "pulse › "
    intro = "\nPulse — evidence before action.\n/help for commands · Tab to complete · Ctrl+C to cancel · /exit to leave\n"
    MENU = """Project
  /demo [FLAGS]   Scan, prepare and open this project's read-only dashboard
  /open PATH       Select a repository (quote paths with spaces)
  /scan            Inventory its metadata; never execute its scripts
  /init            Prepare enrollment for you to review and apply
  /watch [FLAGS]   Start monitoring in the background; keep this REPL open
  /status          Check selected project readiness, telemetry and model
  /context         Show repository and selected service scope
  /model           Show reasoning mode and investigation budgets
  /dashboard       Open the local workspace
  /stop            Stop only monitoring owned by this REPL
Investigate
  /services        List scoped services and evidence availability
  /use NAME|UUID   Select a monitored service (/use clears selection)
  /ask QUESTION    Ask about its runtime evidence; never approve recovery
  /logs [LIMIT]    Read selected service logs (default 50, maximum 300)
  /incidents       List project incidents
  /inspect UUID    Read diagnosis, actions and verification evidence
  /timeline UUID   Read persisted incident events
  /investigate ID  Confirm a read-only reinvestigation; invalidate old proposals
  /report          Read the latest retained report, including offline
Decide
  /approve ID      Review and approve one exact, expiring action
  /reject ID       Reject a proposal; handle the issue yourself
  /permissions ID  Explicitly change service recovery permission
  /recheck ID      Verify again without replaying remediation
Incident lab
  /lab demo        Guided crash → investigation → approved recovery
  2 / telemetry    Missing evidence → inconclusive → restored recovery
  /lab status      Check the lab explicitly, even with a selected project
  /lab dashboard   Open the lab workspace
  /lab stop        Confirm stopping the lab; keep data
  5 / reports      Show measured evaluation results
  7 / quality      Review retained measurements offline
Session
  /help [COMMAND]  Command reference and detailed help
  /clear           Clear the visible terminal; retain evidence and context
  0 / exit         Stop owned project monitoring and leave
Slash prefixes are optional. Legacy numeric shortcuts 3–6 also work.
"""

    def __init__(self, *args, repo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_path = None
        self.service_id = None
        self.watch_process = None
        self.watch_log = None
        self.watch_stream = None
        self.watch_offset = 0
        if repo:
            self.do_open(shlex.quote(repo))

    def preloop(self):
        self.stdout.write(self.MENU + "\n\n")

    def precmd(self, line):
        aliases = {
            "1": "demo",
            "2": "telemetry",
            "3": "dashboard",
            "4": "status",
            "5": "reports",
            "6": "stop",
            "7": "quality",
            "0": "exit",
        }
        stripped = line.strip()
        if stripped in aliases:
            return aliases[stripped]
        parts = stripped.split(None, 1)
        if not parts:
            return ""
        return parts[0].lstrip("/").lower() + (" " + parts[1] if len(parts) > 1 else "")

    def onecmd(self, line):
        try:
            normalized = self.precmd(line)
            parts = normalized.split(None, 1)
            if len(parts) == 2 and parts[0] in {
                "context",
                "services",
                "status",
                "stop",
                "clear",
                "exit",
                "quit",
                "telemetry",
                "reports",
                "quality",
            }:
                raise RuntimeError(f"/{parts[0]} takes no arguments. See /help {parts[0]}.")
            return super().onecmd(normalized)
        except SystemExit:
            # argparse's help and invalid arguments must not terminate monitoring.
            return False
        except KeyboardInterrupt:
            self.emit("Cancelled. No action is automatically retried.")
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self.emit(
                f"Project API returned {status}. Inspect /status and /incidents; no request is automatically retried."
            )
        except httpx.HTTPError:
            self.emit(
                "Project API unavailable. Use /watch, then /status; unavailable telemetry is not healthy."
            )
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
            self.emit(
                str(error)
                if isinstance(error, RuntimeError)
                else f"Command unavailable: {type(error).__name__}. See /help for usage."
            )
        return False

    def postcmd(self, stop, line):
        self.watch_updates()
        return stop

    def completions(self, text, line, begidx, endidx):
        """Pure command-name completion; never call a model or API while typing."""
        before = line[:endidx].lstrip()
        if len(before.split()) <= 1 and not before.endswith(" "):
            prefix = before.lstrip("/").lower()
            return [
                name[begidx:] if begidx == 0 else name.lstrip("/")
                for name in [
                    ("/" if before.startswith("/") else "") + command
                    for command in self.command_names()
                    if command.startswith(prefix)
                ]
            ]
        if line.lstrip().split(None, 1)[0].lstrip("/").lower() == "help":
            return [name for name in self.command_names() if name.startswith(text.lstrip("/"))]
        return []

    def complete(self, text, state):
        import readline

        if state == 0:
            line = readline.get_line_buffer()
            self.completion_matches = self.completions(
                text, line, readline.get_begidx(), readline.get_endidx()
            )
        matches = self.completion_matches or []
        return matches[state] if state < len(matches) else None

    def command_names(self):
        return sorted(
            {
                name[3:]
                for name in dir(self)
                if name.startswith("do_") and name not in {"do_EOF", "do_eof"}
            }
        )

    def do_open(self, arg):
        """Select a repository without executing it or starting monitoring."""
        from pulse.project.scan import repository

        try:
            parts = shlex.split(arg)
            if len(parts) != 1:
                raise RuntimeError("Use open PATH, quoting paths that contain spaces")
            selected = str(repository(parts[0]))
            if (
                self.watch_process is not None
                and self.watch_process.poll() is None
                and selected != self.project_path
            ):
                self.emit(
                    "Use /stop before switching repositories; monitoring remains on the current project."
                )
                return
            if selected != self.project_path:
                self.service_id = None
            self.project_path = selected
            from pulse.project.cli import safe_text

            self.prompt = f"pulse [{safe_text(repository(selected).name)}] › "
            self.emit(
                f"Selected repository: {self.project_path}\nType scan, init, then watch. No application command was executed."
            )
        except (OSError, ValueError, RuntimeError) as error:
            self.stdout.write(
                f"Repository could not be opened: {type(error).__name__}. Check the path.\n"
            )

    def project_command(self, command, arg=""):
        if not self.project_path:
            self.stdout.write(
                "Select your project with open PATH first. Demo commands remain available.\n"
            )
            return
        from pulse.project.cli import main

        try:
            arguments = shlex.split(arg)
        except ValueError:
            self.stdout.write("Invalid command quoting.\n")
            return
        path = (
            [self.project_path]
            if command in {"scan", "init", "watch", "dashboard", "incidents"}
            else ["--repo", self.project_path]
        )
        with redirect_stdout(self.stdout), redirect_stderr(self.stdout):
            main([command, *arguments, *path], approval_prompt=self.read_answer)

    def do_scan(self, arg):
        """Inventory selected repository metadata without executing its scripts."""
        self.project_command("scan", arg)

    def do_init(self, arg):
        """Prepare a private project profile and an enrollment override to review."""
        self.project_command("init", arg)

    def do_watch(self, arg):
        """/watch [--port PORT] [--model PROVIDER/MODEL] [--no-browser] — Start owned background monitoring. /stop or /exit stops it; your application and history remain."""
        with redirect_stdout(self.stdout), redirect_stderr(self.stdout):
            self.start_watch(arg)

    def do_incidents(self, arg):
        """Show the selected project's incident state."""
        self.project_command("incidents", arg)

    def do_report(self, arg):
        """Read the selected project's retained incident report."""
        self.project_command("report", arg)

    def do_approve(self, arg):
        """Review and approve an exact, expiring project action."""
        self.project_command("approve", arg)

    def do_reject(self, arg):
        """Reject the selected project's action; handle the issue yourself."""
        self.project_command("reject", arg)

    def do_permissions(self, arg):
        """Set the selected project's service permission; approvals remain required."""
        self.project_command("permissions", arg)

    def do_recheck(self, arg):
        """Request read-only recovery verification for the selected project."""
        self.project_command("recheck", arg)

    def emptyline(self):
        pass

    def default(self, line):
        command = line.split(None, 1)[0].lstrip("/")
        matches = difflib.get_close_matches(command, self.command_names(), n=1, cutoff=0.6)
        hint = (
            f" Did you mean /{matches[0]}?"
            if matches
            else " Use /ask QUESTION for runtime questions."
        )
        self.emit("Unknown command." + hint + " /help lists commands.")

    def do_help(self, arg):
        """/help [COMMAND] — Show the grouped command reference or help for one command."""
        command = arg.strip().lstrip("/").lower()
        if not command:
            self.stdout.write(self.MENU + "\n")
        elif command in self.command_names():
            self.emit(getattr(self, "do_" + command).__doc__ or "No detailed help available.")
            from pulse.project.cli import COMMANDS, main

            with redirect_stdout(self.stdout), redirect_stderr(self.stdout):
                if command == "watch":
                    self.start_watch("--help")
                elif command in COMMANDS:
                    main([command, "--help"])
        else:
            self.default(command)

    def do_clear(self, arg):
        """/clear — Clear visible terminal output; retain scope, reports and audit history."""
        if getattr(self.stdout, "isatty", lambda: False)():
            self.stdout.write("\033[2J\033[H")
        else:
            self.emit(
                "Clear is available in an interactive terminal. Context and evidence are retained."
            )

    def read_answer(self, prompt):
        self.stdout.write(prompt)
        self.stdout.flush()
        return self.stdin.readline()

    def confirm(self, message):
        self.emit(message)
        return self.read_answer("Continue? [y/N] ").strip().lower() in {"y", "yes"}

    def docker_ready(self):
        if not shutil.which("docker"):
            self.stdout.write(
                "Install Docker Desktop (or Docker Engine + Compose), then start it and try demo again.\n"
            )
            return False
        for args in (
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            ["docker", "compose", "version"],
        ):
            try:
                result = subprocess.run(args, capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                result = None
            if not result or result.returncode:
                self.stdout.write("Docker or Compose is unavailable. Start Docker and try again.\n")
                return False
        return True

    def ensure_lab(self):
        from pulse.lab import cli

        if not (cli.LAB / ".env").exists():
            for args in (
                [
                    "docker",
                    "ps",
                    "-a",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=pulse-lab",
                ],
                [
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=pulse-lab",
                ],
            ):
                existing = subprocess.run(args, capture_output=True, text=True, timeout=15)
                if existing.returncode or existing.stdout.strip():
                    raise RuntimeError(
                        "Existing lab resources need their original installation and credentials; no replacement credentials were created"
                    )
        if (cli.LAB / ".env").exists():
            with cli.client() as http:
                response = http.get("/settings")
                if response.is_success:
                    if response.json()["model"] != "mock/evidence":
                        raise RuntimeError(
                            "The existing lab uses another model. Start a mock/evidence lab explicitly before using this demo."
                        )
                    cli.ready(http)
                    return
                if response.status_code in (401, 403):
                    raise RuntimeError(
                        "A different lab occupies port 8100; use its own installation to stop it first"
                    )
        with mock_mode():
            if cli.main(["lab", "up", "--dashboard"]):
                raise RuntimeError("Lab startup did not complete; check Docker and retry")

    def demonstrate(self, scenario):
        if not self.confirm(
            "This starts only the pulse-lab demo and approves its scoped test action. Reasoning is mocked; measurements are real. The first build can take several minutes."
        ):
            self.stdout.write("Cancelled; no demo action was authorized.\n")
            return
        if not self.docker_ready():
            return
        from pulse.lab import cli

        try:
            try:
                self.ensure_lab()
            except httpx.ConnectError:
                with mock_mode():
                    if cli.main(["lab", "up", "--dashboard"]):
                        return
            self.stdout.write(
                "\nFollow the real evidence in the terminal or open http://localhost:3100/lab.\n"
            )
            from pulse.lab import evaluate

            previous_reports = evaluate.REPORTS
            folder = cli.LAB / "reports" / ("demo-" + str(time.time_ns()))
            folder.mkdir(parents=True, exist_ok=True)
            evaluate.REPORTS = folder
            try:
                result = cli.main(["lab", "run", scenario, "--approve"])
            finally:
                evaluate.REPORTS = previous_reports
            if not result:
                self.do_reports("")
                self.stdout.write(
                    "\nDemo complete. Type reports for evidence, /lab dashboard to explore, or /lab stop to preserve data and stop the lab.\n"
                )
        except (RuntimeError, httpx.HTTPError, OSError) as error:
            explanation = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            self.stdout.write(
                f"Demo could not finish: {explanation}. Check Docker or run pulse lab status. No automatic retry.\n"
            )

    def do_demo(self, arg):
        """/demo [--compose-file PATH] [--compose-project NAME] [--port PORT] [--model PROVIDER/MODEL] [--no-browser] — Scan and open selected project monitoring in read-only mode. /lab demo runs the isolated fault lab."""
        if self.project_path:
            from pulse.project.demo import run

            with redirect_stdout(self.stdout), redirect_stderr(self.stdout):
                run(self, arg)
        else:
            self.demonstrate("container-crash")

    def do_telemetry(self, arg):
        """Demonstrate inconclusive verification and restored telemetry."""
        self.demonstrate("telemetry-loss")

    def do_dashboard(self, arg):
        """/dashboard — Open the selected project's dashboard, or the incident lab if no project is selected."""
        if self.project_path:
            self.project_command("dashboard", arg)
            return
        self.lab_dashboard(arg)

    def lab_dashboard(self, arg):
        from pulse.lab.cli import LAB

        url = "http://localhost:3100/lab"
        webbrowser.open(url)
        self.stdout.write(
            f"Dashboard: {url}\nSign in with PULSE_ADMIN_TOKEN from {LAB / '.env'}. Keep that file private.\n"
        )

    def do_status(self, arg):
        """/status — Show selected project readiness and model; without a project, check the incident lab."""
        if self.project_path:
            return self.project_status()
        self.lab_status(arg)

    def lab_status(self, arg):
        from pulse.lab import cli

        if not (cli.LAB / ".env").exists():
            self.stdout.write("The demo has not started yet. Type demo.\n")
            return
        try:
            with cli.client() as http:
                result = cli.status(http)
            self.stdout.write(f"Lab Docker: {result['docker']}\n")
            for service in result["services"]:
                self.stdout.write(
                    f"  {service['name']}: {service['snapshot'].get('status', 'unknown')} / {service['snapshot'].get('health', 'unknown')}\n"
                )
        except (RuntimeError, httpx.HTTPError):
            self.stdout.write("Lab is stopped or unavailable. Type demo to start it.\n")

    def do_reports(self, arg):
        """Show the most recent measured evaluation, including failure reasons."""
        from pulse.lab.cli import LAB

        candidates = list((LAB / "reports").glob("verification-*/summary.json")) + list(
            (LAB / "reports").rglob("evaluation-summary.json")
        )
        if not candidates:
            self.stdout.write("No demo report yet. Type demo or telemetry.\n")
            return
        path = max(candidates, key=lambda item: item.stat().st_mtime)
        summary = json.loads(path.read_text())
        rows = summary.get("reports", summary.get("scenarios", []))
        for row in rows:
            raw = path.parent / (row["scenario"] + ".json")
            details = json.loads(raw.read_text()) if raw.exists() else row
            verification = details.get("verification", {})
            diagnosis = details.get("diagnosis", {})
            if diagnosis:
                self.stdout.write(
                    f"Diagnosis: {str(diagnosis.get('category', 'unknown')).replace('_', ' ')} · {diagnosis.get('successful_tool_calls', 0)} real tool results · {diagnosis.get('validated_citations', 0)} evidence citations\n"
                )
            action = details.get("remediation")
            if action:
                self.stdout.write(
                    f"Approved action: {action.get('kind', 'unknown')} · {action.get('status', 'unknown')}\n"
                )
            self.stdout.write(
                f"{row['scenario']}: {row['status']} — {verification.get('result', 'unavailable')}\n{verification.get('reason', details.get('error', 'No verdict recorded.'))}\n"
            )
            if details.get("inconclusive_verification"):
                self.stdout.write(
                    "Initial INCONCLUSIVE: " + details["inconclusive_verification"]["reason"] + "\n"
                )
        self.stdout.write(f"Full evidence: {path}\n")

    def do_quality(self, arg):
        """Review retained lab measurements offline; never start or change the lab."""
        from pulse.lab.cli import LAB
        from pulse.lab.quality import from_reports, markdown

        try:
            review = from_reports(LAB / "reports")
            self.stdout.write(markdown(review))
        except (RuntimeError, OSError) as error:
            self.stdout.write(
                f"Quality review unavailable: {type(error).__name__}. Inspect retained reports locally.\n"
            )

    def do_stop(self, arg):
        """/stop — Stop only this REPL's project monitoring. Without a project, confirm stopping the lab. Data is retained."""
        if self.project_path:
            return self.stop_watch()
        self.lab_stop(arg)

    def lab_stop(self, arg):
        from pulse.lab import cli

        if not (cli.LAB / ".env").exists():
            self.stdout.write("No lab to stop.\n")
            return
        if self.confirm("Stop the pulse-lab containers? Databases and reports will remain."):
            cli.main(["lab", "stop"])

    def do_lab(self, arg):
        """/lab demo|status|dashboard|stop — Explicitly target the incident lab, independent of project context."""
        operations = {
            "status": self.lab_status,
            "dashboard": self.lab_dashboard,
            "stop": self.lab_stop,
            "demo": lambda arg: self.demonstrate("container-crash"),
        }
        operation = operations.get(arg.strip().lower())
        if operation is None:
            self.emit("Use /lab demo, /lab status, /lab dashboard or /lab stop.")
        else:
            operation("")

    def do_exit(self, arg):
        """/exit — Stop project monitoring owned by this terminal and leave. Running incident lab resources remain available."""
        if self.watch_process is not None:
            self.stop_watch()
        self.stdout.write(
            "Goodbye. Running demos remain available; use pulse lab stop to stop them.\n"
        )
        return True

    do_quit = do_exit
    do_EOF = do_exit
    do_eof = do_exit


def terminal_completion(shell):
    """Python 3.12 cmd.Cmd assumes GNU readline; uv/macOS may supply libedit."""
    try:
        import readline
    except ImportError:
        return lambda: None
    readline.set_auto_history(False)  # Never retain questions or accidental credentials.
    previous = readline.get_completer()
    readline.set_completer(shell.complete)
    readline.parse_and_bind(
        "bind ^I rl_complete" if "libedit" in (readline.__doc__ or "") else "tab: complete"
    )
    shell.completekey = None  # The completion binding above also works on libedit.
    return lambda: readline.set_completer(previous)


def run(repo=None):
    shell = PulseRepl(stdin=sys.stdin, stdout=sys.stdout)
    shell.do_open(shlex.quote(repo or os.getcwd()))
    shell.use_rawinput = sys.stdin.isatty() and sys.stdout.isatty()
    restore_completion = terminal_completion(shell) if shell.use_rawinput else lambda: None
    try:
        while True:
            try:
                shell.cmdloop()
                break
            except KeyboardInterrupt:
                shell.emit(
                    "\nCancelled input. Monitoring continues; /stop stops it and /exit leaves."
                )
                shell.intro = ""
    finally:
        if shell.watch_process is not None:
            shell.stop_watch()
        if shell.watch_stream is not None:
            shell.watch_stream.close()
        restore_completion()
    return 0
