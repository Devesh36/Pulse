"""Supplemental real evidence-loss evaluation; no new application fault category."""

import json
import subprocess
import time
import uuid

import httpx

from pulse.lab.cli import LAB, ROOT, compose, request, reset, wait_for
from pulse.lab.evaluate import (
    detail,
    evaluate_diagnosis,
    healthy_baseline,
    record_report,
    run_scenario,
    write_quality,
)


def scrape(service):
    with httpx.Client(base_url="http://127.0.0.1:8109", trust_env=False, timeout=10) as http:
        response = http.get(
            "/api/v1/query", params={"query": f'up{{job="incident-lab",instance="{service}:8080"}}'}
        )
        response.raise_for_status()
        return response.json()["data"]["result"]


def restart_api(native):
    if native:
        result = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                str(LAB / "scripts/verification-session.py"),
                "restart-api",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError("Scoped native API restart failed; inspect local session logs")
    else:
        compose("restart", "api")


def run_loss(http, native):
    spec = json.loads((LAB / "fixtures/api-failure.json").read_text())
    report = {
        "scenario": "telemetry-loss",
        "mode": "mock-model",
        "status": "FAIL",
        "started_at": time.time(),
    }
    sid = None
    try:
        started = time.time()
        injected = request(http, "POST", "/lab/faults/telemetry-loss", json={})
        sid = injected["service_id"]
        rows = wait_for(
            lambda: request(http, "GET", "/incidents"),
            lambda rows: any(
                i["service_id"] == sid and i["kind"] == "errors" and i["created_at"] >= started
                for i in rows
            ),
            "existing HTTP fault detection",
            60,
        )
        incident = next(
            i
            for i in rows
            if i["service_id"] == sid and i["kind"] == "errors" and i["created_at"] >= started
        )
        iid = incident["id"]
        initial = wait_for(
            lambda: detail(http, iid),
            lambda i: i["state"] == "AWAITING_APPROVAL",
            "evidence-backed diagnosis",
            180,
        )
        report.update(
            incident_id=iid,
            service_id=sid,
            detection_latency_seconds=incident["created_at"] - started,
            diagnosis=evaluate_diagnosis(initial, spec),
            evidence=initial["tools"],
        )
        timeline = request(http, "GET", f"/incidents/{iid}/timeline")
        report["time_to_diagnosis_seconds"] = (
            next(e["at"] for e in reversed(timeline) if e["kind"] == "investigation.diagnosed")
            - incident["created_at"]
        )
        report["configured_targets"] = {
            "detection_deadline_seconds": 60,
            "expected_verification": "RECOVERED",
            "initial_verification": "INCONCLUSIVE",
        }
        action = next(a for a in initial["actions"] if a["status"] == "proposed")
        assert action["kind"] == "reset_errors"
        with httpx.Client(trust_env=False, timeout=10) as anonymous:
            denied = anonymous.post(
                str(http.base_url).rstrip("/") + f"/remediations/{action['id']}/approve",
                json={"action_digest": action["digest"]},
            )
            assert denied.status_code == 401
        invalid = http.post(
            f"/remediations/{action['id']}/approve", json={"action_digest": "0" * 64}
        )
        assert invalid.status_code == 409
        request(
            http,
            "PATCH",
            f"/services/{sid}/permissions",
            json={"monitored": True, "remediation_allowed": True},
        )
        request(
            http,
            "POST",
            f"/remediations/{action['id']}/approve",
            json={"action_digest": action["digest"]},
        )
        assert (
            http.post(
                f"/remediations/{action['id']}/approve", json={"action_digest": action["digest"]}
            ).status_code
            == 409
        )
        wait_for(
            lambda: detail(http, iid),
            lambda i: (
                i["state"] == "VERIFYING" and (i["verification"] or {}).get("sample_count", 0) >= 1
            ),
            "persisted verification progress",
            30,
        )
        request(http, "POST", f"/lab/telemetry/{sid}", json={"enabled": False})
        down = wait_for(
            lambda: scrape("demo-api"),
            lambda rows: rows and float(rows[0]["value"][1]) == 0,
            "selected metrics scrape failure",
            15,
        )
        peer = scrape("demo-worker")
        assert peer and float(peer[0]["value"][1]) == 1, "Unselected telemetry was interrupted"
        before = detail(http, iid)["verification"]
        report.update(
            progress_before_restart=before, selected_scrape_down=down, unselected_scrape_up=peer
        )
        restart_api(native)
        resumed = wait_for(
            lambda: detail(http, iid),
            lambda i: (i["verification"] or {}).get("resume_count", 0) >= 1,
            "verification resume after API restart",
            30,
        )
        assert resumed["verification"]["deadline_at"] == before["deadline_at"]
        assert resumed["verification"]["started_at"] == before["started_at"]
        assert resumed["verification"]["sample_count"] >= before["sample_count"]
        assert resumed["verification"]["samples"][: len(before["samples"])] == before["samples"]
        final = wait_for(
            lambda: detail(http, iid),
            lambda i: i["state"] == "FAILED",
            "original verification deadline",
            45,
        )
        assert final["verification"]["result"] == "INCONCLUSIVE", final["verification"]["reason"]
        assert final["verification"]["reason"] and final["verification"]["required_evidence"]
        assert any(
            "prometheus" in sample.get("rejected_evidence", {})
            for sample in final["verification"]["samples"]
        )
        report["inconclusive_verification"] = final["verification"]
        request(http, "POST", f"/lab/telemetry/{sid}", json={"enabled": True})
        restored = wait_for(
            lambda: scrape("demo-api"),
            lambda rows: rows and float(rows[0]["value"][1]) == 1,
            "selected telemetry restoration",
            15,
        )
        execution_audits = [
            a
            for a in request(http, "GET", "/audit")
            if a["operation"] == "remediation.executed" and a["resource_id"] == action["id"]
        ]
        executed_before = len(execution_audits)
        # There is no mutation replay. Only the same incident's read-only observation
        # window is explicitly requested after telemetry has been restored.
        request(http, "POST", f"/incidents/{iid}/verification/recheck")
        assert http.post(f"/incidents/{iid}/verification/recheck").status_code == 409
        recovered = wait_for(
            lambda: detail(http, iid),
            lambda i: i["state"] in ("RESOLVED", "FAILED"),
            "read-only fresh recovery verification",
            45,
        )
        assert recovered["state"] == "RESOLVED", recovered["verification"]["reason"]
        assert recovered["verification"]["result"] == "RECOVERED"
        assert recovered["verification"]["history"][-1]["result"] == "INCONCLUSIVE"
        events = request(http, "GET", f"/incidents/{iid}/timeline")
        # Detailed samples/tool outputs already appear in this report and remain
        # in the durable event journal. Keep timeline references and verdict data
        # without duplicating entire completed verification payloads.
        events = [
            {
                **event,
                "payload": {
                    key: value
                    for key, value in event["payload"].items()
                    if key
                    in {
                        "id",
                        "tool",
                        "success",
                        "at",
                        "from",
                        "to",
                        "reason",
                        "result",
                        "outcome",
                        "sample_count",
                        "required_evidence",
                        "deadline_at",
                        "missing_evidence",
                        "accepted_timestamps",
                        "rejected_evidence",
                        "failures",
                        "contradictions",
                        "tokens_used",
                    }
                },
            }
            for event in events
        ]
        assert (
            len(
                [
                    a
                    for a in request(http, "GET", "/audit")
                    if a["operation"] == "remediation.executed" and a["resource_id"] == action["id"]
                ]
            )
            == executed_before
            == 1
        )
        assert len(recovered["actions"]) == len(initial["actions"]) == 1
        time.sleep(6)
        matching = [
            i
            for i in request(http, "GET", "/incidents")
            if i["service_id"] == sid and i["kind"] == "errors" and i["created_at"] >= started
        ]
        assert len(matching) == 1 and matching[0]["id"] == iid
        report.update(
            status="PASS",
            verification=recovered["verification"],
            restored_scrape=restored,
            no_duplicate_incidents=True,
            mutation_execution_count=executed_before,
            approval_enforced=True,
            duplicate_rejected=True,
            restart_preserved_deadline=True,
            final_state=recovered["state"],
            timeline=events,
            execution_audits=execution_audits,
        )
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["completed_at"] = time.time()
        if sid:
            request(http, "POST", f"/lab/telemetry/{sid}", json={"enabled": True})
    return report


