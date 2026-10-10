"""Read-only reviews of recorded lab evidence; never authorize or execute actions."""

import json
import math
import time
import uuid
from pathlib import Path

from pydantic import ValidationError

from pulse.core.schemas import Settings
from pulse.lab.catalog import SCENARIOS

MODES = ("mock-model", "deterministic-evidence", "live-model")
VERDICTS = ("RECOVERED", "NOT_RECOVERED", "INCONCLUSIVE", "VERIFICATION_FAILED")
LATENCIES = ("detection_latency_seconds", "time_to_diagnosis_seconds")


def run_identity(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def number(value):
    try:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        )
    except OverflowError:
        return False


def valid_context(context):
    if (
        not isinstance(context, dict)
        or context.get("version") != 1
        or context.get("suite") not in ("standard", "telemetry-restoration")
    ):
        return False
    runtime = context.get("runtime")
    if not isinstance(runtime, dict) or not set(Settings.model_fields).issubset(runtime):
        return False
    try:
        Settings.model_validate(runtime, strict=True)
    except ValidationError:
        return False
    return True


def assessment(report, scenario=None):
    issues = []
    failed = report.get("status") == "FAIL"

    def issue(code, explanation, follow_up, failure=False):
        nonlocal failed
        failed |= failure
        issues.append({"code": code, "explanation": explanation, "follow_up": follow_up})

    if report.get("scenario") not in tuple(SCENARIOS) or (
        scenario is not None and report.get("scenario") != scenario
    ):
        issue(
            "scenario_identity",
            "The report's scenario identity is missing or contradicts its record.",
            "Inspect the original evaluation record; compare only the same authorized scenario.",
        )

    if failed:
        issue(
            "evaluation_failed",
            "The recorded evaluation failed.",
            "Inspect its retained report and incident evidence before another explicitly approved run.",
        )
    elif report.get("status") != "PASS":
        issue(
            "missing_status",
            "No completed PASS/FAIL evaluation status was recorded.",
            "Finish the evaluation and preserve its report, including failed checks.",
        )
    context = report.get("evaluation_context")
    if not valid_context(context):
        issue(
            "missing_context",
            "Evaluation settings or suite version are unavailable.",
            "Run the current evaluator to record comparable settings; preserve this historical report.",
        )
    if report.get("mode") not in MODES or report.get(
        "actual_investigation_mode", report.get("mode")
    ) != report.get("mode"):
        issue(
            "reasoning_mode",
            "Reasoning provenance is missing or contradicts the requested mode.",
            "Check provider configuration. Mock or deterministic results cannot establish live-model quality.",
        )
    if not run_identity(report.get("run_id")):
        issue(
            "missing_run",
            "No evaluation run identity was recorded.",
            "Run the current evaluator; do not infer a baseline from file names.",
        )
    started, completed = report.get("started_at"), report.get("completed_at")
    if (
        not number(started)
        or not number(completed)
        or completed < started
        or completed > time.time() + 30
    ):
        issue(
            "invalid_timestamps",
            "Evaluation timestamps are missing, reversed or in the future.",
            "Check the evaluator clock and record a completed, ordered run.",
        )
    for key in ("approval_enforced", "duplicate_rejected"):
        if report.get(key) is not True:
            issue(
                key,
                "Approval enforcement or replay rejection was not confirmed.",
                "Inspect the approval/audit checks; never replay an action to fill this evidence gap.",
                report.get(key) is False,
            )
    diagnosis = report.get("diagnosis") if isinstance(report.get("diagnosis"), dict) else {}
    if diagnosis.get("category_correct") is False:
        issue(
            "diagnosis_incorrect",
            "The diagnosis disagreed with the scenario fixture.",
            "Inspect cited tool results and add a regression for the incorrect diagnosis.",
            True,
        )
    elif (
        diagnosis.get("category_correct") is not True
        or diagnosis.get("required_tools_present") is not True
        or not number(diagnosis.get("successful_tool_calls"))
        or diagnosis["successful_tool_calls"] < 1
        or not number(diagnosis.get("validated_citations"))
        or diagnosis["validated_citations"] < 1
    ):
        issue(
            "diagnosis_evidence",
            "Required diagnosis tools or validated citations are missing.",
            "Restore scoped read-only tool evidence and rerun the diagnosis checks.",
        )
    verification = (
        report.get("verification") if isinstance(report.get("verification"), dict) else {}
    )
    outcome = verification.get("result")
    targets = (
        report.get("configured_targets")
        if isinstance(report.get("configured_targets"), dict)
        else {}
    )
    expected = targets.get("expected_verification")
    if expected not in VERDICTS or outcome not in VERDICTS:
        issue(
            "verification_missing",
            "An expected or observed verification verdict is unavailable.",
            "Record the scenario's expected outcome and completed verification evidence.",
        )
    elif outcome != expected or report.get("final_state") != (
        "RESOLVED" if outcome == "RECOVERED" else "FAILED"
    ):
        issue(
            "verification_mismatch",
            f"Observed {outcome}; expected {expected}, with a matching incident state.",
            "Inspect the verification samples. An expected ineffective remediation must remain NOT_RECOVERED.",
            True,
        )
    if (
        not verification.get("samples")
        or not verification.get("required_evidence")
        or not verification.get("reason")
    ):
        issue(
            "verification_evidence",
            "Supporting verification samples, requirements or explanation are missing.",
            "Restore required observations; do not treat an unsupported verdict as a passing evaluation.",
        )
    if report.get("scenario") == "telemetry-loss":
        initial = report.get("inconclusive_verification") or {}
        if (
            not isinstance(initial, dict)
            or initial.get("result") != "INCONCLUSIVE"
            or report.get("no_duplicate_incidents") is not True
            or report.get("mutation_execution_count") != 1
            or report.get("restart_preserved_deadline") is not True
        ):
            issue(
                "restoration_evidence",
                "Telemetry-loss, restart or restoration safety checks are incomplete.",
                "Run the selected-resource telemetry-loss scenario and inspect its retained initial verdict and audit history.",
            )
    elif report.get("verification_correct") is not True:
        issue(
            "verification_check",
            "The fixture verification check did not pass.",
            "Review the expected and observed outcomes before counting this scenario as successful.",
            report.get("verification_correct") is False,
        )
    for key in LATENCIES:
        if not number(report.get(key)):
            issue(
                key,
                "A required latency measurement is unavailable or invalid.",
                "Record measured detection and diagnosis timestamps; never substitute zero.",
            )
    deadline = targets.get("detection_deadline_seconds")
    if deadline is None or not number(deadline) or deadline <= 0:
        issue(
            "detection_target",
            "A configured detection deadline is unavailable.",
            "Record the scenario fixture's original detection deadline.",
        )
    elif (
        number(report.get("detection_latency_seconds"))
        and report["detection_latency_seconds"] > deadline
    ):
        issue(
            "detection_deadline",
            "Detection exceeded the configured scenario deadline.",
            "Inspect polling and evidence timing without relaxing the original detection deadline.",
            True,
        )
    baseline = report.get("healthy_baseline")
    if (
        not isinstance(baseline, dict)
        or not number(baseline.get("duration_seconds"))
        or baseline["duration_seconds"] < 14
        or not number(baseline.get("false_positive_count"))
    ):
        issue(
            "healthy_baseline",
            "Healthy baseline exposure or false-positive measurements are missing.",
            "Record at least fourteen seconds of healthy baseline exposure before injecting a fault.",
        )
    elif baseline["false_positive_count"] > 0:
        issue(
            "false_positive",
            "Unexpected incidents were observed during a healthy baseline.",
            "Inspect detection evidence and add a false-positive regression before repeating the lab.",
            True,
        )
    return {
        "status": "FAILED" if failed else "INSUFFICIENT_EVIDENCE" if issues else "PASS",
        "issues": issues,
    }


