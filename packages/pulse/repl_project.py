"""Scoped project commands and processes owned by one interactive terminal."""

import argparse
import cmd
import json
import os
import shlex
import subprocess
import sys
import tempfile
from contextlib import closing
from typing import BinaryIO

from pulse.project import session, state
from pulse.project.cli import identifier, safe_text


class ProjectCommands(cmd.Cmd):
    project_path: str | None
    service_id: str | None
    watch_process: subprocess.Popen | None
    watch_log: str | None
    watch_stream: BinaryIO | None
    watch_offset: int

    def confirm(self, message):
        raise NotImplementedError

    def emit(self, value):
        self.stdout.write(safe_text(str(value)) + "\n")

    def request(self, method, path, **kwargs):
        if not self.project_path:
            raise RuntimeError("Select a repository with /open PATH first")
        # The identity handshake precedes attaching the project's credentials.
        with closing(session.client(self.project_path)) as http:
            return http.request(method, path, **kwargs).raise_for_status().json()

    def do_context(self, arg):
        """/context — Show repository and service scope. No repository files go to a model."""
        if not self.project_path:
            self.emit("No repository selected. Use /open PATH, then /scan and /init.")
            return
        self.emit(f"Repository: {self.project_path}")
        self.emit(f"Service: {self.service_id or 'not selected; use /services then /use NAME'}")
        self.emit(
            "Model tools read monitored runtime evidence. Recovery requires an exact approval."
        )

    def do_model(self, arg):
        """/model — Show reasoning mode and budgets. Choose a model with /watch --model PROVIDER/MODEL."""
        if arg.strip():
            self.emit("Use /model to inspect; /stop then /watch --model PROVIDER/MODEL to change.")
            return
        data = self.request("GET", "/settings")
        model = data.get("model") or "deterministic evidence (no live LLM)"
        self.emit(f"Reasoning: {model}")
        if model == "mock/evidence":
            self.emit("Mock reasoning; this is not a live-model evaluation.")
        self.emit(json.dumps(data.get("runtime", {}), indent=2))
        self.emit("Provider credentials are read from your environment when monitoring starts.")

    def do_services(self, arg):
        """/services — List project services, evidence availability and recovery permissions."""
        rows = self.request("GET", "/services")
        if not rows:
            self.emit("No services discovered yet. Review Compose enrollment and /status.")
        for row in rows:
            snapshot = row.get("snapshot") or {}
            self.emit(
                f"{row['id']} · {row['name']} · monitored={row['monitored']} · "
                f"recovery={row['remediation_allowed']} · Docker={snapshot.get('status', 'unknown')} · "
                f"metrics={'received' if row.get('metrics') is not None else 'unavailable'}"
            )
        self.emit(
            "Docker status alone does not prove recovery. /inspect ID shows verification evidence."
        )

    def do_use(self, arg):
        """/use NAME|UUID — Select one monitored service for /ask and /logs; /use clears it."""
        parts = shlex.split(arg)
        if not parts:
            self.service_id = None
            self.emit("Service context cleared.")
            return
        if len(parts) != 1:
            raise RuntimeError("Use /use NAME or the exact service UUID")
        rows = self.request("GET", "/services")
        matches = [r for r in rows if r["id"] == parts[0] or r["name"] == parts[0]]
        if len(matches) != 1 or not matches[0]["monitored"]:
            raise RuntimeError("Choose exactly one monitored service from /services")
        self.service_id = identifier(matches[0]["id"])
        self.emit(f"Service context: {matches[0]['name']} · {self.service_id}")

    def do_ask(self, arg):
        """/ask QUESTION — Request a bounded read-only investigation of the selected service. Inspect its returned incident ID for the answer. This never approves an action."""
        if not self.service_id:
            raise RuntimeError("Select a monitored service with /use NAME first")
        question = arg.strip()
        if not 1 <= len(question) <= 2000:
            raise RuntimeError("Use /ask with a question of 1–2000 characters")
        result = self.request(
            "POST", "/chat", json={"service_id": self.service_id, "message": question}
        )
        self.emit(f"Read-only investigation queued: {result['incident_id']}")
        self.emit(
            f"Use /inspect {result['incident_id']} or /timeline {result['incident_id']} for the answer."
        )

    def do_logs(self, arg):
        """/logs [LIMIT] — Read 1–300 log lines from the selected monitored service (default 50)."""
        if not self.service_id:
            raise RuntimeError("Select a monitored service with /use NAME first")
        limit = int(arg.strip() or "50")
        if not 1 <= limit <= 300:
            raise RuntimeError("Log limit must be between 1 and 300")
        self.emit(
            json.dumps(
                self.request("GET", f"/services/{self.service_id}/logs", params={"limit": limit}),
                indent=2,
            )
        )

    def do_inspect(self, arg):
        """/inspect INCIDENT_UUID — Show diagnosis, tools, proposed actions and the verification verdict with supporting evidence."""
        self.emit(
            json.dumps(self.request("GET", f"/incidents/{identifier(arg.strip())}"), indent=2)
        )

    def do_timeline(self, arg):
        """/timeline INCIDENT_UUID — Read the persisted incident event history."""
        self.emit(
            json.dumps(
                self.request("GET", f"/incidents/{identifier(arg.strip())}/timeline"), indent=2
            )
        )

    def do_investigate(self, arg):
        """/investigate INCIDENT_UUID — Rerun a read-only investigation. Existing pending proposals are invalidated; new proposals still need approval."""
        iid = identifier(arg.strip())
        if self.confirm(
            "Reinvestigate this incident? Existing pending proposals will be invalidated; no recovery is approved."
        ):
            self.request("POST", f"/incidents/{iid}/investigate", json={})
            self.emit(f"Read-only investigation queued: {iid}. Use /inspect or /timeline.")

    def project_status(self):
        self.do_context("")
        data = self.request("GET", "/health")
        self.emit(
            f"Project API: {data['status']} · telemetry gateway: {data['docker']} · last poll: {data['last_poll']}"
        )
        self.emit(
            "API availability does not prove application health. Missing evidence remains unavailable."
        )
        self.do_model("")

    def start_watch(self, arg):
        parser = argparse.ArgumentParser(
            prog="/watch",
            description="Start monitoring in this REPL; /stop or /exit stops only its owned Pulse processes.",
        )
        parser.add_argument("--port", type=int, default=8765)
        parser.add_argument("--model")
        parser.add_argument("--no-browser", action="store_true")
        args = parser.parse_args(shlex.split(arg))
        if not self.project_path:
            raise RuntimeError("Select a repository with /open PATH first")
        if self.watch_process is not None and self.watch_process.poll() is None:
            raise RuntimeError("This REPL already owns monitoring. Use /status or /stop first")
        state.load(self.project_path)  # Validate scope before launching; never enroll the app here.
        folder = state.location(self.project_path)
        session.origin(args.port)
        session.origin(args.port + 1)
        if self.watch_stream is not None:
            self.watch_stream.close()
            self.watch_stream = None
        with tempfile.NamedTemporaryFile(
            mode="w", prefix="repl-watch-", suffix=".log", dir=folder, delete=False
        ) as log:
            self.watch_log = log.name
            self.watch_offset = 0
            self.watch_stream = os.fdopen(
                os.open(log.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb"
            )
            command = [
                sys.executable,
                "-m",
                "pulse.project.repl_worker",
                "watch",
                self.project_path,
                "--port",
                str(args.port),
            ]
            if args.model is not None:
                command += ["--model", args.model]
            if args.no_browser:
                command += ["--no-browser"]
            try:
                self.watch_process = subprocess.Popen(
                    command,
                    cwd=folder,
                    env={
                        **os.environ,
                        "PULSE_HOME": str(state.home().resolve()),
                        "PULSE_SESSION_OWNER": str(os.getpid()),
                        "PYTHONUNBUFFERED": "1",
                    },
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            except OSError:
                self.watch_stream.close()
                self.watch_stream = None
                raise
        self.emit(
            "Monitoring is starting in the background. Keep this REPL open; use /status to check readiness."
        )
        self.emit(f"Dashboard when ready: {session.origin(args.port)}")
        self.emit(
            f"Sign in using admin_token from {folder / 'credentials.json'}; keep that file private."
        )
        self.emit(
            "Use /services, /incidents and /ask while monitoring runs. Updates appear after each command."
        )

    def watch_updates(self):
        if not self.watch_log:
            return
        # Read our already-opened private file, without following a replaced path.
        if self.watch_stream is None:
            return
        self.watch_stream.seek(self.watch_offset)
        data = self.watch_stream.read(65536)
        self.watch_offset = self.watch_stream.tell()
        if data:
            self.emit(data.decode("utf-8", errors="replace").rstrip())
        if self.watch_process is not None and self.watch_process.poll() is not None:
            self.emit(
                f"Monitoring stopped (exit {self.watch_process.returncode}). Data and reports are retained; /watch starts another session."
            )
            self.watch_process = None
            self.watch_stream.close()
            self.watch_stream = None

    def stop_watch(self):
        if self.watch_process is None:
            self.emit(
                "This REPL owns no monitoring process. An external pulse watch session was not stopped."
            )
            return
        session.stop(self.watch_process)
        self.watch_updates()
        self.watch_process = None
        self.emit("Stopped this REPL's Pulse session. Your app, databases and reports remain.")
