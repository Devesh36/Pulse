"""Opt-in real repository-companion check. Only synthetic fixture resources are changed.

Run: uv run python examples/incident-lab/scripts/project-session.py
Requires local Docker and cached pulse-lab-demo:latest / alpine:3.21 images.
Reports and Pulse databases are retained outside the checkout. No live LLM calls.
"""

import json
import os
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import docker
import httpx
from pulse.project.state import credentials, initialize, location

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "examples/incident-lab/repository-demo"
OUTPUT = ROOT.parent / "pulse-project-session" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def port():
    with socket.socket() as channel:
        channel.bind(("127.0.0.1", 0))
        return channel.getsockname()[1]


def wait(operation, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = operation()
            if value:
                return value
        except (httpx.HTTPError, KeyError):
            pass
        time.sleep(1)
    raise RuntimeError("Expected real observation did not arrive within the deadline")


def identity(container):
    container.reload()
    return {
        "id": container.id,
        "status": container.status,
        "started_at": container.attrs["State"]["StartedAt"],
        "restart_count": container.attrs["RestartCount"],
    }


def main():
    OUTPUT.mkdir(parents=True, mode=0o700)
    os.environ["PULSE_HOME"] = str(OUTPUT / "state")
    engine = docker.from_env(timeout=10)
    engine.images.get("pulse-lab-demo:latest")
    engine.images.get("alpine:3.21")
    original = {container.id: identity(container) for container in engine.containers.list(all=True)}
    project = f"pulse-repository-lab-{os.getpid()}"
    app_port, api_port = port(), port()
    token = secrets.token_urlsafe(32)
    env = {**os.environ, "PULSE_LAB_TOKEN": token, "PULSE_REPO_DEMO_PORT": str(app_port)}
    env.pop("PULSE_LLM_MODEL", None)
    compose = [
        "docker",
        "compose",
        "--project-directory",
        str(FIXTURE),
        "-p",
        project,
        "-f",
        str(FIXTURE / "compose.yaml"),
    ]
    initialize(
        FIXTURE,
        project=project,
        recovery_services=["demo-api"],
        health_urls={"demo-api": f"http://127.0.0.1:{app_port}/health"},
    )
    command = [*compose, "-f", str(location(FIXTURE) / "monitor.compose.json")]
    subprocess.run([*command, "config", "--quiet"], env=env, check=True)
    peer = None
    watcher = None
    result = {
        "result": "FAIL",
        "started_at": time.time(),
        "source": "real Docker and HTTP measurements",
        "reasoning": "deterministic evidence; no live LLM",
        "checks": [],
    }
    log = (OUTPUT / "terminal.log").open("w")
    http = httpx.Client(
        base_url=f"http://127.0.0.1:{api_port}/api/v1/",
        trust_env=False,
        timeout=15,
        headers={"Authorization": "Bearer " + credentials(FIXTURE)["admin_token"]},
    )

    def launch():
        nonlocal watcher
        watcher = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pulse.cli",
                "watch",
                str(FIXTURE),
                "--port",
                str(api_port),
                "--no-browser",
            ],
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        wait(lambda: http.get("/project").is_success, 45)

    try:
        subprocess.run([*command, "up", "-d", "--no-build", "--pull", "never"], env=env, check=True)
        cid = subprocess.check_output(
            [*command, "ps", "-q", "demo-api"], env=env, text=True
        ).strip()
        app = engine.containers.get(cid)
        wait(lambda: httpx.get(f"http://127.0.0.1:{app_port}/health", trust_env=False).is_success)
        wait(
            lambda: (
                app.reload() is None
                and app.attrs["State"].get("Health", {}).get("Status") == "healthy"
            )
        )
        # A same-name Compose service from another working directory must stay excluded.
        peer = engine.containers.run(
            "alpine:3.21",
            ["sleep", "600"],
            detach=True,
            name=project + "-scope-peer",
            network_mode="none",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit="32m",
            labels={
                "pulse.monitor": "true",
                "pulse.remediate": "true",
                "pulse.environment": "development",
                "com.docker.compose.project": project,
                "com.docker.compose.project.working_dir": str(OUTPUT / "unrelated"),
                "com.docker.compose.service": "demo-api",
            },
        )
        peer_before = identity(peer)
        launch()
        service = wait(lambda: next(iter(http.get("/services").json()), None))
        assert service["container_id"] == cid and len(http.get("/services").json()) == 1
        assert service["remediation_allowed"] is False
        assert http.post("/lab/reset", json={}).status_code == 403
        gateway = httpx.Client(
            base_url=f"http://127.0.0.1:{api_port + 1}",
            trust_env=False,
            headers={"Authorization": "Bearer " + credentials(FIXTURE)["adapter_token"]},
        )
        assert gateway.get(f"/containers/{peer.id}").status_code == 403
        gateway.close()
        result["checks"].append(
            "Only selected repository discovered; same-project peer rejected; lab controls disabled"
        )
        response = httpx.post(
            f"http://127.0.0.1:{app_port}/control/crash",
            json={},
            headers={"X-Lab-Token": token},
            trust_env=False,
        )
        response.raise_for_status()
        incident = wait(
            lambda: next(
                (
                    row
                    for row in http.get("/incidents").json()
                    if row["state"] == "AWAITING_APPROVAL" and row["kind"] == "stopped"
                ),
                None,
            )
        )
        iid = incident["id"]
        detail = http.get(f"/incidents/{iid}").raise_for_status().json()
        action = detail["actions"][0]
        assert action["kind"] == "start"
        time.sleep(3)
        assert identity(app)["status"] == "exited", "Pulse acted without approval"
        assert (
            http.post(
                f"/remediations/{action['id']}/approve", json={"action_digest": action["digest"]}
            ).status_code
            == 409
        )
        assert http.patch(
            f"/services/{service['id']}/permissions",
            json={"monitored": True, "remediation_allowed": True},
        ).is_success
        review = subprocess.run(
            [sys.executable, "-m", "pulse.cli", "approve", action["id"], "--repo", str(FIXTURE)],
            env=env,
            input="\n",
            text=True,
            capture_output=True,
            check=False,
        )
        assert review.returncode == 0, review.stderr
        assert "No approval issued" in review.stdout and identity(app)["status"] == "exited"
        result["checks"].append(
            "Real crash exit 42 diagnosed; no mutation before permission and digest-bound approval; terminal default is decline"
        )
        approved = subprocess.run(
            [
                sys.executable,
                "-m",
                "pulse.cli",
                "approve",
                action["id"],
                "--repo",
                str(FIXTURE),
                "--yes",
                "--digest",
                action["digest"],
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Approval accepted" in approved.stdout
        before_restart = wait(
            lambda: (
                row
                if (row := http.get(f"/incidents/{iid}").json()).get("verification")
                and row["verification"].get("sample_count", 0) >= 1
                else None
            )
        )
        original_deadline = before_restart["verification"]["deadline_at"]
        watcher.send_signal(signal.SIGINT)
        watcher.wait(timeout=30)
        assert identity(app)["status"] == "running" and identity(peer) == peer_before
        result["checks"].append(
            "Session stopped during verification; app and unrelated peer left running; progress persisted"
        )
        launch()
        assert (
            http.get(f"/incidents/{iid}").json()["verification"]["deadline_at"] == original_deadline
        )
        resolved = wait(
            lambda: (
                row
                if (row := http.get(f"/incidents/{iid}").json())
                .get("verification", {})
                .get("result")
                else None
            ),
            90,
        )
        # A restart gap may make this first window inconclusive; a read-only recheck observes a new window.
        result["initial_verification"] = resolved["verification"]
        result["original_deadline_at"] = original_deadline
        if resolved["verification"]["result"] == "INCONCLUSIVE":
            assert http.post(f"/incidents/{iid}/verification/recheck", json={}).is_success
            resolved = wait(
                lambda: (
                    row
                    if (row := http.get(f"/incidents/{iid}").json())["state"] == "RESOLVED"
                    else None
                ),
                90,
            )
        assert resolved["verification"]["result"] == "RECOVERED"
        assert len([row for row in http.get("/incidents").json() if row["kind"] == "stopped"]) == 1
        assert (
            http.post(
                f"/remediations/{action['id']}/approve", json={"action_digest": action["digest"]}
            ).status_code
            == 409
        )
        result["incident"] = resolved
        result["timeline"] = http.get(f"/incidents/{iid}/timeline").json()
        result["audit"] = http.get("/audit").json()
        result["incident_counts"] = {
            kind: sum(row["kind"] == kind for row in http.get("/incidents").json())
            for kind in ("stopped", "unhealthy")
        }
        with sqlite3.connect(location(FIXTURE) / "gateway.db") as journal:
            assert (
                journal.execute("SELECT COUNT(*) FROM actions WHERE status='executed'").fetchone()[
                    0
                ]
                == 1
            )
        result["checks"].append(
            "Measured RECOVERED after restart; one stopped incident and one journaled mutation; approval replay rejected"
        )
        wait(
            lambda: (
                (
                    json.loads(
                        (location(FIXTURE) / "reports" / f"incident-{iid}.json").read_text()
                    ).get("verification")
                    or {}
                ).get("result")
                == "RECOVERED"
            )
        )
        if "--browser" in sys.argv:
            browser_check(api_port, iid)
            result["checks"].append(
                "Actual authenticated dashboard and downloaded evidence match API at desktop/mobile widths; no overflow or JavaScript errors"
            )
        before_kill = identity(app)
        watcher.kill()
        watcher.wait(timeout=5)
        wait(lambda: _unavailable(api_port) and _unavailable(api_port + 1), 20)
        assert identity(app) == before_kill and identity(peer) == peer_before
        report = subprocess.run(
            [
                sys.executable,
                "-m",
                "pulse.cli",
                "report",
                "--repo",
                str(FIXTURE),
                "--format",
                "json",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(report.stdout)["id"] == iid
        assert json.loads(report.stdout)["verification"]["result"] == "RECOVERED"
        result["checks"].append(
            "Hard terminal-owner death stops both child services; app unchanged; report readable offline"
        )
        for original_id, before in original.items():
            assert identity(engine.containers.get(original_id)) == before, (
                "A pre-existing container changed. Run this acceptance check separately from other lab fault tests."
            )
        result["unrelated_container_count"] = len(original)
        result["checks"].append(
            "All pre-existing container identities, states, start times and restart counts unchanged"
        )
        result["result"] = "PASS"
    finally:
        result["completed_at"] = time.time()
        if watcher and watcher.poll() is None:
            watcher.terminate()
            watcher.wait(timeout=30)
        http.close()
        log.close()
        if peer:
            peer.remove(force=True)
        subprocess.run([*command, "down", "--timeout", "5"], env=env, check=True)
        engine.close()
        (OUTPUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"PASS: {len(result['checks'])} real checks. Retained measurements and databases: {OUTPUT}"
    )


def _unavailable(port_number):
    try:
        httpx.get(f"http://127.0.0.1:{port_number}/", timeout=1, trust_env=False)
        return False
    except httpx.HTTPError:
        return True


def browser_check(api_port, iid):
    from playwright.sync_api import sync_playwright

    base = f"http://127.0.0.1:{api_port}"
    with sync_playwright() as playwright:
        options = {"headless": True}
        if Path("/usr/bin/chromium").exists():
            options.update(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100}, accept_downloads=True
        )
        response = context.request.post(
            base + "/api/v1/session",
            data={"token": credentials(FIXTURE)["admin_token"]},
            headers={"Origin": base},
        )
        assert response.status == 200
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="domcontentloaded")
        page.locator("#workspace").wait_for(state="visible")
        row = page.locator("#incidents .row").filter(has_text="Container unexpectedly stopped")
        row.get_by_role("button").click()
        page.get_by_role("heading", name="Verification: RECOVERED", exact=True).wait_for()
        with page.expect_download() as download:
            page.get_by_role("button", name="Download JSON report").click()
        downloaded = json.loads(Path(download.value.path()).read_text())
        assert downloaded["id"] == iid and downloaded["verification"]["result"] == "RECOVERED"
        assert credentials(FIXTURE)["admin_token"] not in page.content()
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1100 if width == 1440 else 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(OUTPUT / f"dashboard-{width}.png"), full_page=True)
        page.route("**/api/v1/**", lambda route: route.abort())
        page.get_by_text("Displayed evidence is historical.", exact=False).wait_for(timeout=10000)
        page.unroute("**/api/v1/**")
        page.get_by_text("Gateway: connected", exact=False).wait_for(timeout=10000)
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
