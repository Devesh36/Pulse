"""Own only Pulse's local processes; never start, stop or execute the selected app."""

import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager

import docker
import httpx
from docker.errors import DockerException

from pulse.core.redaction import redact
from pulse.project.state import atomic_json, credentials, load, location


@contextmanager
def lock(folder):
    path = folder / "session.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(descriptor)
        raise RuntimeError(
            "Another Pulse watch session owns this project; no duplicate monitor was started"
        ) from error
    try:
        yield
    finally:
        os.close(descriptor)


def origin(port):
    if not isinstance(port, int) or not 1024 <= port <= 65534:
        raise RuntimeError("Choose a local port between 1024 and 65534")
    return f"http://127.0.0.1:{port}"


def available(port):
    with socket.socket() as channel:
        channel.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            channel.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(
                f"Local port {port} is in use. Choose another --port; existing services were not stopped."
            ) from error


def client(path):
    profile = load(path)
    folder = location(path)
    try:
        active = json.loads((folder / "active.json").read_text())
        base = origin(active["port"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            "No active project session. Keep pulse watch running in another terminal."
        ) from error
    http = httpx.Client(base_url=base + "/api/v1", trust_env=False, timeout=10)
    try:
        response = http.get("/project/identity")
        response.raise_for_status()
        if response.json().get("project_id") != profile["inventory"]["id"]:
            raise RuntimeError(
                "The local API belongs to another project; no project credentials were sent"
            )
        http.headers["Authorization"] = f"Bearer {credentials(path)['admin_token']}"
    except Exception:
        http.close()
        raise
    return http


def stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def snapshot(http, folder, incident):
    iid = incident["id"]
    detail = http.get(f"/incidents/{iid}").raise_for_status().json()
    timeline = http.get(f"/incidents/{iid}/timeline").raise_for_status().json()
    report = {
        **detail,
        "timeline": timeline,
        "recorded_at": time.time(),
        "source": "project-runtime",
    }
    atomic_json(folder / "reports" / f"incident-{iid}.json", redact(report))
    return report


def terminal(value):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", redact(value))


def environment(profile, folder, port, model):
    tokens = credentials(profile["root"])
    # Never source the target repository's .env or execute its package scripts.
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("PULSE_")}
    profile_context = {
        "inventory": profile["inventory"],
        "root": profile["root"],
        "compose_project": profile["compose_project"],
        "services": profile["services"],
        "override_file": str(folder / "monitor.compose.json"),
        "prometheus_configured": bool(profile.get("prometheus_url")),
    }
    api = {
        **inherited,
        "PULSE_DATABASE_URL": "sqlite:///" + str(folder / "pulse.db"),
        "PULSE_ADMIN_TOKEN": tokens["admin_token"],
        "PULSE_ADAPTER_TOKEN": tokens["adapter_token"],
        "PULSE_ADAPTER_URL": origin(port + 1),
        "PULSE_WEB_ORIGIN": origin(port),
        "PULSE_PROMETHEUS_URL": profile.get("prometheus_url", ""),
        "PULSE_PROBE_URLS": json.dumps(profile.get("health_urls", {})),
        "PULSE_PROBE_ALLOWED_HOSTS": '["127.0.0.1", "localhost", "::1"]',
        "PULSE_PROJECT_CONTEXT": json.dumps(profile_context),
        "PULSE_PROJECT_SESSION": "true",
        "PULSE_LLM_MODEL": model,
        "PULSE_LLM_API_KEY": os.getenv("PULSE_LLM_API_KEY", ""),
        "PULSE_LLM_API_BASE": os.getenv("PULSE_LLM_API_BASE", ""),
        "PULSE_LAB_ENABLED": "false",
        "PULSE_SESSION_OWNER": str(os.getpid()),
    }
    gateway = {
        **inherited,
        "PULSE_ADAPTER_TOKEN": tokens["adapter_token"],
        "PULSE_GATEWAY_JOURNAL": str(folder / "gateway.db"),
        "PULSE_RESOURCE_PROJECT": profile["compose_project"],
        "PULSE_RESOURCE_ROOT": profile["root"],
        "PULSE_RESOURCE_SERVICES": json.dumps(profile["services"]),
        "PULSE_LAB_ENABLED": "false",
        "PULSE_SESSION_OWNER": str(os.getpid()),
    }
    return api, gateway


