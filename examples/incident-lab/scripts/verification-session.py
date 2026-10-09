"""Small test session: reuse development PostgreSQL; never change its containers."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pulse.lab.cli import LAB, ROOT, client, compose, credentials, ready
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

STATE = ROOT.parent / "pulse-verification-session"


def state():
    STATE.mkdir(exist_ok=True)
    return STATE


def stage_source():
    source = state() / "source"
    for name in ("packages", "apps/api"):
        shutil.copytree(
            ROOT / name,
            source / name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for item in source.rglob("*"):
        item.chmod(0o755 if item.is_dir() else 0o644)
    return source


def docker_inspect(name):
    return json.loads(subprocess.check_output(["docker", "inspect", name]))[0]


def native_env():
    values = credentials()
    development = dotenv_values(ROOT / ".env")
    database = make_url(development["PULSE_DATABASE_URL"]).set(database="pulse_verification_lab")
    env = os.environ.copy()
    ips = {}
    for name in ("gateway", "demo-api", "demo-worker"):
        info = docker_inspect(f"pulse-lab-{name}-1")
        assert info["Config"]["Labels"]["com.docker.compose.project"] == "pulse-lab"
        ips[name] = info["NetworkSettings"]["Networks"]["pulse-lab_control"]["IPAddress"]
    env.update(
        PULSE_DATABASE_URL=database.render_as_string(hide_password=False),
        PULSE_ADMIN_TOKEN=values["PULSE_ADMIN_TOKEN"],
        PULSE_ADAPTER_TOKEN=values["PULSE_ADAPTER_TOKEN"],
        PULSE_LAB_TEST_TOKEN=values["PULSE_LAB_TEST_TOKEN"],
        PULSE_LAB_ENABLED="true",
        PULSE_LAB_PROJECT="pulse-lab",
        PULSE_ADAPTER_URL=f"http://{ips['gateway']}:8001",
        PULSE_PROMETHEUS_URL="http://127.0.0.1:8109",
        PULSE_WEB_ORIGIN="http://localhost:3100",
        PULSE_LLM_MODEL="mock/evidence",
        PULSE_LLM_API_KEY="",
        PULSE_LLM_API_BASE="",
        PULSE_PROBE_URLS=json.dumps(
            {name: f"http://{ips[name]}:8080/health" for name in ("demo-api", "demo-worker")}
        ),
        PULSE_PROBE_ALLOWED_HOSTS=json.dumps([ips["demo-api"], ips["demo-worker"]]),
        NO_PROXY=",".join(["localhost", "127.0.0.1", *ips.values()]),
        no_proxy=",".join(["localhost", "127.0.0.1", *ips.values()]),
    )
    return env


def stop_api():
    path = state() / "api.pid"
    if not path.exists():
        return
    pid = int(path.read_text())
    proc = Path(f"/proc/{pid}/cmdline")
    if proc.exists():
        command = proc.read_bytes().replace(b"\0", b" ")
        if b"apps.api.serve" in command and b"8100" in command:
            os.kill(pid, signal.SIGTERM)
            for _ in range(60):
                if not proc.exists() or Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z":
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, signal.SIGKILL)
        elif command.strip():
            raise RuntimeError("Recorded PID belongs to another process; refusing termination")
    path.unlink(missing_ok=True)


def start_api():
    with (state() / "api.log").open("ab") as logs:
        process = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "apps.api.serve",
                "--host",
                "127.0.0.1",
                "--port",
                "8100",
            ],
            cwd=ROOT,
            env=native_env(),
            stdout=logs,
            stderr=logs,
            start_new_session=True,
        )
    (state() / "api.pid").write_text(str(process.pid))
    with client() as http:
        ready(http)
    print("Scoped native lab API ready; development containers unchanged.")


def up():
    if not (LAB / ".env").exists():
        raise RuntimeError(
            "Existing lab credentials required; this focused session does not create or change credentials"
        )
    with httpx.Client(trust_env=False, timeout=1) as http:
        try:
            http.get("http://127.0.0.1:8100/api/v1/health")
        except httpx.RequestError:
            pass
        else:
            raise RuntimeError("Port 8100 is already occupied; refusing to replace an existing API")
    # Record exactly the unrelated runtime identities, not environments/secrets.
    names = subprocess.check_output(
        ["docker", "ps", "--format", "{{.Names}}"], text=True
    ).splitlines()
    untouched = {}
    for name in names:
        if not name.startswith("pulse-lab-"):
            info = docker_inspect(name)
            untouched[name] = {
                "id": info["Id"],
                "started_at": info["State"]["StartedAt"],
                "restart_count": info["RestartCount"],
            }
    (state() / "untouched.json").write_text(json.dumps(untouched))
    override = state() / "compose.json"
    source = stage_source()
    override.write_text(
        json.dumps(
            {
                "services": {
                    "gateway": {
                        "image": "pulse-gateway",
                        "volumes": [
                            f"{source}/packages:/app/packages:ro",
                            f"{source}/apps/api:/app/apps/api:ro",
                        ],
                    }
                }
            }
        )
    )
    compose("build", "demo-api")
    compose(
        "-f",
        str(override),
        "up",
        "--no-build",
        "--no-deps",
        "-d",
        "gateway",
        "prometheus",
        "demo-api",
        "demo-worker",
    )
    values = dotenv_values(ROOT / ".env")
    engine = create_engine(values["PULSE_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as db:
            if not db.scalar(
                text("SELECT 1 FROM pg_database WHERE datname='pulse_verification_lab'")
            ):
                db.execute(text("CREATE DATABASE pulse_verification_lab"))
    finally:
        engine.dispose()
    result = subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=ROOT,
        env=native_env(),
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Isolated lab migration failed; inspect the local session logs without exposing credentials"
        )
    start_api()


def check_untouched():
    for name, previous in json.loads((state() / "untouched.json").read_text()).items():
        info = docker_inspect(name)
        assert {
            "id": info["Id"],
            "started_at": info["State"]["StartedAt"],
            "restart_count": info["RestartCount"],
        } == previous, name
    print(
        "All unrelated development containers retain their identities, start times and restart counts."
    )


def main():
    command = sys.argv[1]
    if command == "up":
        up()
    elif command == "restart-api":
        stop_api()
        start_api()
    elif command == "check":
        check_untouched()
    elif command == "down":
        stop_api()
        compose("down", "--remove-orphans")
        check_untouched()
        print(
            "Session stopped. Databases, reports, credentials, and named telemetry/audit volumes preserved."
        )
    else:
        raise RuntimeError("Use up, restart-api, check, or down")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, OSError) as error:
        print(f"Verification session failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from None
