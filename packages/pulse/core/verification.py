"""Durable verification policy: unknown evidence is never a healthy observation."""

import math
import time
from enum import StrEnum
from typing import TypeGuard

from pulse.core.schemas import Settings


class VerificationOutcome(StrEnum):
    RECOVERED = "RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"
    INCONCLUSIVE = "INCONCLUSIVE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


def classify_recovery(confirmed: bool, observations: list[dict]) -> VerificationOutcome:
    if (
        confirmed
        and observations
        and observations[-1].get("healthy") is True
        and not (
            observations[-1].get("missing_evidence")
            or observations[-1].get("error")
            or observations[-1].get("contradictions")
        )
    ):
        return VerificationOutcome.RECOVERED
    # Unknown observations do not erase a trustworthy continuing failure. A later
    # complete healthy observation supersedes earlier transient failures.
    for sample in reversed(observations):
        if sample.get("error") == "PolicyError":
            return VerificationOutcome.VERIFICATION_FAILED
        if sample.get("failures") and not sample.get("contradictions"):
            return VerificationOutcome.NOT_RECOVERED
        if sample.get("healthy"):
            return VerificationOutcome.INCONCLUSIVE
        if sample.get("healthy") is False and not (
            sample.get("missing_evidence") or sample.get("error") or sample.get("contradictions")
        ):
            return VerificationOutcome.NOT_RECOVERED
    return VerificationOutcome.INCONCLUSIVE


def finite(value: object) -> TypeGuard[float | int]:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def new_progress(kind, baseline, settings: Settings, probe: bool, now=None):
    now = time.time() if now is None else now
    started = baseline.get("action_completed_at")
    required = ["docker_state", "docker_metrics"]
    if kind in ("latency", "errors"):
        required += ["prometheus", "request_count"]
    if probe:
        required.append("http_health")
    duration = settings.verification_seconds + settings.recovery_grace_seconds
    if kind in ("latency", "errors"):
        duration += settings.window_seconds
    return {
        "version": 2,
        "outcome": "running",
        "result": None,
        "reason": "Collecting fresh evidence; recovery has not been confirmed.",
        "started_at": started if finite(started) else now,
        "deadline_at": (started if finite(started) else now) + duration,
        "updated_at": now,
        "required_evidence": required,
        "policy": settings.model_dump(),
        "baseline": baseline,
        "source_watermarks": {},
        "stable_since": None,
        "stable_samples": 0,
        "stable_source_starts": {},
        "required_stable_seconds": settings.verification_seconds,
        "max_gap_seconds": settings.verification_max_gap_seconds
        or (2 * min(settings.interval_seconds, settings.verification_seconds / 2) + 1),
        "sample_count": 0,
        "samples": [],
        "last_decisive": None,
        "condition_evidence": {},
    }