def watch(path, port=8765, browser=True, model=None):
    profile = load(path)
    folder = location(path)
    model = model if model is not None else os.getenv("PULSE_LLM_MODEL", "")
    if model == "mock/evidence":
        raise RuntimeError(
            "Mock reasoning is restricted to the incident lab. Omit --model for deterministic evidence, or configure a real provider."
        )
    origin(port)
    with lock(folder):
        available(port)
        available(port + 1)
        engine = None
        try:
            engine = docker.from_env(timeout=5)
            engine.ping()
        except DockerException as error:
            raise RuntimeError(
                "Docker is unavailable. Start Docker and the selected app with Compose, then retry."
            ) from error
        finally:
            if engine is not None:
                engine.close()
        for name in ("pulse.db", "gateway.db", "api.log", "gateway.log", "active.json"):
            if (folder / name).is_symlink():
                raise RuntimeError("Project state files cannot use symlinks")
        api_env, gateway_env = environment(profile, folder, port, model)
        children = []
        logs = []
        http = None
        try:

            def exit_session(signum, frame):
                raise KeyboardInterrupt

            previous_signals = {
                sig: signal.signal(sig, exit_session)
                for sig in (signal.SIGTERM, *([signal.SIGHUP] if hasattr(signal, "SIGHUP") else []))
            }
            for name, args, env in [
                (
                    "gateway",
                    [
                        "-m",
                        "uvicorn",
                        "apps.api.gateway:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port + 1),
                        "--no-access-log",
                        "--log-level",
                        "warning",
                    ],
                    gateway_env,
                ),
                ("api", ["-m", "pulse.project.server", "--port", str(port)], api_env),
            ]:
                logfile = folder / (name + ".log")
                descriptor = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                stream = os.fdopen(descriptor, "a")
                logs.append(stream)
                children.append(
                    subprocess.Popen(
                        [sys.executable, *args],
                        cwd=folder,
                        env=env,
                        stdout=stream,
                        stderr=stream,
                        start_new_session=True,
                    )
                )
            print(
                "Starting Pulse's scoped gateway and local dashboard. Your application is not started or changed.",
                flush=True,
            )
            atomic_json(folder / "active.json", {"port": port, "owner_pid": os.getpid()})
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError(
                        f"A Pulse service stopped during startup. Inspect the private logs in {folder}; no app change was made."
                    )
                try:
                    http = client(path)
                    break
                except (httpx.HTTPError, RuntimeError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Pulse startup timed out; own processes will be stopped")
            print(
                f"Project dashboard: {origin(port)}\nSign in using admin_token from {folder / 'credentials.json'}. Keep that file private.",
                flush=True,
            )
            print(
                f"Reasoning: {model or 'deterministic evidence (no live LLM)'}\nKeep this terminal open. Ctrl+C stops only Pulse; project data and reports remain.",
                flush=True,
            )
            if browser:
                webbrowser.open(origin(port))
            seen = {}
            last_docker = None
            while True:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError(
                        "A Pulse service stopped; monitoring is unavailable. Own session services will be stopped."
                    )
                try:
                    health = http.get("/health").raise_for_status().json()
                    if health["docker"] != last_docker:
                        print(
                            f"Telemetry gateway: {health['docker']}. Missing telemetry is not a healthy observation.",
                            flush=True,
                        )
                        last_docker = health["docker"]
                    incidents = http.get("/incidents").raise_for_status().json()
                    for incident in incidents:
                        fingerprint = (
                            incident["state"],
                            incident["updated_at"],
                            json.dumps(incident.get("verification"), sort_keys=True),
                        )
                        if seen.get(incident["id"]) == fingerprint:
                            continue
                        report = snapshot(http, folder, incident)
                        seen[incident["id"]] = fingerprint
                        print(
                            terminal(
                                f"[{incident['state']}] {incident['title']} · incident {incident['id']}"
                            ),
                            flush=True,
                        )
                        if report.get("diagnosis"):
                            print(terminal(report["diagnosis"].get("summary", "")), flush=True)
                        for action in report.get("actions", []):
                            if action["status"] == "proposed":
                                print(
                                    f"Pulse proposes {action['kind']}. Review with: pulse approve {action['id']} --repo {shlex.quote(profile['root'])}\nOr handle it yourself: pulse reject {action['id']} --repo {shlex.quote(profile['root'])}",
                                    flush=True,
                                )
                        if report.get("verification"):
                            print(
                                terminal(
                                    f"Verification: {report['verification'].get('result') or 'collecting evidence'} · {report['verification'].get('reason', '')}"
                                ),
                                flush=True,
                            )
                except httpx.HTTPError:
                    print(
                        "Project API unavailable; no current health verdict is inferred. Retained reports remain available.",
                        flush=True,
                    )
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nStopping Pulse's monitoring session.", flush=True)
        finally:
            for sig, handler in locals().get("previous_signals", {}).items():
                signal.signal(sig, handler)
            if http:
                try:
                    for incident in http.get("/incidents").raise_for_status().json():
                        snapshot(http, folder, incident)
                except (httpx.HTTPError, OSError, ValueError):
                    print(
                        "Latest report snapshot unavailable; previously saved evidence remains.",
                        flush=True,
                    )
                http.close()
            for child in reversed(children):
                stop(child)
            for stream in logs:
                stream.close()
            (folder / "active.json").unlink(missing_ok=True)
            print(
                f"Pulse stopped. App containers untouched; reports and database preserved in {folder}.",
                flush=True,
            )
