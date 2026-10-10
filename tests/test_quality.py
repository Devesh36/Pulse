"""Synthetic report regressions, distinct from the real lab validation."""

import json
import time
import uuid
from copy import deepcopy
from io import StringIO

import pytest
from fastapi.testclient import TestClient
from pulse.core.schemas import Settings
from pulse.db.store import Store
from pulse.lab import cli, evaluate
from pulse.lab.catalog import SCENARIOS
from pulse.lab.quality import assessment, compare, from_reports, markdown, quality_review
from pulse.repl import PulseRepl

from apps.api.main import create_app


def report(**updates):
    now = time.time()
    row = {
        "scenario": "container-crash",
        "status": "PASS",
        "mode": "mock-model",
        "actual_investigation_mode": "mock-model",
        "run_id": str(uuid.uuid4()),
        "evaluation_context": {
            "version": 1,
            "suite": "standard",
            "runtime": Settings(interval_seconds=2).model_dump(),
        },
        "started_at": now - 10,
        "completed_at": now - 1,
        "approval_enforced": True,
        "duplicate_rejected": True,
        "diagnosis": {
            "category_correct": True,
            "required_tools_present": True,
            "successful_tool_calls": 5,
            "validated_citations": 2,
        },
        "configured_targets": {
            "expected_verification": "RECOVERED",
            "detection_deadline_seconds": 30,
        },
        "verification": {
            "result": "RECOVERED",
            "samples": [{"healthy": True}],
            "required_evidence": ["docker_state"],
            "reason": "Synthetic report fixture",
        },
        "verification_correct": True,
        "final_state": "RESOLVED",
        "detection_latency_seconds": 4,
        "time_to_diagnosis_seconds": 2,
        "healthy_baseline": {"duration_seconds": 14, "false_positive_count": 0},
    }
    row.update(updates)
    return row


def pair():
    previous = report(started_at=time.time() - 100, completed_at=time.time() - 90)
    return report(), previous


def record(data, at=1):
    return {"id": str(uuid.uuid4()), "at": at, "scenario": data["scenario"], "report": data}


