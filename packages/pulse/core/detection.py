import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pulse.core.schemas import Settings
from pulse.db.models import Event, Incident

TERMINAL = {"RESOLVED", "DISMISSED"}


def evaluate(samples: list[dict], settings: Settings) -> list[tuple[str, str]]:
    """CPU is Docker percent: one fully used core = 100%, may exceed 100%."""
    now = time.time()
    samples = [
        s
        for s in samples
        if "observed_at" not in s
        or -5 <= now - s["observed_at"] <= settings.telemetry_max_age_seconds
    ]
    if not samples:
        return []
    latest = samples[-1]
    result = []
    status = latest.get("status")
    if status == "exited" and (
        latest.get("exit_code", 0) != 0
        or latest.get("oom_killed")
        or any(s.get("status") == "running" for s in samples[:-1])
    ):
        result.append(("stopped", "Container unexpectedly stopped"))
    if (
        status == "restarting"
        or latest.get("restart_count", 0) - min(s.get("restart_count", 0) for s in samples)
        >= settings.restart_threshold
    ):
        result.append(("restarting", "Container repeatedly restarting"))
    if latest.get("health") == "unhealthy":
        result.append(("unhealthy", "Container health check failing"))
    valid = samples[-settings.min_samples :]
    for key, threshold, kind, title in [
        ("cpu_percent", settings.cpu_threshold, "cpu", "Excessive CPU utilization"),
        ("memory_percent", settings.memory_threshold, "memory", "Excessive memory utilization"),
    ]:
        if len(valid) >= settings.min_samples and all(
            s.get("available") and s.get(key, 0) >= threshold for s in valid
        ):
            result.append((kind, title))
    # Prometheus values are rates / histogram quantiles over a genuine rolling window.
    for key, threshold, kind, title in [
        ("latency_ms", settings.latency_threshold_ms, "latency", "Elevated API latency"),
        ("error_rate", settings.error_rate_threshold, "errors", "Elevated HTTP error rate"),
    ]:
        observed = samples[-settings.min_samples :]
        if len(observed) >= settings.min_samples and all(
            isinstance(s.get(key), (float, int))
            and s[key] >= threshold
            and (s.get("request_count", settings.http_min_requests) or 0)
            >= settings.http_min_requests
            for s in observed
        ):
            result.append((kind, title))
    return result


def detect(store, service, samples, settings, now=None):
    now = now or time.time()
    ids = []
    for kind, title in evaluate(samples, settings):
        key = f"{service.id}:{kind}"
        with store.session() as db:
            active = db.scalar(select(Incident.id).where(Incident.active_key == key))
            recent = db.scalar(
                select(Incident)
                .where(Incident.service_id == service.id, Incident.kind == kind)
                .order_by(Incident.created_at.desc())
                .limit(1)
            )
            if active or (recent and now - recent.updated_at < settings.cooldown_seconds):
                continue
            row = Incident(
                service_id=service.id,
                kind=kind,
                title=f"{service.name}: {title}",
                active_key=key,
                severity="critical"
                if kind in ("stopped", "unhealthy", "restarting")
                else "warning",
                detection={"sample": samples[-1], "thresholds": settings.model_dump()},
            )
            db.add(row)
            try:
                db.flush()
                db.add(
                    Event(
                        incident_id=row.id,
                        kind="incident.detected",
                        payload={"title": row.title, "kind": kind},
                    )
                )
                db.commit()
                ids.append(row.id)
            except IntegrityError:
                db.rollback()
    return ids