def compare(current, baseline, scenario=None):
    review = assessment(current, scenario)
    result = {
        **review,
        "comparison": "NO_BASELINE",
        "comparison_reason": "No earlier run is available.",
        "latency_changes": [],
    }
    if baseline is None:
        return result
    previous = assessment(baseline, scenario)
    comparable = (
        current.get("scenario") == baseline.get("scenario")
        and current.get("scenario") in tuple(SCENARIOS)
        and current.get("mode") in MODES
        and current.get("mode") == baseline.get("mode")
        and isinstance(current.get("evaluation_context"), dict)
        and current["evaluation_context"].get("version") == 1
        and current.get("evaluation_context") == baseline.get("evaluation_context")
        and current.get("configured_targets") == baseline.get("configured_targets")
        and run_identity(current.get("run_id"))
        and run_identity(baseline.get("run_id"))
        and current["run_id"] != baseline["run_id"]
        and number(current.get("started_at"))
        and number(baseline.get("completed_at"))
        and current["started_at"] > baseline["completed_at"]
    )
    if not comparable:
        result.update(
            comparison="INCOMPARABLE",
            comparison_reason="Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.",
        )
    elif "INSUFFICIENT_EVIDENCE" in (review["status"], previous["status"]):
        result.update(
            comparison="INCONCLUSIVE",
            comparison_reason="At least one run has incomplete evidence. Inspect the original reports before making a trend claim.",
        )
    elif review["status"] == "FAILED":
        result.update(
            comparison="REGRESSED" if previous["status"] == "PASS" else "PERSISTING_FAILURE",
            comparison_reason="The current evaluation failed; an observed failure remains visible even when other evidence is missing.",
        )
    elif previous["status"] == "FAILED":
        result.update(
            comparison="IMPROVED",
            comparison_reason="The earlier evaluation failed; the current compatible evaluation passed all evidence checks.",
        )
    else:
        result.update(
            comparison="STABLE",
            comparison_reason="Both compatible evaluations passed; no latency change exceeded the review threshold.",
        )
        for key in LATENCIES:
            before, after = baseline[key], current[key]
            delta = after - before
            # Review heuristic, not a statistical performance claim from two runs.
            threshold = max(1.0, before * 0.25)
            direction = (
                "SLOWER" if delta > threshold else "FASTER" if delta < -threshold else "STABLE"
            )
            result["latency_changes"].append(
                {
                    "metric": key,
                    "baseline_seconds": before,
                    "current_seconds": after,
                    "delta_seconds": delta,
                    "threshold_seconds": threshold,
                    "direction": direction,
                }
            )
        if any(c["direction"] == "SLOWER" for c in result["latency_changes"]):
            result.update(
                comparison="REGRESSED",
                comparison_reason="A latency increase exceeded max(1 second, 25% of baseline). Reproduce under the same settings before concluding a performance regression.",
            )
        elif any(c["direction"] == "FASTER" for c in result["latency_changes"]):
            result.update(
                comparison="IMPROVED",
                comparison_reason="A measured latency decrease exceeded the review threshold; repeat the run to establish whether it is reproducible.",
            )
    return result