@pytest.mark.parametrize(
    "key",
    [
        "evaluation_context",
        "run_id",
        "healthy_baseline",
        "approval_enforced",
        "duplicate_rejected",
        "diagnosis",
        "verification",
        "configured_targets",
        "detection_latency_seconds",
        "completed_at",
    ],
)
def test_missing_evidence_never_counts_as_pass(key):
    data = report()
    data.pop(key)
    assert assessment(data)["status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), 10**1000, "4", []])
def test_invalid_latency_is_not_zero_or_healthy(value):
    assert assessment(report(detection_latency_seconds=value))["status"] == "INSUFFICIENT_EVIDENCE"


def test_failed_incompatible_run_cannot_be_hidden_by_inconclusive():
    current, previous = pair()
    current.update(status="FAIL", verification={}, evaluation_context=None)
    review = quality_review([record(previous), record(current, 2)])
    assert review["status"] == "ATTENTION_REQUIRED"
    row = next(r for r in review["scenarios"] if r["scenario"] == "container-crash")
    assert row["status"] == "FAILED" and row["comparison"] == "INCOMPARABLE"
    assert row["issues"][0]["code"] == "evaluation_failed"


def test_expected_ineffective_remediation_is_a_passing_test():
    data = report(scenario="recovery-verification", final_state="FAILED")
    data["verification"]["result"] = "NOT_RECOVERED"
    data["configured_targets"]["expected_verification"] = "NOT_RECOVERED"
    assert assessment(data)["status"] == "PASS"
    data["verification"]["result"] = "INCONCLUSIVE"
    assert assessment(data)["status"] == "FAILED"


@pytest.mark.parametrize(
    "field", ["mode", "evaluation_context", "configured_targets", "run_id", "started_at"]
)
def test_incompatible_or_replayed_reports_are_not_improvements(field):
    current, previous = pair()
    if field == "mode":
        current[field] = "live-model"
    elif field == "evaluation_context":
        current[field]["runtime"]["interval_seconds"] = 5
    elif field == "configured_targets":
        current[field]["detection_deadline_seconds"] = 60
    elif field == "run_id":
        current[field] = previous[field]
    else:
        current[field] = previous["started_at"] - 1
    assert compare(current, previous)["comparison"] == "INCOMPARABLE"


@pytest.mark.parametrize(
    ("latency", "expected"), [(4.5, "STABLE"), (6, "REGRESSED"), (2, "IMPROVED")]
)
def test_measured_latency_review_threshold(latency, expected):
    current, previous = pair()
    current["detection_latency_seconds"] = latency
    assert compare(current, previous)["comparison"] == expected


def test_correctness_regression_and_subsequent_fix():
    current, previous = pair()
    current["diagnosis"]["category_correct"] = False
    assert compare(current, previous)["comparison"] == "REGRESSED"
    fixed = report(started_at=time.time(), completed_at=time.time() + 1)
    assert compare(fixed, current)["comparison"] == "IMPROVED"


def test_baseline_gap_does_not_establish_improvement():
    current, previous = pair()
    previous.pop("diagnosis")
    assert compare(current, previous)["comparison"] == "INCONCLUSIVE"
    review = quality_review([record(current)])
    assert review["status"] == "INSUFFICIENT_EVIDENCE"
    assert review["summary"]["needs_evidence"] == len(SCENARIOS)


@pytest.mark.parametrize(
    "field",
    ["mode", "verification", "diagnosis", "evaluation_context", "configured_targets", "run_id"],
)
def test_malformed_report_types_cannot_crash_or_pass(field):
    data = report(**{field: ["malformed"]})
    assert assessment(data)["status"] == "INSUFFICIENT_EVIDENCE"


def test_false_positive_and_detection_deadline_are_failures():
    data = report(detection_latency_seconds=31)
    assert assessment(data)["status"] == "FAILED"
    data = report(healthy_baseline={"duration_seconds": 14, "false_positive_count": 1})
    assert assessment(data)["status"] == "FAILED"


def test_telemetry_restoration_requires_initial_verdict_and_safety_checks():
    data = report(scenario="telemetry-loss")
    assert assessment(data)["status"] == "INSUFFICIENT_EVIDENCE"
    data.update(
        inconclusive_verification={"result": "INCONCLUSIVE"},
        no_duplicate_incidents=True,
        mutation_execution_count=1,
        restart_preserved_deadline=True,
    )
    assert assessment(data)["status"] == "PASS"


def test_offline_read_is_deduplicated_redacted_and_nonmutating(tmp_path, monkeypatch, capsys):
    data = report(error="token=must-not-leak")
    path = tmp_path / "crash.json"
    path.write_text(json.dumps(data))
    (tmp_path / "copied.json").write_text(json.dumps(data))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(
        cli, "credentials", lambda: pytest.fail("Offline review requested credentials")
    )
    assert (
        cli.main(["lab", "quality", "--reports-dir", str(tmp_path), "--format", "json", "--check"])
        == 2
    )
    assert "must-not-leak" not in capsys.readouterr().out
    review = from_reports(tmp_path)
    assert review["scenarios"][1]["baseline"] is None
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    path.write_text(json.dumps(report(status="FAIL")))
    assert cli.main(["lab", "quality", "--reports-dir", str(tmp_path), "--fail-on-regression"]) == 2


def test_repl_quality_never_starts_the_lab(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LAB", tmp_path)
    monkeypatch.setattr(
        cli, "compose", lambda *a, **k: pytest.fail("Review tried to modify Docker")
    )
    output = StringIO()
    repl = PulseRepl(stdout=output)
    assert repl.precmd("7") == "quality"
    repl.do_quality("")
    assert "INSUFFICIENT_EVIDENCE" in output.getvalue()
    assert not (tmp_path / ".env").exists()


def test_quality_api_is_authenticated_persistent_and_read_only(config, store, runtime):
    current, previous = pair()
    config.lab_enabled = True
    headers = {"Authorization": f"Bearer {config.admin_token}"}
    with TestClient(create_app(config, store, runtime)) as http:
        assert http.get("/api/v1/lab/quality").status_code == 401
        for data in (previous, current):
            data["error"] = "token=must-not-leak"
            assert (
                http.post(
                    "/api/v1/lab/evaluations",
                    headers=headers,
                    json={"scenario": "container-crash", "report": data},
                ).status_code
                == 200
            )
        first = http.get("/api/v1/lab/quality", headers=headers).json()
        assert first["scenarios"][1]["comparison"] == "STABLE"
        assert "must-not-leak" not in json.dumps(first)
        audits = http.get("/api/v1/audit", headers=headers).json()
        http.get("/api/v1/lab/quality", headers=headers)
        assert http.get("/api/v1/audit", headers=headers).json() == audits
    reopened = Store(config.database_url)
    try:
        from pulse.core.runtime import Runtime

        restarted = Runtime(reopened, config, runtime.adapter)
        with TestClient(create_app(config, reopened, restarted)) as http:
            second = http.get("/api/v1/lab/quality", headers=headers).json()
        assert first["scenarios"] == second["scenarios"]
        assert not runtime.adapter.mutations
    finally:
        reopened.engine.dispose()


def test_archive_retains_previous_runs_and_failed_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "REPORTS", tmp_path)
    (tmp_path / "evaluation-summary.json").write_text("preserved")
    monkeypatch.setattr(evaluate, "ready", lambda http: None)
    monkeypatch.setattr(evaluate, "reset", lambda http: None)
    monkeypatch.setattr(
        evaluate,
        "healthy_baseline",
        lambda http: {"started_at": time.time(), "duration_seconds": 14, "false_positive_count": 1},
    )
    recorded = []

    def request(http, method, path, **kwargs):
        if path == "/settings" and method == "GET":
            return {"provider_configured": False, "model": "mock/evidence", "runtime": {}}
        if path == "/lab/evaluations":
            recorded.append(deepcopy(kwargs["json"]))
            return {"id": str(uuid.uuid4()), "at": time.time()}
        return {}

    monkeypatch.setattr(evaluate, "request", request)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="Unexpected incidents"):
            evaluate.evaluate(None, ["container-crash"])
    assert (tmp_path / "evaluation-summary.json").read_text() == "preserved"
    assert len(list(tmp_path.glob("run-*/container-crash.json"))) == 2
    assert len({r["report"]["run_id"] for r in recorded}) == 2
    assert all(r["report"]["status"] == "FAIL" for r in recorded)
    assert (
        quality_review([record(r["report"], index) for index, r in enumerate(recorded)])["status"]
        == "ATTENTION_REQUIRED"
    )
    assert from_reports(tmp_path)["status"] == "ATTENTION_REQUIRED"
    (tmp_path / "malformed.json").write_text("invalid")
    with pytest.raises(RuntimeError, match="Invalid JSON"):
        from_reports(tmp_path)


