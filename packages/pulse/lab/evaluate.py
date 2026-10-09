"""Real-infrastructure evaluator. Hidden fixtures never enter investigation context."""

import json
import time

import httpx

from pulse.lab.cli import LAB, compose, ready, request, reset, wait_for

REPORTS = LAB / "reports"
TARGETS = {
    "detection_rate": 1.0,
    "false_positive_count": 0,
    "root_cause_accuracy": 1.0,
    "approval_enforcement": 1.0,
    "verification_accuracy": 1.0,
}


def detail(http, iid):
    return request(http, "GET", f"/incidents/{iid}")


def healthy_baseline(http, seconds=14):
    ready(http)
    began = time.time()
    stop = time.monotonic() + seconds
    while time.monotonic() < stop:
        time.sleep(2)
    unexpected = [i for i in request(http, "GET", "/incidents") if i["created_at"] >= began]
    return {
        "started_at": began,
        "duration_seconds": time.time() - began,
        "unexpected_incidents": [i["id"] for i in unexpected],
        "false_positive_count": len(unexpected),
    }


def evaluate_diagnosis(incident, spec):
    tools = incident["tools"]
    evidence = {t["id"]: t for t in tools if t["success"]}
    diagnosis = incident["diagnosis"] or {}
    citations = [
        eid for finding in diagnosis.get("root_causes", []) for eid in finding["evidence_ids"]
    ]
    assert set(spec["required_tools"]).issubset({t["name"] for t in evidence.values()}), (
        "Required real tool evidence missing"
    )
    assert citations and all(eid in evidence for eid in citations), (
        "Diagnosis contains missing evidence references"
    )
    assert diagnosis["affected_service"] and diagnosis["incident_id"] == incident["id"]
    if spec["expected_category"]:
        assert diagnosis.get("category") == spec["expected_category"], (
            "Failure category does not match hidden fixture"
        )
    if spec["scenario_id"] == "container-crash":
        assert any(
            t["name"] == "inspect_container" and t["result"].get("exit_code") == 42 for t in tools
        )
        assert any(
            t["name"] == "get_container_logs" and "application_crash" in str(t["result"])
            for t in tools
        )
        assert any(
            t["name"] == "get_recent_service_events"
            and any(e["action"] == "die" for e in t["result"].get("events", []))
            for t in tools
        )
    if spec["scenario_id"] == "memory-pressure":
        assert any(
            t["name"] == "get_container_metrics" and t["result"].get("memory_percent", 0) >= 60
            for t in tools
        )
    if spec["scenario_id"] in ("api-failure", "slow-response"):
        assert any(
            t["name"] == "query_prometheus"
            and t["result"].get("value") is not None
            and t["result"]["value"] > 0
            for t in tools
        )
    return {
        "category": diagnosis.get("category"),
        "category_correct": spec["expected_category"] is None
        or diagnosis.get("category") == spec["expected_category"],
        "validated_citations": len(set(citations)),
        "tool_calls": len(tools),
        "successful_tool_calls": len(evidence),
        "required_tools_present": True,
        "manual_review_required": "References and numeric observations are checked; truth of every free-text statement is not mechanically proven.",
    }


