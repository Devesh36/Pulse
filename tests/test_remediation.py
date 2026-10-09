import asyncio
import time

import pytest
from pulse.core.remediation import PolicyError, authorize
from pulse.core.schemas import ActionProposal, State
from pulse.db.models import Audit, Incident, Remediation, Service
from sqlalchemy import select


def proposed(runtime, incident, service, kind="start"):
    for state in [State.INVESTIGATING, State.DIAGNOSED]:
        runtime.store.transition(incident.id, state)
    action = runtime.remediator.propose(
        incident, service, ActionProposal(kind=kind, reason="Reviewed test recovery")
    )
    runtime.store.transition(incident.id, State.AWAITING_APPROVAL)
    runtime.adapter.snapshot.update(status="exited", exit_code=42)
    return action


@pytest.mark.parametrize(
    "condition",
    ["disabled", "permissions", "production", "expired", "digest", "identity", "running"],
)
def test_policy_denial(condition, runtime, service, incident):
    action = proposed(runtime, incident, service)
    settings = runtime.store.settings()
    snapshot = dict(runtime.adapter.snapshot)
    if condition == "disabled":
        settings.remediation_disabled = True
    if condition == "permissions":
        service.remediation_allowed = False
    if condition == "production":
        snapshot["labels"] = {**snapshot["labels"], "pulse.environment": "production"}
    if condition == "expired":
        action.expires_at = time.time() - 10
    if condition == "digest":
        action.reason = "tampered"
    if condition == "identity":
        snapshot["container_id"] = "b" * 64
    if condition == "running":
        snapshot["status"] = "running"
    with pytest.raises(PolicyError):
        authorize(action, service, settings, snapshot)


async def test_execution_without_approval_rejected(runtime, service, incident):
    action = proposed(runtime, incident, service)
    await runtime.remediator.execute(action.id)
    assert runtime.adapter.mutations == []
    with runtime.store.session() as db:
        assert db.get(Remediation, action.id).status == "proposed"


async def test_duplicate_approval_and_execution_prevented(runtime, service, incident):
    action = proposed(runtime, incident, service)
    first, second = await asyncio.gather(
        runtime.remediator.claim(action.id, action.digest),
        runtime.remediator.claim(action.id, action.digest),
        return_exceptions=True,
    )
    assert sum(isinstance(x, PolicyError) for x in (first, second)) == 1
    await runtime.remediator.execute(action.id)
    assert len(runtime.adapter.mutations) == 1
    with pytest.raises(PolicyError):
        await runtime.remediator.claim(action.id, action.digest)
    await runtime.remediator.execute(action.id)
    assert len(runtime.adapter.mutations) == 1
    with runtime.store.session() as db:
        assert db.get(Incident, incident.id).state == "RESOLVED"
        assert db.get(Incident, incident.id).verification["outcome"] == "confirmed"
        assert db.scalars(select(Audit).where(Audit.operation == "remediation.approved")).one()


async def test_failed_recovery_not_resolved(runtime, service, incident):
    action = proposed(runtime, incident, service)
    runtime.adapter.recover = False
    await runtime.remediator.claim(action.id, action.digest)
    await runtime.remediator.execute(action.id)
    with runtime.store.session() as db:
        row = db.get(Incident, incident.id)
        assert row.state == "FAILED" and row.verification["outcome"] == "failed"


async def test_missing_metrics_inconclusive(runtime, service, incident):
    action = proposed(runtime, incident, service)
    runtime.adapter.measurement = {"available": False}
    await runtime.remediator.claim(action.id, action.digest)
    await runtime.remediator.execute(action.id)
    with runtime.store.session() as db:
        assert db.get(Incident, incident.id).verification["outcome"] == "inconclusive"


async def test_permission_revoked_after_approval(runtime, service, incident):
    action = proposed(runtime, incident, service)
    await runtime.remediator.claim(action.id, action.digest)
    with runtime.store.session.begin() as db:
        db.get(Service, service.id).remediation_allowed = False
    await runtime.remediator.execute(action.id)
    assert runtime.adapter.mutations == []


async def test_interrupted_mutation_never_replayed(runtime, service, incident):
    action = proposed(runtime, incident, service)
    await runtime.remediator.claim(action.id, action.digest)
    await runtime.start()
    assert runtime.adapter.mutations == []
    with runtime.store.session() as db:
        assert db.get(Incident, incident.id).state == "FAILED"
        assert db.get(Remediation, action.id).status == "interrupted"
    await runtime.stop()