def test_markdown_table_and_issue_followups():
    review = quality_review([record(report(status="FAIL"))])
    text = markdown(review)
    assert text.count("| container-crash |") == 1
    assert text.index("| slow-response |") < text.index("**telemetry-loss**")
    assert "Inspect its retained report" in text


def test_complete_compatible_suite_can_pass_strict_gate(tmp_path, capsys):
    records = []
    for scenario in SCENARIOS:
        current, previous = pair()
        for index, data in enumerate((previous, current)):
            data["scenario"] = scenario
            if scenario == "recovery-verification":
                data["verification"]["result"] = "NOT_RECOVERED"
                data["configured_targets"]["expected_verification"] = "NOT_RECOVERED"
                data["final_state"] = "FAILED"
            elif scenario == "telemetry-loss":
                data.update(
                    inconclusive_verification={"result": "INCONCLUSIVE"},
                    no_duplicate_incidents=True,
                    mutation_execution_count=1,
                    restart_preserved_deadline=True,
                )
            records.append(record(data, index))
            (tmp_path / f"{scenario}-{index}.json").write_text(json.dumps(data))
    assert quality_review(records)["status"] == "NO_REGRESSIONS_OBSERVED"
    assert cli.main(["lab", "quality", "--reports-dir", str(tmp_path), "--check"]) == 0
    assert "NO_REGRESSIONS_OBSERVED" in capsys.readouterr().out