def quality_review(records):
    rows = []
    for scenario in SCENARIOS:
        candidates = sorted(
            (r for r in records if r.get("scenario") == scenario),
            key=lambda r: (r["at"], r["id"]),
            reverse=True,
        )[:2]
        if not candidates:
            rows.append(
                {
                    "scenario": scenario,
                    "status": "NOT_RUN",
                    "comparison": "NO_BASELINE",
                    "comparison_reason": "No recorded evaluation is available.",
                    "issues": [],
                    "latency_changes": [],
                    "current": None,
                    "baseline": None,
                }
            )
            continue
        current = candidates[0]
        baseline = candidates[1] if len(candidates) > 1 else None
        result = compare(current["report"], baseline["report"] if baseline else None, scenario)
        refs = {}
        for name, record in (("current", current), ("baseline", baseline)):
            report = record["report"] if record else {}
            refs[name] = (
                {
                    "id": record["id"],
                    "at": record["at"],
                    "run_id": report.get("run_id") if run_identity(report.get("run_id")) else None,
                    "incident_id": report.get("incident_id")
                    if run_identity(report.get("incident_id"))
                    else None,
                    "mode": report.get("mode") if report.get("mode") in MODES else "unknown",
                    "verdict": report["verification"].get("result")
                    if isinstance(report.get("verification"), dict)
                    and report["verification"].get("result") in VERDICTS
                    else None,
                }
                if record
                else None
            )
        rows.append({"scenario": scenario, **result, **refs})
    failed = sum(r["status"] == "FAILED" for r in rows)
    regressed = sum(r["comparison"] == "REGRESSED" for r in rows)
    incomplete = sum(
        r["status"] in {"NOT_RUN", "INSUFFICIENT_EVIDENCE"}
        or r["comparison"] in {"NO_BASELINE", "INCOMPARABLE", "INCONCLUSIVE"}
        for r in rows
    )
    return {
        "generated_at": time.time(),
        "status": "ATTENTION_REQUIRED"
        if failed or regressed
        else "INSUFFICIENT_EVIDENCE"
        if incomplete
        else "NO_REGRESSIONS_OBSERVED",
        "summary": {
            "scenario_count": len(rows),
            "failed": failed,
            "regressed": regressed,
            "needs_evidence": incomplete,
        },
        "scenarios": rows,
        "limitations": [
            "Reviews describe recorded lab evaluations, not current service health or live-model accuracy.",
            "Missing scenarios or incompatible baselines prevent a complete-suite improvement claim.",
            "Latency thresholds are review heuristics; two runs do not prove a statistical performance change.",
            "Follow-up work is advisory. No settings, approvals or resources are modified.",
        ],
    }


