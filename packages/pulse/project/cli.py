"""Repository commands. Runtime changes always go through the existing approval API."""

import argparse
import json
import re
import shlex
import sys
import time
import uuid
import webbrowser
from contextlib import closing

import httpx
import yaml

from pulse.core.redaction import redact
from pulse.project import session
from pulse.project.scan import repository, scan
from pulse.project.state import initialize, location

COMMANDS = {
    "scan",
    "init",
    "watch",
    "dashboard",
    "incidents",
    "report",
    "approve",
    "reject",
    "recheck",
    "permissions",
}


def safe_text(value):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", redact(value))


def identifier(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as error:
        raise RuntimeError(
            "Use the exact incident/action/service UUID from this project's report"
        ) from error
    return value


def setup_instructions(profile):
    root = profile["root"]
    folder = location(root)
    command = " ".join(
        shlex.quote(str(part))
        for part in [
            "docker",
            "compose",
            "--project-directory",
            root,
            "-p",
            profile["compose_project"],
            "-f",
            repository(root) / profile["compose_file"],
            "-f",
            folder / "monitor.compose.json",
            "up",
            "-d",
        ]
    )
    return f"Profile: {folder / 'profile.json'}\nReview the enrollment override: {folder / 'monitor.compose.json'}\nTo apply its opt-in labels yourself (Compose may recreate services):\n{command}\nThen: pulse watch {shlex.quote(root)}\nNo app command was executed by Pulse."


def report_markdown(report):
    verification = report.get("verification") or {}
    diagnosis = report.get("diagnosis") or {}
    return safe_text(
        f"# Pulse incident report\n\n{report['title']}\n\nIncident: {report['id']}\nState: {report['state']}\n\nDiagnosis: {diagnosis.get('summary', 'Not yet diagnosed')}\n\nVerification: {verification.get('result') or 'No completed verification'}\n{verification.get('reason', '')}\n\nRecorded tools: {len(report.get('tools', []))}\nTimeline entries: {len(report.get('timeline', []))}\n\nThe JSON report retains citations, tool results, action digests and supporting verification observations.\n"
    )


def approval(http, aid, digest=None, yes=False, prompt=input):
    action = http.get(f"/remediations/{identifier(aid)}").raise_for_status().json()
    if action.get("read_only"):
        raise RuntimeError(
            "Project demo is read-only. Stop it, then use normal monitoring and reviewed enrollment to enable recovery; no approval was issued."
        )
    if (
        action["status"] != "proposed"
        or action["expires_at"] <= time.time()
        or action["incident_state"] != "AWAITING_APPROVAL"
    ):
        raise RuntimeError(
            "This proposal is expired or no longer pending; inspect the current report. No action was approved."
        )
    if not action["remediation_allowed"]:
        raise RuntimeError(
            f"Recovery permission is disabled. Review the service and enable it explicitly with pulse permissions {action['service_id']} --allow-recovery (or in the project dashboard)."
        )
    if digest is not None and digest != action["digest"]:
        raise RuntimeError("Digest differs from the current proposal; no action was approved")
    if yes and digest is None:
        raise RuntimeError(
            "Noninteractive approval requires --yes and the exact --digest from the reviewed proposal"
        )
    print(
        safe_text(
            json.dumps(
                {
                    key: action[key]
                    for key in [
                        "id",
                        "service_name",
                        "container_id",
                        "kind",
                        "reason",
                        "digest",
                        "expires_at",
                    ]
                },
                indent=2,
            )
        )
    )
    answer = ""
    if not yes:
        try:
            answer = prompt("Approve this exact action once? [y/N] ").strip().lower()
        except EOFError:
            pass
    if not yes and answer not in {"y", "yes"}:
        print("No approval issued. You can handle the incident yourself.")
        return False
    http.post(
        f"/remediations/{aid}/approve", json={"action_digest": action["digest"]}
    ).raise_for_status()
    print("Approval accepted. Keep pulse watch running to observe the recovery verdict.")
    return True


def main(argv, approval_prompt=None):
    parser = argparse.ArgumentParser(
        prog="pulse", description="Inspect and monitor one local repository"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "init", "watch", "dashboard", "incidents"):
        command = commands.add_parser(name)
        command.add_argument("repo", nargs="?", default=".")
        if name in {"scan", "incidents"}:
            command.add_argument("--format", choices=["text", "json"], default="text")
        if name == "init":
            command.add_argument("--compose-file")
            command.add_argument("--compose-project")
            command.add_argument("--recovery-service", action="append", default=[])
            command.add_argument("--health", action="append", default=[], metavar="SERVICE=URL")
            command.add_argument("--prometheus-url", default="")
        if name == "watch":
            command.add_argument("--port", type=int, default=8765)
            command.add_argument("--no-browser", action="store_true")
            command.add_argument("--model")
            command.add_argument(
                "--read-only",
                action="store_true",
                help="Observe strictly scoped project services without label changes; gateway rejects all recovery",
            )
    report = commands.add_parser("report")
    report.add_argument("--repo", default=".")
    report.add_argument("--incident")
    report.add_argument("--format", choices=["json", "markdown"], default="markdown")
    for name in ("approve", "reject", "recheck", "permissions"):
        command = commands.add_parser(name)
        command.add_argument("id")
        command.add_argument("--repo", default=".")
        if name == "approve":
            command.add_argument("--digest")
            command.add_argument("--yes", action="store_true")
        if name == "permissions":
            permission = command.add_mutually_exclusive_group(required=True)
            permission.add_argument("--allow-recovery", action="store_true")
            permission.add_argument("--deny-recovery", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            inventory = scan(args.repo)
            print(
                json.dumps(redact(inventory), indent=2)
                if args.format == "json"
                else safe_text(
                    f"Project: {inventory['name']}\nLanguages: {', '.join(inventory['languages']) or 'not inferred'}\nFrameworks: {', '.join(inventory['frameworks']) or 'not inferred'}\nCompose services: {', '.join(inventory['services']) or 'not declared'}\n{inventory['scope']}\n"
                    + "\n".join(inventory["warnings"])
                )
            )
        elif args.command == "init":
            probes = {}
            for entry in args.health:
                if "=" not in entry:
                    raise RuntimeError(
                        "Health probes use --health SERVICE=http://127.0.0.1:PORT/health"
                    )
                service, url = entry.split("=", 1)
                if service in probes:
                    raise RuntimeError("Health probes must be unique per service")
                probes[service] = url
            profile = initialize(
                args.repo,
                args.compose_file,
                args.compose_project,
                args.recovery_service,
                probes,
                args.prometheus_url,
            )
            print(setup_instructions(profile))
        elif args.command == "watch":
            if not (location(args.repo) / "profile.json").exists():
                profile = initialize(args.repo)
                print(setup_instructions(profile), flush=True)
            session.watch(args.repo, args.port, not args.no_browser, args.model, args.read_only)
        elif args.command == "report":
            folder = location(args.repo) / "reports"
            if args.incident:
                selected = folder / f"incident-{identifier(args.incident)}.json"
            else:
                candidates = list(folder.glob("incident-*.json"))
                if not candidates:
                    raise RuntimeError(
                        "No retained project incidents yet. Run pulse watch to collect real observations."
                    )
                selected = max(candidates, key=lambda path: path.stat().st_mtime)
            if (
                selected.is_symlink()
                or folder.is_symlink()
                or selected.stat().st_size > 4 * 1024 * 1024
            ):
                raise RuntimeError("Report is an unsafe symlink or exceeds the 4 MiB read limit")
            data = json.loads(selected.read_text())
            print(
                json.dumps(redact(data), indent=2)
                if args.format == "json"
                else report_markdown(data)
            )
        else:
            with closing(session.client(args.repo)) as http:
                if args.command == "dashboard":
                    base = str(http.base_url).split("/api/v1")[0]
                    webbrowser.open(base)
                    print(f"Project dashboard: {base}")
                elif args.command == "incidents":
                    incidents = http.get("/incidents").raise_for_status().json()
                    print(
                        json.dumps(redact(incidents), indent=2)
                        if args.format == "json"
                        else "\n".join(
                            safe_text(f"{row['id']} · {row['state']} · {row['title']}")
                            for row in incidents
                        )
                        or "No recorded incidents. Check actual telemetry coverage in the dashboard."
                    )
                elif args.command == "approve":
                    approval(http, args.id, args.digest, args.yes, prompt=approval_prompt or input)
                elif args.command == "reject":
                    http.post(
                        f"/remediations/{identifier(args.id)}/reject", json={}
                    ).raise_for_status()
                    print("Proposal rejected. No recovery action was executed by this command.")
                elif args.command == "recheck":
                    http.post(
                        f"/incidents/{identifier(args.id)}/verification/recheck", json={}
                    ).raise_for_status()
                    print("Read-only verification requested; no remediation will be replayed.")
                elif args.command == "permissions":
                    sid = identifier(args.id)
                    service = http.get(f"/services/{sid}").raise_for_status().json()
                    labels = service["snapshot"].get("labels", {})
                    if args.allow_recovery and (
                        labels.get("pulse.remediate") != "true"
                        or labels.get("pulse.environment") != "development"
                    ):
                        raise RuntimeError(
                            "Recovery requires explicit pulse.remediate=true and pulse.environment=development labels. No permission was changed."
                        )
                    http.patch(
                        f"/services/{sid}/permissions",
                        json={
                            "monitored": service["monitored"],
                            "remediation_allowed": args.allow_recovery,
                        },
                    ).raise_for_status()
                    print(
                        "Project service permission updated. Each recovery action still needs its own digest-bound approval."
                    )
        return 0
    except (
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        yaml.YAMLError,
        httpx.HTTPError,
    ) as error:
        explanation = (
            safe_text(str(error)) if isinstance(error, RuntimeError) else type(error).__name__
        )
        print(f"Project operation unavailable: {explanation}", file=sys.stderr)
        return 1