def evaluate_telemetry_loss(http, native=False):
    configured = request(http, "GET", "/settings")
    if configured["model"] != "mock/evidence":
        raise RuntimeError(
            "This focused deterministic evaluation requires the lab mock/evidence model; it measures real telemetry, not live-model accuracy"
        )
    original = configured["runtime"]
    settings = {
        **original,
        "interval_seconds": 2,
        "min_samples": 2,
        "window_seconds": 10,
        "cooldown_seconds": 0,
        "verification_seconds": 6,
        "recovery_grace_seconds": 15,
        "http_min_requests": 5,
        "verification_max_gap_seconds": 5,
    }
    run_id = str(uuid.uuid4())
    folder = LAB / "reports" / ("verification-" + run_id)
    folder.mkdir(parents=True)
    reports, baselines = [], []
    failure = None
    try:
        request(http, "PATCH", "/settings", json=settings)
        reset(http)
        for scenario in (
            "container-crash",
            "api-failure",
            "recovery-verification",
            "telemetry-loss",
        ):
            baseline = healthy_baseline(http)
            baselines.append(baseline)
            if baseline["false_positive_count"]:
                result = {
                    "scenario": scenario,
                    "status": "FAIL",
                    "mode": "mock-model",
                    "started_at": baseline["started_at"],
                    "completed_at": time.time(),
                    "error": "Unexpected incidents during healthy baseline; evaluation stopped",
                }
            else:
                print(f"Real verification evaluation: {scenario}", flush=True)
                result = (
                    run_loss(http, native)
                    if scenario == "telemetry-loss"
                    else run_scenario(http, scenario, mock=True)
                )
            result.update(
                run_id=run_id,
                evaluation_context={
                    "version": 1,
                    "suite": "telemetry-restoration",
                    "runtime": settings,
                },
                healthy_baseline=baseline,
            )
            reports.append(result)
            record_report(http, folder, result)
            assert result["status"] == "PASS", result.get("error", "Scenario failed")
            outcome = (
                "INCONCLUSIVE -> RECOVERED"
                if scenario == "telemetry-loss"
                else result.get("verification", {}).get("result")
            )
            print(f"{scenario}: PASS ({outcome})", flush=True)
            if result.get("inconclusive_verification"):
                print(result["inconclusive_verification"]["reason"], flush=True)
            print(result.get("verification", {}).get("reason", ""), flush=True)
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        raise
    finally:
        request(http, "PATCH", "/settings", json=original)
        summary = {
            "run_id": run_id,
            "mode": "mock-model / real Docker and Prometheus",
            "reports": reports,
            "healthy_baselines": baselines,
            "failure": failure,
            "passed": sum(r["status"] == "PASS" for r in reports),
            "scenario_count": 4,
        }
        (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        lines = [
            "# Recovery evidence evaluation",
            "",
            "Reasoning: mock/evidence. Observations: real Docker, HTTP probes and Prometheus.",
            "",
            "| Scenario | Result | Verdict |",
            "|---|---|---|",
        ]
        for report in reports:
            outcome = report.get("verification", {}).get("result", "unavailable")
            if report.get("inconclusive_verification"):
                outcome = "INCONCLUSIVE → " + outcome
            lines.append(f"| {report['scenario']} | {report['status']} | {outcome} |")
        for report in reports:
            lines.extend(
                [
                    "",
                    f"**{report['scenario']}**: "
                    + report.get("verification", {}).get("reason", ""),
                ]
            )
            if report.get("inconclusive_verification"):
                lines.extend(
                    [
                        "",
                        "Initial INCONCLUSIVE outcome: "
                        + report["inconclusive_verification"]["reason"],
                    ]
                )
        if failure:
            lines += ["", "Evaluation failed: " + failure]
        (folder / "summary.md").write_text("\n".join(lines) + "\n")
        if reports:
            write_quality(http, folder)
        print(f"Preserved evaluation reports: {folder}", flush=True)
