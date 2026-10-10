"""Repository-aware lab CLI. Only operates on the fixed pulse-lab Compose project."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

from pulse.distribution import project_root
from pulse.lab.catalog import SCENARIOS

ROOT = project_root()
LAB = ROOT / "examples/incident-lab"
API = "http://127.0.0.1:8100/api/v1"


def credentials():
    path = LAB / ".env"
    if not path.exists():
        # Exclusive creation preserves an existing user's file and credentials.
        values = {
            name: secrets.token_hex(32)
            for name in (
                "PULSE_ADMIN_TOKEN",
                "PULSE_ADAPTER_TOKEN",
                "PULSE_LAB_TOKEN",
                "PULSE_LAB_TEST_TOKEN",
                "POSTGRES_PASSWORD",
            )
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
        path.chmod(0o600)
    values = dotenv_values(path)
    if any(
        len(values.get(name) or "") < 16
        for name in (
            "PULSE_ADMIN_TOKEN",
            "PULSE_ADAPTER_TOKEN",
            "PULSE_LAB_TOKEN",
            "PULSE_LAB_TEST_TOKEN",
            "POSTGRES_PASSWORD",
        )
    ):
        raise RuntimeError(
            "Lab credentials are missing; configure the private lab .env file securely"
        )
    return values


def compose(*args, dashboard=False):
    credentials()
    command = [
        "docker",
        "compose",
        "--project-name",
        "pulse-lab",
        "--project-directory",
        str(LAB),
        "--env-file",
        str(LAB / ".env"),
        "-f",
        str(LAB / "docker-compose.yml"),
    ]
    # Pass the trusted system CA as a build secret, never disable TLS verification.
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and Path(ca).is_file():
        setup = ROOT.parent / "pulse-lab-build"
        setup.mkdir(exist_ok=True)
        config = {
            "secrets": {"cloud_ca": {"file": ca}},
            "services": {
                name: {"build": {"secrets": ["cloud_ca"]}}
                for name in ("api", "gateway", "demo-api", "demo-worker", "web")
            },
        }
        override = setup / "compose-ca.json"
        override.write_text(json.dumps(config))
        command += ["-f", str(override)]
    if dashboard:
        command += ["--profile", "dashboard"]
    environ = os.environ.copy()
    environ.setdefault("BUILDX_CONFIG", str(ROOT.parent / ".cache/docker/buildx"))
    environ.setdefault("COMPOSE_PARALLEL_LIMIT", "3")
    # Do not print expanded Compose configuration, environment values, or credentials.
    result = subprocess.run(command + list(args), env=environ)
    if result.returncode:
        raise RuntimeError(
            f"Lab Compose operation failed ({result.returncode}); check Docker availability and trusted network access"
        )


def client(test=False):
    values = credentials()
    return httpx.Client(
        base_url=API,
        timeout=15,
        trust_env=False,
        headers={
            "Authorization": "Bearer "
            + str(values["PULSE_LAB_TEST_TOKEN" if test else "PULSE_ADMIN_TOKEN"])
        },
    )


def wait_for(fetch, predicate, description, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = fetch()
            if predicate(value):
                return value
        except (httpx.RequestError, httpx.HTTPStatusError):
            pass
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {description} ({seconds}s)")


def request(http, method, path, **kwargs):
    result = http.request(method, path, **kwargs)
    if not result.is_success:
        # No response headers, request tokens, or tracebacks containing credentials.
        raise RuntimeError(f"Lab API {method} {path} failed: HTTP {result.status_code}")
    return result.json()


def status(http):
    return request(http, "GET", "/lab/status")


def ready(http):
    def healthy(value):
        rows = value["services"]
        return (
            value["docker"] == "connected"
            and len(rows) == 2
            and all(
                s["snapshot"].get("status") == "running"
                and s["snapshot"].get("health") == "healthy"
                and time.time() - s["last_seen"] < 30
                for s in rows
            )
        )

    return wait_for(
        lambda: status(http), healthy, "fresh lab discovery and healthy containers", 180
    )


def reset(http):
    # Explicit cleanup first cancels/dismisses active investigations; it cannot
    # silently fix a fault while an incident is awaiting approval or verification.
    for incident in request(http, "GET", "/incidents"):
        iid = incident["id"]
        if incident["state"] == "INVESTIGATING":
            request(http, "POST", f"/incidents/{iid}/cancel")
            incident = request(http, "GET", f"/incidents/{iid}")
        if incident["state"] in ("REMEDIATING", "VERIFYING"):
            incident = wait_for(
                lambda iid=iid: request(http, "GET", f"/incidents/{iid}"),
                lambda i: i["state"] in ("RESOLVED", "FAILED"),
                "completion before cleanup",
                90,
            )
        if incident["state"] in ("DETECTED", "DIAGNOSED", "AWAITING_APPROVAL", "FAILED"):
            request(
                http,
                "POST",
                f"/incidents/{iid}/dismiss",
                json={"reason": "Explicit lab cleanup; preserve original evidence and outcome"},
            )
    compose("start", "demo-api", "demo-worker")
    wait_for(
        lambda: status(http),
        lambda v: (
            len(v["services"]) == 2
            and all(s["snapshot"].get("status") == "running" for s in v["services"])
        ),
        "running demo services",
    )
    request(http, "POST", "/lab/reset")
    ready(http)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pulse")
    sub = parser.add_subparsers(dest="group", required=True)
    lab = sub.add_parser("lab")
    commands = lab.add_subparsers(dest="command", required=True)
    up = commands.add_parser("up")
    up.add_argument("--dashboard", action="store_true")
    commands.add_parser("status")
    quality = commands.add_parser(
        "quality", help="Review recorded evaluations without changing resources"
    )
    quality.add_argument("--format", choices=["json", "markdown"], default="markdown")
    quality.add_argument(
        "--reports-dir",
        type=Path,
        help="Review retained JSON reports offline; no Docker or API connection",
    )
    quality.add_argument(
        "--check",
        action="store_true",
        help="Exit 2 unless every scenario has complete, compatible evidence without regressions",
    )
    quality.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit 2 for observed failures or regression flags; missing baselines remain explicit",
    )
    run = commands.add_parser("run")
    run.add_argument("scenario", choices=SCENARIOS)
    run.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly authorize only the scenario lab remediation through the test principal",
    )
    run.add_argument("--live-model", action="store_true")
    run.add_argument(
        "--native-api",
        action="store_true",
        help="Restart only the scoped native verification-session API",
    )
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--all", action="store_true", required=True)
    evaluate.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly authorize reviewed lab actions through the real approval API",
    )
    evaluate.add_argument("--live-model", action="store_true")
    evaluate.add_argument(
        "--native-api",
        action="store_true",
        help="Restart only the scoped native verification-session API",
    )
    report = commands.add_parser("report")
    report.add_argument("--format", choices=["json", "markdown"], default="json")
    report.add_argument(
        "--verification", action="store_true", help="Export the latest recovery evidence evaluation"
    )
    commands.add_parser("reset")
    commands.add_parser("stop")
    commands.add_parser("down")
    args = parser.parse_args(argv)
    try:
        if args.command == "quality":
            from pulse.lab.quality import from_reports, markdown

            if args.reports_dir:
                if not args.reports_dir.is_dir():
                    raise RuntimeError("Report directory does not exist")
                review = from_reports(args.reports_dir)
            else:
                if not (LAB / ".env").exists():
                    raise RuntimeError(
                        "No lab credentials; use --reports-dir for an offline quality review"
                    )
                with client() as http:
                    review = request(http, "GET", "/lab/quality")
            print(json.dumps(review, indent=2) if args.format == "json" else markdown(review))
            return (
                2
                if (args.check and review["status"] != "NO_REGRESSIONS_OBSERVED")
                or (args.fail_on_regression and review["status"] == "ATTENTION_REQUIRED")
                else 0
            )
        elif args.command == "up":
            compose(
                "build",
                "api",
                "demo-api",
                *(["web"] if args.dashboard else []),
                dashboard=args.dashboard,
            )
            compose("up", "--no-build", "-d", dashboard=args.dashboard)
            with client() as http:
                ready(http)
                print("Lab ready: real Docker discovery and both demo health checks verified.")
        elif args.command == "stop":
            compose("stop", dashboard=True)
            print("Lab stopped. Credentials, databases, volumes and reports retained.")
        elif args.command == "down":
            # All resources here belong to the fixed disposable lab project.
            compose("down", "--volumes", "--remove-orphans", dashboard=True)
            for tag in ("pulse-lab-backend", "pulse-lab-demo", "pulse-lab-web"):
                image = subprocess.run(
                    [
                        "docker",
                        "image",
                        "inspect",
                        tag,
                        "--format",
                        '{{index .Config.Labels "com.docker.compose.project"}}',
                    ],
                    capture_output=True,
                    text=True,
                )
                if image.returncode == 0:
                    if image.stdout.strip() != "pulse-lab":
                        raise RuntimeError(
                            "A reserved lab image belongs to another project; refusing removal"
                        )
                    subprocess.run(["docker", "image", "rm", tag], check=True)
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=pulse-lab",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            volumes = subprocess.run(
                [
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=pulse-lab",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            networks = subprocess.run(
                [
                    "docker",
                    "network",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=pulse-lab",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout.strip() or volumes.stdout.strip() or networks.stdout.strip():
                raise RuntimeError("Lab cleanup left resources behind")
            print(
                "Lab cleanup verified: no project containers, networks, volumes, or tagged build images remain."
            )
        elif args.command == "report":
            extension = "json" if args.format == "json" else "md"
            if args.verification:
                candidates = list((LAB / "reports").glob(f"verification-*/summary.{extension}"))
                if not candidates:
                    raise RuntimeError(
                        "No recovery evidence report; run pulse lab run telemetry-loss --approve first"
                    )
                path = max(candidates, key=lambda item: item.stat().st_mtime)
            else:
                candidates = list((LAB / "reports").rglob(f"evaluation-summary.{extension}"))
                path = (
                    max(candidates, key=lambda item: item.stat().st_mtime)
                    if candidates
                    else LAB / "reports" / f"evaluation-summary.{extension}"
                )
            if not path.exists():
                raise RuntimeError(
                    "No evaluation report; run pulse lab evaluate --all --approve first"
                )
            print(path.read_text())
        else:
            with client(test=args.command in ("run", "evaluate")) as http:
                if args.command == "status":
                    print(json.dumps(status(http), indent=2))
                elif args.command == "reset":
                    reset(http)
                    print("Lab reset; evidence and evaluation history retained.")
                else:
                    from pulse.lab.evaluate import evaluate

                    if sys.flags.optimize:
                        raise RuntimeError(
                            "Run evaluation without Python optimization so all assertions execute"
                        )
                    if not args.approve:
                        raise RuntimeError(
                            "Evaluation mutates lab resources. Pass --approve to explicitly authorize its scoped test actions, or use dashboard fault injection and manual approval."
                        )
                    if args.command == "run" and args.scenario == "telemetry-loss":
                        from pulse.lab.telemetry_loss import evaluate_telemetry_loss

                        evaluate_telemetry_loss(http, native=args.native_api)
                        return 0
                    evaluate(
                        http,
                        [name for name in SCENARIOS if name != "telemetry-loss"]
                        if args.command == "evaluate"
                        else [args.scenario],
                        live=args.live_model,
                        native=args.native_api,
                    )
    except (AssertionError, RuntimeError, httpx.HTTPError, OSError) as error:
        print(f"Lab operation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
