"""Opt-in real REPL acceptance check; one existing lab fixture, no live model calls.

Run: uv run python examples/incident-lab/scripts/repl-session.py
Requires Docker and cached pulse-lab-demo:latest. Reports/databases are retained.
PULSE_TEST_CLI optionally selects an installed pulse executable to check its wheel.
"""

import json
import os
import secrets
import shlex
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

import docker
import httpx
from pulse.core.redaction import redact
from pulse.project.state import initialize, location

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "examples/incident-lab/repository-demo"
OUTPUT = ROOT.parent / "pulse-repl-session" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def wait(operation, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if result := operation():
                return result
        except (httpx.HTTPError, OSError, KeyError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Expected real REPL observation timed out")


def ports():
    with socket.socket() as first, socket.socket() as second:
        first.bind(("127.0.0.1", 0))
        value = first.getsockname()[1]
        second.bind(("127.0.0.1", value + 1))
        return value


def identity(container):
    container.reload()
    return {
        "id": container.id,
        "status": container.status,
        "started_at": container.attrs["State"]["StartedAt"],
        "restarts": container.attrs["RestartCount"],
    }


def main():
    demo_mode = "--demo" in sys.argv
    OUTPUT.mkdir(parents=True, mode=0o700)
    os.environ["PULSE_HOME"] = str(OUTPUT / "state")
    engine = docker.from_env(timeout=10)
    engine.images.get("pulse-lab-demo:latest")
    original = {c.id: identity(c) for c in engine.containers.list(all=True)}
    app_port, api_port = ports(), ports()
    env = {
        **os.environ,
        "PULSE_LLM_MODEL": "",
        "PULSE_LAB_TOKEN": secrets.token_urlsafe(32),
        "PULSE_REPO_DEMO_PORT": str(app_port),
    }
    if not demo_mode:
        initialize(
            FIXTURE,
            project=f"pulse-repl-lab-{os.getpid()}",
            health_urls={"demo-api": f"http://127.0.0.1:{app_port}/health"},
        )
    profile = location(FIXTURE)
    compose = [
        "docker",
        "compose",
        "--project-directory",
        str(FIXTURE),
        "-p",
        f"pulse-repl-lab-{os.getpid()}",
        "-f",
        str(FIXTURE / "compose.yaml"),
    ]
    if not demo_mode:
        compose += ["-f", str(profile / "monitor.compose.json")]
    cli = shlex.split(os.getenv("PULSE_TEST_CLI", "")) or [sys.executable, "-m", "pulse.cli"]
    process = None
    result = {
        "result": "FAIL",
        "source": "real Docker, native API and REPL subprocess",
        "reasoning": "deterministic evidence; no mock or live LLM",
        "started_at": time.time(),
        "checks": [],
    }
    terminal = OUTPUT / "terminal.log"

    def output():
        return terminal.read_text()

    def send(command):
        assert process is not None and process.poll() is None and process.stdin is not None
        process.stdin.write(command + "\n")
        process.stdin.flush()

    def unavailable():
        try:
            httpx.get(f"http://127.0.0.1:{api_port}/api/v1/health", trust_env=False, timeout=1)
            return False
        except httpx.HTTPError:
            try:
                httpx.get(f"http://127.0.0.1:{api_port + 1}/health", trust_env=False, timeout=1)
                return False
            except httpx.HTTPError:
                return True

    try:
        subprocess.run([*compose, "config", "--quiet"], env=env, check=True)
        subprocess.run([*compose, "up", "-d", "--no-build", "--pull", "never"], env=env, check=True)
        cid = subprocess.check_output(
            [*compose, "ps", "-q", "demo-api"], env=env, text=True
        ).strip()
        app = engine.containers.get(cid)
        wait(lambda: httpx.get(f"http://127.0.0.1:{app_port}/health", trust_env=False).is_success)
        wait(
            lambda: (
                app.reload() is None
                and app.attrs["State"].get("Health", {}).get("Status") == "healthy"
            )
        )
        before = identity(app)
        with terminal.open("w") as log:
            process = subprocess.Popen(
                [*cli, "repl", *([] if demo_mode else [str(FIXTURE)])],
                cwd=FIXTURE,
                env=env,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=log,
                text=True,
                start_new_session=True,
            )
        wait(lambda: "pulse [repository-demo]" in output())
        send(f"/{'demo' if demo_mode else 'watch'} --no-browser --port {api_port}")
        wait(
            lambda: (
                httpx.get(
                    f"http://127.0.0.1:{api_port}/api/v1/project/identity", trust_env=False
                ).is_success
            )
        )
        from pulse.project.session import client

        with closing(client(FIXTURE)) as http:
            if demo_mode:
                wait(lambda: "[4/4] Local dashboard and monitoring ready" in output())
                assert not app.labels.get("pulse.monitor")
                assert http.get("/project").json()["read_only"] is True
                send("/demo --no-browser")
                wait(lambda: "Reusing the existing read-only session" in output())
            services = wait(lambda: http.get("/services").json())
            assert (
                len(services) == 1
                and services[0]["monitored"]
                and not services[0]["remediation_allowed"]
            )
            sid = services[0]["id"]
            if demo_mode:
                assert (
                    http.patch(
                        f"/services/{sid}/permissions",
                        json={"monitored": True, "remediation_allowed": True},
                    ).status_code
                    == 403
                )
                assert (
                    http.post(
                        f"/remediations/{uuid.uuid4()}/approve", json={"action_digest": "a" * 64}
                    ).status_code
                    == 409
                )
                from pulse.project.state import credentials

                with httpx.Client(
                    base_url=f"http://127.0.0.1:{api_port + 1}",
                    trust_env=False,
                    headers={"Authorization": "Bearer " + credentials(FIXTURE)["adapter_token"]},
                ) as gateway:
                    assert (
                        gateway.post(
                            f"/containers/{cid}/start", json={"action_id": str(uuid.uuid4())}
                        ).status_code
                        == 403
                    )
                    if original:
                        assert gateway.get(f"/containers/{next(iter(original))}").status_code == 403
                result["checks"].append(
                    "One /demo scans and auto-enrolls the current repository without pulse labels; repeated demo reuses the session; API and gateway reject recovery and foreign resources"
                )
            send("/status")
            send("/model")
            send("/services")
            send("/use " + sid)
            send("/ask What observed evidence describes this service?")
            question = wait(
                lambda: next(
                    (r for r in http.get("/incidents").json() if r["kind"] == "question"), None
                )
            )
            iid = question["id"]
            detail = wait(
                lambda: (
                    r
                    if (r := http.get(f"/incidents/{iid}").json()).get("diagnosis")
                    and r.get("tools")
                    else None
                )
            )
            send("/logs 20")
            send("/inspect " + iid)
            send("/timeline " + iid)
            send("/incidents --bad-flag")
            send("/context")
            wait(
                lambda: (
                    "Read-only investigation queued" in output()
                    and "Service context:" in output()
                    and "unrecognized arguments" in output()
                )
            )
            assert identity(app) == before
            result["checks"].append(
                "Background monitoring accepts scoped questions, logs, evidence inspection and malformed commands; app unchanged"
            )
            result["question"] = detail
            if "--browser" in sys.argv:
                browser_check(api_port, iid)
                result["checks"].append(
                    "Authenticated read-only dashboard/report at desktop and mobile widths: correct scope, recovery disabled, no overflow or JavaScript errors"
                )
            wait(lambda: (profile / "reports" / f"incident-{iid}.json").exists())
            send("/stop")
            wait(unavailable, 25)
            assert process.poll() is None and identity(app) == before
            result["checks"].append(
                "/stop leaves REPL and app alive; API/gateway stop and evidence report persists"
            )
            send("/report --format json")
            send(f"/{'demo' if demo_mode else 'watch'} --no-browser --port {api_port}")
            wait(
                lambda: (
                    httpx.get(
                        f"http://127.0.0.1:{api_port}/api/v1/project/identity", trust_env=False
                    ).is_success
                )
            )
            with closing(client(FIXTURE)) as restarted:
                rows = restarted.get("/incidents").raise_for_status().json()
                assert len([r for r in rows if r["kind"] == "question"]) == 1
                assert restarted.get(f"/incidents/{iid}").is_success
            result["checks"].append(
                "Restart retains the same question and evidence with no duplicate question or remediation"
            )
            # API readiness can precede /demo returning to its prompt.
            context_count = output().count("Repository: ")
            send("/context")
            wait(lambda: output().count("Repository: ") > context_count)
            process.send_signal(signal.SIGINT)
            wait(lambda: "Cancelled input. Monitoring continues" in output())
            send("/status")
            assert httpx.get(
                f"http://127.0.0.1:{api_port}/api/v1/health", trust_env=False
            ).is_success
            result["checks"].append(
                "Ctrl+C at the prompt preserves live monitoring and never retries a command"
            )
            process.kill()
            process.wait(timeout=5)
            wait(unavailable, 25)
            assert identity(app) == before
            with sqlite3.connect(profile / "gateway.db") as journal:
                executed = journal.execute(
                    "SELECT COUNT(*) FROM actions WHERE status='executed'"
                ).fetchone()[0]
                assert executed == 0
                result["executed_actions"] = executed
            result["checks"].append(
                "Hard REPL-owner death stops worker/API/gateway; app unchanged and zero executed mutations"
            )
            for original_id, prior in original.items():
                assert identity(engine.containers.get(original_id)) == prior
            result["unrelated_container_count"] = len(original)
            result["checks"].append(
                "All pre-existing containers preserve identity, start time, state and restart count"
            )
            result["result"] = "PASS"
    except Exception as error:
        result["error"] = type(error).__name__
        raise
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
            wait(unavailable, 25)
        subprocess.run([*compose, "down"], env=env, check=True)
        engine.close()
        result["ended_at"] = time.time()
        (OUTPUT / "result.json").write_text(json.dumps(redact(result), indent=2) + "\n")
        print(f"Real REPL result: {result['result']} · {OUTPUT / 'result.json'}")


def browser_check(api_port, iid):
    from playwright.sync_api import sync_playwright
    from pulse.project.state import credentials

    base = f"http://127.0.0.1:{api_port}"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
        )
        context = browser.new_context()
        assert (
            context.request.post(
                base + "/api/v1/session",
                data={"token": credentials(FIXTURE)["admin_token"]},
                headers={"Origin": base},
            ).status
            == 200
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for width in [1440, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            page.goto(base, wait_until="networkidle")
            page.locator("#workspace").wait_for(state="visible")
            assert "Read-only project demo" in page.locator("#scope").inner_text()
            assert "recovery is disabled" in page.locator("#services").inner_text()
            assert (
                page.get_by_role(
                    "button", name="Allow reviewed recovery for this service", exact=True
                ).count()
                == 0
            )
            page.get_by_role(
                "button", name="Open report & recovery choices", exact=True
            ).first.click()
            page.get_by_text("Diagnosis and citations", exact=True).wait_for(state="visible")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUTPUT / f"dashboard-{width}.png"), full_page=True)
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