def from_reports(directory: Path):
    records = []
    files = sorted(
        path
        for path in directory.rglob("*.json")
        if path.name
        not in {"summary.json", "evaluation-summary.json", "quality-review.json", "review.json"}
    )
    if len(files) > 1000:
        raise RuntimeError("Too many report files; select a smaller report directory")
    for path in files:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise RuntimeError("Formatted report exceeds the 4 MB input limit")
        try:
            report = json.loads(path.read_text())
        except (ValueError, UnicodeError) as error:
            raise RuntimeError(
                "Invalid JSON in report directory; inspect the report locally"
            ) from error
        if (
            not isinstance(report, dict)
            or not isinstance(report.get("scenario"), str)
            or report.get("scenario") not in SCENARIOS
        ):
            continue
        # Never reinterpret a copied report as a distinct baseline run.
        identity = report.get("run_id")
        if identity:
            existing = next(
                (
                    r
                    for r in records
                    if r["report"].get("run_id") == identity and r["scenario"] == report["scenario"]
                ),
                None,
            )
            if existing:
                if existing["report"] != report:
                    raise RuntimeError(
                        "Conflicting reports for the same run and scenario; inspect retained evidence"
                    )
                continue
        at = report.get("completed_at")
        receipt = report.get("evaluation_record")
        if (
            isinstance(receipt, dict)
            and run_identity(receipt.get("id"))
            and number(receipt.get("at"))
        ):
            at = receipt["at"]
        records.append(
            {
                "id": receipt["id"]
                if isinstance(receipt, dict) and run_identity(receipt.get("id"))
                else str(path.relative_to(directory)),
                "at": at if number(at) else path.stat().st_mtime,
                "scenario": report["scenario"],
                "report": report,
            }
        )
    return quality_review(records)


def markdown(review):
    lines = [
        "# Pulse quality review",
        "",
        f"Status: {review['status']}",
        "",
        "| Scenario | Evidence | Comparison |",
        "|---|---|---|",
    ]
    for row in review["scenarios"]:
        lines.append(f"| {row['scenario']} | {row['status']} | {row['comparison']} |")
    for row in review["scenarios"]:
        lines += ["", f"**{row['scenario']}**: {row['comparison_reason']}"]
        for issue in row["issues"]:
            lines.append(f"- {issue['explanation']} {issue['follow_up']}")
        for change in row["latency_changes"]:
            lines.append(
                f"- {change['metric']}: {change['baseline_seconds']:.2f}s → {change['current_seconds']:.2f}s ({change['direction']})."
            )
    lines += ["", *review["limitations"]]
    return "\n".join(lines) + "\n"