def run_scenario(http, scenario, live=False, mock=False):
    spec = json.loads((LAB / "fixtures" / f"{scenario}.json").read_text())
    report = {
        "scenario": scenario,
        "status": "FAIL",
        "started_at": time.time(),
        "mode": "live-model" if live else "mock-model" if mock else "deterministic-evidence",
        "configured_targets": {
            "detection_deadline_seconds": spec["detection_deadline_seconds"],
            "expected_verification": spec["expected_verification"],
        },
    }
    try:
        injection_time = time.time()
        injected = request(http, "POST", f"/lab/faults/{scenario}", json={})
        sid = injected["service_id"]
        observed_service = request(http, "GET", f"/services/{sid}")
        assert (
            observed_service["snapshot"]["labels"]["com.docker.compose.service"]
            == spec["expected_service"]
        )
        rows = wait_for(
            lambda: request(http, "GET", "/incidents"),
            lambda rows: any(
                i["service_id"] == sid
                and i["kind"] == spec["expected_signal"]
                and i["created_at"] >= injection_time
                for i in rows
            ),
            f"{scenario} detection",
            spec["detection_deadline_seconds"],
        )
        row = next(
            i
            for i in rows
            if i["service_id"] == sid
            and i["kind"] == spec["expected_signal"]
            and i["created_at"] >= injection_time
        )
        report.update(
            incident_id=row["id"],
            detection_latency_seconds=row["created_at"] - injection_time,
            incident_created_at=row["created_at"],
        )
        incident = wait_for(
            lambda: detail(http, row["id"]),
            lambda i: i["state"] in ("AWAITING_APPROVAL", "FAILED"),
            "completed investigation",
            180,
        )
        assert incident["state"] == "AWAITING_APPROVAL", (
            "Investigation did not produce an approvable action"
        )
        report["diagnosis"] = evaluate_diagnosis(incident, spec)
        assert incident["diagnosis"]["affected_service"] == observed_service["name"]
        report["detection"] = incident["detection"]
        report["evidence"] = incident["tools"]
        timeline = request(http, "GET", f"/incidents/{row['id']}/timeline")
        diagnosed = [e["at"] for e in timeline if e["kind"] == "investigation.diagnosed"]
        report["time_to_diagnosis_seconds"] = diagnosed[-1] - row["created_at"]
        usage = next(
            e["payload"].get("tokens_used", 0)
            for e in reversed(timeline)
            if e["kind"] == "investigation.diagnosed"
        )
        report["actual_investigation_mode"] = (
            "live-model" if usage else "mock-model" if mock else "deterministic-evidence"
        )
        if live:
            assert usage > 0, (
                "Live model reasoning was not verified; deterministic fallback is not live accuracy"
            )
        report["investigation_cost"] = {
            "tokens_used": usage,
            "tool_calls": len(incident["tools"]),
            "estimated_provider_cost_usd": 0 if not live else None,
            "cost_note": "No provider calls in deterministic/mock mode; live pricing estimate unavailable.",
        }
        actions = [a for a in incident["actions"] if a["status"] == "proposed"]
        assert len(actions) == 1 and actions[0]["kind"] == spec["expected_remediation"]
        action = actions[0]
        with httpx.Client(timeout=10, trust_env=False) as anonymous:
            denied = anonymous.post(
                str(http.base_url).rstrip("/") + f"/remediations/{action['id']}/approve",
                json={"action_digest": action["digest"]},
            )
        assert denied.status_code == 401, "Anonymous approval was not rejected"
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
        replay = http.post(
            f"/remediations/{action['id']}/approve", json={"action_digest": action["digest"]}
        )
        assert replay.status_code == 409, "Duplicate approval was accepted"
        final = wait_for(
            lambda: detail(http, row["id"]),
            lambda i: i["state"] in ("RESOLVED", "FAILED"),
            "sustained recovery verification",
            90,
        )
        report["verification"] = final["verification"]
        report["remediation"] = next(a for a in final["actions"] if a["id"] == action["id"])
        assert final["verification"]["result"] == spec["expected_verification"], (
            "Recovery classification did not match measured fault outcome"
        )
        assert (final["state"] == "RESOLVED") == (spec["expected_verification"] == "RECOVERED")
        if scenario in ("api-failure", "slow-response"):
            healthy = [s for s in final["verification"]["samples"] if s.get("healthy")]
            assert healthy and all(s["request_count"]["value"] >= 5 for s in healthy)
            assert all(s["prometheus"]["sample_at"] >= s["action_completed_at"] for s in healthy)
        if scenario == "recovery-verification":
            assert any(
                s.get("snapshot", {}).get("health") == "unhealthy"
                for s in final["verification"]["samples"]
            )
        audit = request(http, "GET", "/audit")
        assert any(
            a["operation"] == "remediation.approved"
            and a["resource_id"] == action["id"]
            and a["actor"] == "lab-test"
            for a in audit
        )
        report.update(
            status="PASS",
            final_state=final["state"],
            approval_enforced=True,
            duplicate_rejected=True,
            verification_correct=True,
            remediation_recovered=final["state"] == "RESOLVED",
        )
    except (AssertionError, RuntimeError, httpx.HTTPError, KeyError, StopIteration) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["completed_at"] = time.time()
        try:
            reset(http)
            report["reset_succeeded"] = True
        except (RuntimeError, httpx.HTTPError) as error:
            report.update(status="FAIL", reset_succeeded=False, reset_error=type(error).__name__)
    return report


