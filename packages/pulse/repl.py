"""Interactive, consent-based real demonstrations of the fixed incident lab."""

import cmd
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager

import httpx


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


class PulseRepl(cmd.Cmd):
    prompt = "pulse › "
    intro = "\nPulse — evidence before action.\nType demo for a guided real lab run, help for commands, or exit.\n"
    MENU = "open PATH      Select your repository\nscan           Inventory the selected repository\ninit           Prepare its opt-in monitoring profile\nwatch          Keep its local dashboard and monitoring alive\nincidents      Show the selected project's incidents\nreport         Read its latest retained incident report\napprove ID     Review and approve one proposed action\nreject ID      Handle it yourself; reject the proposal\n1 / demo       Guided crash → investigation → approved recovery\n2 / telemetry  Missing evidence → inconclusive → restored recovery\n3 / dashboard  Open the local incident workspace\n4 / status     Check the lab\n5 / reports    Show the latest measured results\n6 / stop       Stop the lab; keep its data\n7 / quality    Review retained results and improvement steps\n0 / exit       Leave the REPL"

    def __init__(self, *args, repo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_path = None
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
        command, separator, arguments = stripped.partition(" ")
        return command.lower() + separator + arguments

    def do_open(self, arg):
        """Select a repository without executing it or starting monitoring."""
        from pulse.project.scan import repository

        try:
            parts = shlex.split(arg)
            if len(parts) != 1:
                raise RuntimeError("Use open PATH, quoting paths that contain spaces")
            self.project_path = str(repository(parts[0]))
            self.stdout.write(
                f"Selected repository: {self.project_path}\nType scan, init, then watch. No application command was executed.\n"
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
        main([command, *arguments, *path])

    def do_scan(self, arg):
        """Inventory selected repository metadata without executing its scripts."""
        self.project_command("scan", arg)

    def do_init(self, arg):
        """Prepare a private project profile and an enrollment override to review."""
        self.project_command("init", arg)

    def do_watch(self, arg):
        """Run this project's monitoring and dashboard until Ctrl+C."""
        self.project_command("watch", arg)

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
        self.stdout.write("Unknown command. Type help to see the menu.\n")

    def do_help(self, arg):
        """Show the menu."""
        self.stdout.write(self.MENU + "\n")

    def confirm(self, message):
        self.stdout.write(message + "\nContinue? [y/N] ")
        self.stdout.flush()
        return self.stdin.readline().strip().lower() in {"y", "yes"}

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
                    "\nDemo complete. Type reports for evidence, dashboard to explore, or stop to preserve data and stop the lab.\n"
                )
        except (RuntimeError, httpx.HTTPError, OSError) as error:
            explanation = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            self.stdout.write(
                f"Demo could not finish: {explanation}. Check Docker or run pulse lab status. No automatic retry.\n"
            )

    def do_demo(self, arg):
        """Run a real scoped crash-and-recovery demonstration."""
        self.demonstrate("container-crash")

    def do_telemetry(self, arg):
        """Demonstrate inconclusive verification and restored telemetry."""
        self.demonstrate("telemetry-loss")

    def do_dashboard(self, arg):
        """Open the lab dashboard."""
        if self.project_path:
            self.project_command("dashboard", arg)
            return
        from pulse.lab.cli import LAB

        url = "http://localhost:3100/lab"
        webbrowser.open(url)
        self.stdout.write(
            f"Dashboard: {url}\nSign in with PULSE_ADMIN_TOKEN from {LAB / '.env'}. Keep that file private.\n"
        )

    def do_status(self, arg):
        """Check the lab without creating credentials."""
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
        """Stop only the lab; retain volumes and reports."""
        from pulse.lab import cli

        if not (cli.LAB / ".env").exists():
            self.stdout.write("No lab to stop.\n")
            return
        if self.confirm("Stop the pulse-lab containers? Databases and reports will remain."):
            cli.main(["lab", "stop"])

    def do_exit(self, arg):
        """Leave the REPL; running lab resources remain available."""
        self.stdout.write(
            "Goodbye. Running demos remain available; use pulse lab stop to stop them.\n"
        )
        return True

    do_quit = do_exit
    do_EOF = do_exit
    do_eof = do_exit


def run(repo=None):
    shell = PulseRepl(stdin=sys.stdin, stdout=sys.stdout)
    if repo:
        shell.do_open(shlex.quote(repo))
    shell.use_rawinput = False
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        shell.stdout.write(
            "\nInterrupted. No action is automatically retried. The lab stays available; pulse lab stop preserves its data.\n"
        )
    return 0
