"""Interactive, consent-based real demonstrations of the fixed incident lab."""

import cmd
import json
import os
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
    MENU = "1 / demo       Guided crash → investigation → approved recovery\n2 / telemetry  Missing evidence → inconclusive → restored recovery\n3 / dashboard  Open the local incident workspace\n4 / status     Check the lab\n5 / reports    Show the latest measured results\n6 / stop       Stop the lab; keep its data\n0 / exit       Leave the REPL"

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
            "0": "exit",
        }
        return aliases.get(line.strip(), line.lower())

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

        candidates = (
            list((LAB / "reports").glob("verification-*/summary.json"))
            + list((LAB / "reports").glob("evaluation-summary.json"))
            + list((LAB / "reports").glob("demo-*/evaluation-summary.json"))
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


def run():
    shell = PulseRepl(stdin=sys.stdin, stdout=sys.stdout)
    shell.use_rawinput = False
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        shell.stdout.write(
            "\nInterrupted. No action is automatically retried. The lab stays available; pulse lab stop preserves its data.\n"
        )
    return 0