def test_conflicting_copies_block_offline_trend_claim(tmp_path):
    data = report()
    (tmp_path / "original.json").write_text(json.dumps(data))
    data["status"] = "FAIL"
    (tmp_path / "copy.json").write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="Conflicting reports"):
        from_reports(tmp_path)


def test_partial_or_invalid_settings_are_not_comparable_evidence():
    data = report()
    data["evaluation_context"]["runtime"] = {"interval_seconds": 2}
    assert assessment(data)["status"] == "INSUFFICIENT_EVIDENCE"
    data = report()
    data["evaluation_context"]["runtime"]["interval_seconds"] = -1
    assert assessment(data)["status"] == "INSUFFICIENT_EVIDENCE"


def test_wrong_scenario_in_persisted_record_cannot_pass():
    data = report()
    stored = record(data)
    stored["scenario"] = "api-failure"
    result = quality_review([stored])
    row = next(row for row in result["scenarios"] if row["scenario"] == "api-failure")
    assert row["status"] == "INSUFFICIENT_EVIDENCE"
    assert row["issues"][0]["code"] == "scenario_identity"


def test_busy_scenario_cannot_hide_other_scenario_history(config, store, runtime):
    from pulse.db.models import LabEvaluation

    with store.session.begin() as db:
        db.add(LabEvaluation(scenario="api-failure", report=report(scenario="api-failure"), at=1))
        for at in range(2, 80):
            db.add(LabEvaluation(scenario="container-crash", report=report(), at=at))
    with TestClient(create_app(config, store, runtime)) as http:
        review = http.get(
            "/api/v1/lab/quality", headers={"Authorization": f"Bearer {config.admin_token}"}
        ).json()
    row = next(r for r in review["scenarios"] if r["scenario"] == "api-failure")
    assert row["current"] is not None and row["current"]["at"] == 1


def test_receipted_archive_matches_database_review_order_and_references(tmp_path, monkeypatch):
    data, previous = pair()
    rows = [record(previous, 20), record(data, 10)]

    def request(http, method, path, **kwargs):
        return rows[1]

    monkeypatch.setattr(evaluate, "request", request)
    evaluate.record_report(None, tmp_path, data)
    previous["evaluation_record"] = {"id": rows[0]["id"], "at": 20}
    (tmp_path / "older.json").write_text(json.dumps(previous))
    from_database = quality_review(rows)
    offline = from_reports(tmp_path)
    assert from_database["scenarios"] == offline["scenarios"]
    row = next(r for r in offline["scenarios"] if r["scenario"] == "container-crash")
    assert row["comparison"] == "INCOMPARABLE"  # Recording replay does not imply improvement.


def test_pretty_report_larger_than_compact_api_limit_is_readable(tmp_path):
    data = report()
    data["verification"]["samples"] = [{"healthy": True, "at": 1} for _ in range(10000)]
    assert len(json.dumps(data)) < 500000
    path = tmp_path / "crash.json"
    path.write_text(json.dumps(data, indent=2))
    assert path.stat().st_size > 500000
    row = next(r for r in from_reports(tmp_path)["scenarios"] if r["scenario"] == "container-crash")
    assert row["status"] == "PASS"
    data["legacy_extra"] = "x" * (4 * 1024 * 1024)
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="4 MB input"):
        from_reports(tmp_path)


def test_telemetry_evaluator_records_completion_even_when_injection_fails(monkeypatch):
    from pulse.lab import telemetry_loss

    def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic injection unavailable")

    monkeypatch.setattr(telemetry_loss, "request", unavailable)
    data = telemetry_loss.run_loss(None, native=True)
    assert data["status"] == "FAIL"
    assert data["completed_at"] >= data["started_at"]