def assess_observation(progress, kind, container_id, received, now=None):
    now = time.time() if now is None else now
    settings = Settings.model_validate(progress["policy"])
    sample = {
        "at": now,
        "required_evidence": progress["required_evidence"],
        "received_evidence": received,
        "rejected_evidence": {},
        "accepted_timestamps": {},
        "failures": [],
        "contradictions": [],
        "missing_evidence": False,
    }
    accepted = {}
    completed = progress["baseline"].get("action_completed_at")
    for name in progress["required_evidence"]:
        item = received.get(name)
        reason = None
        if not isinstance(item, dict) or not item:
            reason = "missing"
        elif item.get("error"):
            reason = "tool_failed:" + str(item["error"])
        elif item.get("available") is False:
            reason = "unavailable"
        else:
            stamp = item.get("sample_at" if name in ("prometheus", "request_count") else "at")
            if not finite(stamp):
                reason = "missing_timestamp"
            elif stamp > now + 0.05:
                reason = "future_timestamp"
            elif now - stamp > settings.telemetry_max_age_seconds:
                reason = "stale"
            elif not finite(completed) or stamp < max(completed, progress["started_at"]):
                reason = "not_post_action"
            elif stamp <= progress["source_watermarks"].get(name, -1):
                reason = (
                    "duplicate" if stamp == progress["source_watermarks"][name] else "out_of_order"
                )
            elif (
                name in ("docker_state", "docker_metrics")
                and item.get("container_id") != container_id
            ):
                reason = "wrong_resource"
            elif name in ("prometheus", "request_count") and (
                item.get("service") != progress.get("service_name")
                or item.get("metric")
                != (
                    "request_count"
                    if name == "request_count"
                    else "latency"
                    if kind == "latency"
                    else "error_rate"
                )
            ):
                reason = "wrong_metric_or_service"
            elif name in ("prometheus", "request_count") and (
                not finite(item.get("value"))
                or not finite(item.get("window_started_at"))
                or item["window_started_at"] < completed
            ):
                reason = "missing_value_or_pre_action_window"
            elif name == "request_count" and item["value"] < settings.http_min_requests:
                reason = "insufficient_requests"
            elif name == "docker_state" and (
                item.get("status")
                not in ("running", "exited", "created", "restarting", "paused", "dead")
                or item.get("health") not in ("healthy", "unhealthy", "starting", "none")
                or not finite(item.get("restart_count"))
            ):
                reason = "incomplete_state"
            elif name == "docker_metrics" and not all(
                finite(item.get(key)) for key in ("cpu_percent", "memory_percent")
            ):
                reason = "incomplete_metrics"
            elif name == "http_health" and not finite(item.get("status")):
                reason = "missing_http_status"
            if not reason:
                accepted[name] = item
                sample["accepted_timestamps"][name] = stamp
                previous_stamp = progress["source_watermarks"].get(name)
                if (
                    previous_stamp is not None
                    and stamp - previous_stamp > progress["max_gap_seconds"]
                ):
                    sample["rejected_evidence"][name] = "source_telemetry_gap"
                progress["source_watermarks"][name] = stamp
        if reason:
            sample["rejected_evidence"][name] = reason
    state = accepted.get("docker_state")
    probe = accepted.get("http_health")
    metrics = accepted.get("docker_metrics")
    if state:
        if state["status"] != "running":
            sample["failures"].append("container_not_running")
        if state["health"] == "unhealthy":
            sample["failures"].append("docker_health_unhealthy")
        if state["health"] == "starting":
            sample["rejected_evidence"]["docker_health"] = "health_not_ready"
        baseline = progress["baseline"]
        if state["restart_count"] > baseline.get("restart_count", 0) or (
            baseline.get("started_at") and state.get("started_at") != baseline["started_at"]
        ):
            sample["failures"].append("container_restarted")
        if (
            probe
            and state["health"] in ("healthy", "unhealthy")
            and ((state["health"] == "healthy") != (200 <= probe["status"] < 400))
        ):
            sample["contradictions"].append("docker_health_disagrees_with_http_health")
        if metrics and state["status"] != "running":
            sample["contradictions"].append("running_metrics_disagree_with_docker_state")
    if probe and not 200 <= probe["status"] < 400:
        sample["failures"].append("http_health_failed")
    if metrics and kind in ("cpu", "memory"):
        key, threshold = (
            ("cpu_percent", settings.cpu_threshold)
            if kind == "cpu"
            else ("memory_percent", settings.memory_recovery_threshold)
        )
        if metrics[key] >= threshold:
            sample["failures"].append(key + "_above_recovery_threshold")
    if kind in ("latency", "errors") and "prometheus" in accepted and "request_count" in accepted:
        metric = accepted["prometheus"]
        count = accepted["request_count"]
        if metric["sample_at"] != count["sample_at"]:
            sample["contradictions"].append("metric_and_request_count_source_times_disagree")
        elif metric["value"] >= (
            settings.latency_recovery_ms if kind == "latency" else settings.error_recovery_rate
        ):
            sample["failures"].append("incident_metric_above_recovery_threshold")
    previous = progress.get("updated_at")
    if progress["sample_count"] and now - previous > progress["max_gap_seconds"]:
        sample["rejected_evidence"]["continuity"] = "telemetry_gap"
    if now > progress["deadline_at"]:
        sample["rejected_evidence"]["deadline"] = "observation_after_deadline"
    sample["missing_evidence"] = bool(sample["rejected_evidence"] or sample["contradictions"])
    sample["healthy"] = not sample["missing_evidence"] and not sample["failures"]
    conditions = progress.setdefault("condition_evidence", {})
    disputed = {
        "docker_health_disagrees_with_http_health": (
            "docker_health_unhealthy",
            "http_health_failed",
        ),
        "running_metrics_disagree_with_docker_state": ("container_not_running",),
        "metric_and_request_count_source_times_disagree": (
            "incident_metric_above_recovery_threshold",
        ),
    }
    for contradiction in sample["contradictions"]:
        for condition in disputed.get(contradiction, ()):
            conditions.pop(condition, None)

    def remember(condition, failing, source):
        stamp = sample["accepted_timestamps"].get(source)
        if stamp is not None and stamp <= progress["deadline_at"]:
            conditions[condition] = {"failing": bool(failing), "at": stamp, "source": source}

    if state:
        if "running_metrics_disagree_with_docker_state" not in sample["contradictions"]:
            remember("container_not_running", state["status"] != "running", "docker_state")
        if (
            state["health"] != "starting"
            and "docker_health_disagrees_with_http_health" not in sample["contradictions"]
        ):
            remember("docker_health_unhealthy", state["health"] == "unhealthy", "docker_state")
        remember("container_restarted", "container_restarted" in sample["failures"], "docker_state")
    if probe and "docker_health_disagrees_with_http_health" not in sample["contradictions"]:
        remember("http_health_failed", "http_health_failed" in sample["failures"], "http_health")
    if metrics and kind in ("cpu", "memory"):
        condition = (
            "cpu_percent" if kind == "cpu" else "memory_percent"
        ) + "_above_recovery_threshold"
        remember(condition, condition in sample["failures"], "docker_metrics")
    if (
        "prometheus" in accepted
        and "request_count" in accepted
        and "metric_and_request_count_source_times_disagree" not in sample["contradictions"]
    ):
        remember(
            "incident_metric_above_recovery_threshold",
            "incident_metric_above_recovery_threshold" in sample["failures"],
            "prometheus",
        )
    sample["condition_evidence"] = {key: dict(value) for key, value in conditions.items()}
    if sample["healthy"]:
        progress["reason"] = (
            "Fresh ordered evidence received; waiting for the complete stable recovery window."
        )
    elif sample["missing_evidence"]:
        issues = [f"{key}: {value}" for key, value in sample["rejected_evidence"].items()] + sample[
            "contradictions"
        ]
        progress["reason"] = (
            "Healthy window reset because evidence is incomplete: "
            + "; ".join(issues)
            + ". Restore reliable telemetry."
        )
    else:
        progress["reason"] = "Observed recovery conditions still failing: " + ", ".join(
            sample["failures"]
        )
    # Compatibility fields retained for existing reports and consumers.
    sample.update(snapshot=received.get("docker_state"), metrics=received.get("docker_metrics"))
    for key in ("prometheus", "request_count"):
        if key in received:
            sample[key] = received[key]
    sample["action_completed_at"] = completed
    if probe:
        sample["http_status"] = probe["status"]
    if sample["healthy"]:
        if progress["stable_since"] is None:
            progress["stable_source_starts"] = dict(sample["accepted_timestamps"])
        progress["stable_since"] = progress["stable_since"] or now
        progress["stable_samples"] += 1
        progress["last_decisive"] = sample
    else:
        progress["stable_since"], progress["stable_samples"] = None, 0
        progress["stable_source_starts"] = {}
        if sample["failures"] and not sample["contradictions"]:
            progress["last_decisive"] = sample
    progress["sample_count"] += 1
    progress["updated_at"] = now
    progress["samples"] = (progress["samples"] + [sample])[-300:]
    progress["samples_truncated"] = progress["sample_count"] > 300
    return sample


