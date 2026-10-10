"""One-command read-only onboarding of the selected repository's existing runtime."""

import argparse
import math
import shlex
import time
from pathlib import Path

import docker
import httpx

from pulse.project import state
from pulse.project.scan import compose_services, scan


def run(shell, arg):
    parser = argparse.ArgumentParser(
        prog="/demo",
        description="Scan this repository, prepare a private profile and open read-only monitoring. No app scripts, builds, pulls, label changes or recovery actions.",
    )
    parser.add_argument("--compose-file")
    parser.add_argument("--compose-project")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(shlex.split(arg))
    root = shell.project_path
    inventory = scan(root)
    shell.emit(
        f"[1/4] Repository scanned: {root}\nLanguages: {', '.join(inventory['languages']) or 'not detected'}\nFrameworks: {', '.join(inventory['frameworks']) or 'not detected'}"
    )
    for warning in inventory["warnings"]:
        shell.emit(f"Inventory limitation: {warning}")
    candidate = args.compose_file or inventory["compose_file"]
    if not candidate and not (state.location(root) / "profile.json").exists():
        raise RuntimeError(
            "Inventory complete. Live project demo requires an existing local Docker Compose app. Use /demo --compose-file PATH, or /lab demo for an isolated sample. No repository scripts were executed."
        )
    if not shell.docker_ready():
        return
    project = args.compose_project
    if not project and not (state.location(root) / "profile.json").exists():
        services, _ = compose_services(Path(root) / candidate, Path(root))
        engine = docker.from_env(timeout=5)
        try:
            matches = {
                c.labels.get("com.docker.compose.project")
                for c in engine.containers.list(
                    all=True, filters={"label": f"com.docker.compose.project.working_dir={root}"}
                )
                if c.labels.get("com.docker.compose.project.working_dir") == root
                and c.labels.get("com.docker.compose.service") in services
                and not c.labels.get("pulse.lab")
            } - {None, ""}
        finally:
            engine.close()
        if len(matches) > 1:
            raise RuntimeError(
                "Multiple Compose projects use this repository. Choose /demo --compose-project NAME; no runtime was changed."
            )
        project = next(iter(matches), None)
    if (state.location(root) / "profile.json").exists():
        profile = state.load(root)
        if (
            args.compose_file
            and args.compose_file != profile["compose_file"]
            or args.compose_project
            and args.compose_project != profile["compose_project"]
        ):
            raise RuntimeError(
                "A profile already exists with a different Compose scope. Review it locally; existing credentials and history were preserved."
            )
    else:
        profile = state.initialize(root, compose_file=args.compose_file, project=project)
    shell.emit(
        f"[2/4] Private profile ready: {state.location(root) / 'profile.json'}\nCompose project: {profile['compose_project']} · services: {', '.join(profile['services'])}\nRead-only demo: application containers and labels stay unchanged. Recovery is disabled."
    )
    active = None
    try:
        active = shell.request("GET", "/project")
    except (RuntimeError, httpx.ConnectError, httpx.ConnectTimeout):
        pass
    if active is not None and not active.get("read_only"):
        raise RuntimeError(
            "A normal monitoring session is already active. Stop it in its owning terminal before /demo; it was not changed."
        )
    if active is None:
        flags = ["--read-only", "--port", str(args.port)]
        if args.no_browser:
            flags.append("--no-browser")
        if args.model is not None:
            flags += ["--model", args.model]
        shell.start_watch(shlex.join(flags))
    else:
        shell.emit("Reusing the existing read-only session; no duplicate monitor was started.")
    shell.emit("[3/4] Waiting for the project API and telemetry gateway…")
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if shell.watch_process is not None and shell.watch_process.poll() is not None:
            shell.watch_updates()
            raise RuntimeError(
                "Demo startup failed. Inspect the private session logs; the app was not changed."
            )
        try:
            context = shell.request("GET", "/project")
            health = shell.request("GET", "/health")
            settings = shell.request("GET", "/settings")
            if not context.get("read_only"):
                raise RuntimeError(
                    "The active session is not a read-only demo; no demo-ready verdict was issued"
                )
            at = health.get("last_poll")
            max_age = settings.get("runtime", {}).get("telemetry_max_age_seconds", 15)
            if (
                health.get("docker") == "connected"
                and isinstance(at, (int, float))
                and not isinstance(at, bool)
                and math.isfinite(at)
                and 0 <= time.time() - at <= max_age
            ):
                break
        except httpx.HTTPError:
            pass
        except RuntimeError as error:
            if "read-only" in str(error):
                raise
        time.sleep(0.2)
    else:
        if active is None:
            shell.stop_watch()
        raise RuntimeError(
            "Demo readiness timed out. Required telemetry was unavailable; your application and retained data were preserved."
        )
    shell.emit(
        "[4/4] Local dashboard and monitoring ready. API readiness alone does not prove application health."
    )
    shell.do_services("")
    rows = shell.request("GET", "/services")
    monitored = [row for row in rows if row["monitored"]]
    if len(monitored) == 1:
        shell.do_use(monitored[0]["id"])
        shell.emit("Try /ask What evidence explains this service's current behavior?")
    elif monitored:
        shell.emit("Choose a service with /use NAME, then /ask QUESTION.")
    else:
        shell.emit(
            "No scoped containers are available yet. Start your Compose app yourself, then use /services. No health verdict is inferred from missing telemetry."
        )
    incidents = shell.request("GET", "/incidents")
    shell.emit(
        f"Recorded incidents: {len(incidents)}. /incidents lists them; /inspect ID shows the evidence and verdict."
    )
    shell.emit("Keep this REPL open. /stop ends owned monitoring; your app and reports remain.")
    if not args.no_browser:
        shell.project_command("dashboard")
