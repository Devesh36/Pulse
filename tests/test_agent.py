import pytest
from pulse.agents.checkpoints import DatabaseSaver
from pulse.agents.investigator import Investigator
from pulse.core.schemas import AgentDecision, Diagnosis, Finding, ToolArgs, ToolCall
from pulse.db.models import Checkpoint, Incident, ToolExecution
from sqlalchemy import func, select


async def test_evidence_mode_workflow(runtime, service, incident):
    result = await runtime.investigate(incident.id)
    assert result["diagnosis"]["affected_service"] == service.name
    assert result["diagnosis"]["confidence"] == "low"
    assert "No LLM configured" in result["diagnosis"]["uncertainty"]
    assert len(result["evidence"]) == 4
    assert any(f["evidence_ids"] for f in result["diagnosis"]["root_causes"])
    with runtime.store.session() as db:
        assert db.scalar(select(func.count()).select_from(Checkpoint)) > 0
        assert db.get(Incident, incident.id).diagnosis
    # A new checkpointer instance retrieves the persisted LangGraph state.
    saver = DatabaseSaver(runtime.store)
    cp = await saver.aget_tuple({"configurable": {"thread_id": incident.id}})
    assert cp.checkpoint["channel_values"]["diagnosis"]["affected_service"] == service.name
    result2 = await runtime.investigator.run(incident, service, resume=True)
    assert result2["diagnosis"] == result["diagnosis"]
    with runtime.store.session() as db:
        assert db.scalar(select(func.count()).select_from(ToolExecution)) == 4


class AdaptiveModel:
    def __init__(self):
        self.calls = 0

    async def decide(self, state):
        self.calls += 1
        if self.calls == 1:
            return AgentDecision(
                tool_calls=[ToolCall(name="get_incident_history", args=ToolArgs())]
            ), 100
        last = state["evidence"][-1]
        return AgentDecision(
            diagnosis=Diagnosis(
                summary="Observed service status",
                affected_service="forged-service",
                symptoms=["Healthy"],
                timeline=[],
                root_causes=[
                    Finding(
                        statement="History retrieved",
                        classification="observation",
                        evidence_ids=[last["id"]],
                    ),
                    Finding(
                        statement="Unsupported cause",
                        classification="supported_hypothesis",
                        evidence_ids=["invented"],
                    ),
                ],
                confidence="medium",
                uncertainty="Cause unknown",
                next_steps=["Review history"],
            )
        ), 100


async def test_model_adapts_tools_and_validates_evidence(runtime, config, service, incident):
    config.llm_model = "test/model"
    model = AdaptiveModel()
    investigator = Investigator(runtime.store, runtime.tools, config, model)
    result = await investigator.run(incident, service)
    assert model.calls == 2 and len(result["evidence"]) == 5 and result["tokens_used"] == 200
    assert result["diagnosis"]["affected_service"] == service.name
    assert result["diagnosis"]["root_causes"][1]["classification"] == "unverified_possibility"
    assert result["diagnosis"]["root_causes"][1]["evidence_ids"] == []


class FailingModel:
    async def decide(self, state):
        raise TimeoutError("provider timeout")


async def test_provider_failure_preserves_evidence(runtime, config, service, incident):
    config.llm_model = "test/model"
    investigator = Investigator(runtime.store, runtime.tools, config, FailingModel())
    result = await investigator.run(incident, service)
    assert "LLM unavailable" in result["diagnosis"]["uncertainty"]
    assert len(result["evidence"]) == 4


async def test_iteration_budget_stops_tool_loop(runtime, config, service, incident):
    config.llm_model = "test/model"

    class LoopingModel:
        async def decide(self, state):
            return AgentDecision(
                tool_calls=[ToolCall(name="get_container_health", args=ToolArgs())]
            ), 1

    investigator = Investigator(runtime.store, runtime.tools, config, LoopingModel())
    result = await investigator.run(incident, service)
    assert result["iteration"] == runtime.store.settings().agent_max_iterations
    assert "iteration budget reached" in result["diagnosis"]["uncertainty"]


async def test_provider_function_calling_and_budget(config, monkeypatch):
    import json
    from types import SimpleNamespace

    import litellm
    from pulse.agents.investigator import Model

    config.llm_model = "openai/test"
    monkeypatch.setattr(litellm, "token_counter", lambda **kwargs: 100)
    captured = {}

    async def complete(**kwargs):
        captured.update(kwargs)
        message = SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    function=SimpleNamespace(
                        name="get_container_health",
                        arguments=json.dumps({"container_id": "a" * 64}),
                    )
                )
            ],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=500)
        )

    monkeypatch.setattr(litellm, "acompletion", complete)
    state = {
        "service_name": "test",
        "container_id": "a" * 64,
        "kind": "stopped",
        "question": "",
        "evidence": [],
        "limitations": [],
        "tokens_used": 0,
        "token_budget": 2000,
    }
    decision, used = await Model(config).decide(state)
    assert decision.tool_calls[0].name == "get_container_health" and used == 500
    assert len(captured["tools"]) == 11 and captured["num_retries"] == 0
    assert captured["max_tokens"] + 456 <= 2000
    state["token_budget"] = 512
    captured.clear()
    with pytest.raises(ValueError, match="budget exhausted"):
        await Model(config).decide(state)
    assert not captured


async def test_startup_health_grace_requires_sustained_window(runtime, service, incident):
    from pulse.core.schemas import ActionProposal, State
    from pulse.db.models import Setting

    for state in [State.INVESTIGATING, State.DIAGNOSED]:
        runtime.store.transition(incident.id, state)
    action = runtime.remediator.propose(
        incident,
        service,
        ActionProposal(kind="start", reason="Recover a stopped development service"),
    )
    runtime.store.transition(incident.id, State.AWAITING_APPROVAL)
    runtime.adapter.snapshot.update(status="exited", exit_code=42)
    settings = runtime.store.settings().model_copy(update={"recovery_grace_seconds": 2})
    with runtime.store.session.begin() as db:
        db.merge(Setting(key="runtime", value=settings.model_dump()))
    original = runtime.adapter.inspect
    calls = 0

    async def starting(cid):
        nonlocal calls
        calls += 1
        value = await original(cid)
        if calls == 3:  # approval, execution revalidation, then first verification observation
            value["health"] = "starting"
        return value

    runtime.adapter.inspect = starting
    await runtime.remediator.claim(action.id, action.digest)
    await runtime.remediator.execute(action.id)
    with runtime.store.session() as db:
        row = db.get(Incident, incident.id)
        assert row.state == "RESOLVED"
        assert row.verification["observation_seconds"] >= 2