def write_summary(reports, baseline, persisted):
    scored = [r for r in reports if r["scenario"] != "recovery-verification"]
    n = len(reports)
    summary = {
        "generated_at": time.time(),
        "mode": reports[0]["mode"],
        "configured_targets": TARGETS,
        "healthy_baselines": baseline,
        "incident_persistence_after_api_restart": persisted,
        "measurements": {
            "scenario_count": n,
            "passed": sum(r["status"] == "PASS" for r in reports),
            "detection_rate": sum("incident_id" in r for r in reports) / n,
            "root_cause_accuracy": sum(
                r.get("diagnosis", {}).get("category_correct", False) for r in scored
            )
            / len(scored)
            if scored
            else None,
            "false_positive_count": sum(b["false_positive_count"] for b in baseline),
            "remediation_recovery_rate": sum(r.get("remediation_recovered", False) for r in scored)
            / len(scored)
            if scored
            else None,
            "verification_accuracy": sum(r.get("verification_correct", False) for r in reports) / n,
        },
        "scenarios": [
            {k: v for k, v in r.items() if k not in ("evidence", "detection", "verification")}
            for r in reports
        ],
        "limitations": [
            "Deterministic evidence analysis is not live-model reasoning accuracy."
            if reports[0]["mode"] != "live-model"
            else "Live model conclusions require manual review.",
            "False-positive exposure is limited to the measured healthy baseline durations.",
            "Resource removal is verified by pulse lab down, independently of scenario reset.",
        ],
    }
    (REPORTS / "evaluation-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Incident lab evaluation",
        "",
        f"Mode: {summary['mode']}",
        "",
        "| Scenario | Result | Detection seconds | Verification |",
        "|---|---|---:|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r['scenario']} | {r['status']} | {r.get('detection_latency_seconds', 0):.2f} | {r.get('verification', {}).get('result', 'unrun')} |"
        )
    lines += [
        "",
        "Measured results:",
        "",
        "```json",
        json.dumps(summary["measurements"], indent=2),
        "```",
        "",
        f"Persistence after API restart: {persisted}",
        "",
        *summary["limitations"],
    ]
    (REPORTS / "evaluation-summary.md").write_text("\n".join(lines) + "\n")
    return summary


def evaluate(http, scenarios, live=False):
    REPORTS.mkdir(exist_ok=True)
    ready(http)
    configured = request(http, "GET", "/settings")
    if bool(configured["provider_configured"]) != live:
        raise RuntimeError(
            "Model mode does not match running lab configuration; deterministic runs require an empty model, live runs require an explicitly configured provider"
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
        "memory_threshold": 60,
        "memory_recovery_threshold": 40,
        "latency_threshold_ms": 1500,
        "latency_recovery_ms": 200,
        "error_rate_threshold": 0.2,
        "error_recovery_rate": 0.05,
        "http_min_requests": 5,
    }
    reports, baselines = [], []
    persisted = False
    try:
        request(http, "PATCH", "/settings", json=settings)
        reset(http)
        for scenario in scenarios:
            baseline = healthy_baseline(http)
            baselines.append(baseline)
            if baseline["false_positive_count"]:
                raise RuntimeError(
                    "Unexpected incidents during healthy baseline; evaluation stopped"
                )
            print(f"Evaluating {scenario} against real Docker and Prometheus.", flush=True)
            report = run_scenario(http, scenario, live, mock=configured["model"] == "mock/evidence")
            reports.append(report)
            (REPORTS / f"{scenario}.json").write_text(json.dumps(report, indent=2) + "\n")
            request(http, "POST", "/lab/evaluations", json={"scenario": scenario, "report": report})
            print(
                f"{scenario}: {report['status']} ({report.get('error', report.get('final_state'))})",
                flush=True,
            )
        if any(r.get("incident_id") for r in reports):
            before = [
                (r["incident_id"], detail(http, r["incident_id"])["state"])
                for r in reports
                if r.get("incident_id")
            ]
            compose("restart", "api")
            ready(http)
            persisted = all(detail(http, iid)["state"] == state for iid, state in before)
        summary = write_summary(reports, baselines, persisted)
        assert all(r["status"] == "PASS" for r in reports) and persisted, (
            "Evaluation has failed scenarios or persistence check"
        )
        print(json.dumps(summary["measurements"], indent=2))
    finally:
        request(http, "PATCH", "/settings", json=original)
        if reports:
            write_summary(reports, baselines, persisted)