def verdict(progress, now=None):
    now = time.time() if now is None else now
    confirmed = bool(
        progress["stable_since"] is not None
        and now - progress["stable_since"] >= progress["required_stable_seconds"]
        and progress["stable_samples"] >= 2
        and now - progress["updated_at"] <= progress["max_gap_seconds"]
        and all(
            progress["source_watermarks"].get(name, 0)
            - progress.get("stable_source_starts", {}).get(name, float("inf"))
            >= progress["required_stable_seconds"]
            for name in progress["required_evidence"]
        )
    )
    decisive = [progress["last_decisive"]] if progress.get("last_decisive") else []
    code = classify_recovery(confirmed, decisive + progress["samples"])
    failing = []
    if (
        not confirmed
        and code != VerificationOutcome.VERIFICATION_FAILED
        and "condition_evidence" in progress
    ):
        max_age = progress["policy"]["telemetry_max_age_seconds"]
        failing = [
            name
            for name, evidence in progress["condition_evidence"].items()
            if evidence["failing"] and 0 <= now - evidence["at"] <= max_age
        ]
        code = VerificationOutcome.NOT_RECOVERED if failing else VerificationOutcome.INCONCLUSIVE
    recent = progress["samples"][-1] if progress["samples"] else {}
    if code == VerificationOutcome.RECOVERED:
        reason = "All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window."
    elif code == VerificationOutcome.NOT_RECOVERED:
        reason = (
            "Observed continuing failure: "
            + ", ".join(
                failing
                if "condition_evidence" in progress
                else (progress.get("last_decisive") or recent).get(
                    "failures", ["recovery condition failed"]
                )
            )
            + ". Inspect the evidence before proposing another action."
        )
    elif code == VerificationOutcome.VERIFICATION_FAILED:
        reason = "Verification policy failed. Correct the allowlisted probe configuration and inspect the evidence."
    else:
        issues = {**recent.get("rejected_evidence", {})}
        if recent.get("contradictions"):
            issues["contradictions"] = ", ".join(recent["contradictions"])
        reason = (
            "Recovery is inconclusive: "
            + (
                "; ".join(f"{key}: {value}" for key, value in issues.items())
                or "insufficient uninterrupted fresh observations before the deadline"
            )
            + ". Restore reliable telemetry and request read-only re-verification; do not replay the remediation."
        )
    return code, reason
