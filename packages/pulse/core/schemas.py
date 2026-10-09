from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class State(StrEnum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    DISMISSED = "DISMISSED"


TRANSITIONS = {
    State.DETECTED: {State.INVESTIGATING, State.DISMISSED},
    State.INVESTIGATING: {State.DIAGNOSED, State.FAILED},
    State.DIAGNOSED: {State.AWAITING_APPROVAL, State.DISMISSED, State.INVESTIGATING},
    State.AWAITING_APPROVAL: {State.REMEDIATING, State.DISMISSED, State.INVESTIGATING},
    State.REMEDIATING: {State.VERIFYING, State.FAILED},
    State.VERIFYING: {State.RESOLVED, State.FAILED},
    State.FAILED: {State.INVESTIGATING, State.DISMISSED},
    State.RESOLVED: set(),
    State.DISMISSED: set(),
}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interval_seconds: float = Field(default=10, ge=2, le=300)
    cpu_threshold: float = Field(default=85, ge=1, le=10000)
    memory_threshold: float = Field(default=85, ge=1, le=100)
    latency_threshold_ms: float = Field(default=800, ge=1, le=60000)
    error_rate_threshold: float = Field(default=0.2, ge=0.01, le=1)
    restart_threshold: int = Field(default=3, ge=1, le=50)
    window_seconds: int = Field(default=60, ge=2, le=3600)
    min_samples: int = Field(default=3, ge=1, le=100)
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)
    verification_seconds: float = Field(default=30, ge=2, le=600)
    recovery_grace_seconds: float = Field(default=15, ge=0, le=120)
    agent_max_iterations: int = Field(default=6, ge=1, le=15)
    agent_token_budget: int = Field(default=12000, ge=512, le=64000)
    remediation_disabled: bool = False


class ServicePermission(BaseModel):
    monitored: bool
    remediation_allowed: bool

    @model_validator(mode="after")
    def valid(self):
        if self.remediation_allowed and not self.monitored:
            raise ValueError("Monitoring must be enabled before remediation")
        return self


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{12,64}$")
    service_id: str | None = Field(default=None, max_length=64)
    since: int = Field(default=1800, ge=1, le=86400)
    limit: int = Field(default=100, ge=1, le=300)
    query: Literal["cpu", "memory", "latency", "error_rate"] = "latency"


TOOL_NAMES = [
    "list_containers",
    "inspect_container",
    "get_container_logs",
    "get_container_metrics",
    "get_container_health",
    "get_container_restart_history",
    "query_prometheus",
    "get_service_dependencies",
    "get_recent_service_events",
    "get_incident_history",
]


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal[
        "list_containers",
        "inspect_container",
        "get_container_logs",
        "get_container_metrics",
        "get_container_health",
        "get_container_restart_history",
        "query_prometheus",
        "get_service_dependencies",
        "get_recent_service_events",
        "get_incident_history",
    ]
    args: ToolArgs


class Finding(BaseModel):
    statement: str = Field(max_length=2000)
    classification: Literal["observation", "supported_hypothesis", "unverified_possibility"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class Diagnosis(BaseModel):
    summary: str = Field(max_length=4000)
    affected_service: str
    symptoms: list[str] = Field(max_length=20)
    timeline: list[str] = Field(max_length=30)
    root_causes: list[Finding] = Field(max_length=10)
    confidence: Literal["low", "medium", "high"]
    uncertainty: str
    next_steps: list[str] = Field(max_length=15)


class ActionProposal(BaseModel):
    kind: Literal["restart", "start", "collect_diagnostics", "configuration_recommendation"]
    reason: str = Field(min_length=1, max_length=2000)


class AgentDecision(BaseModel):
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=3)
    diagnosis: Diagnosis | None = None
    action: ActionProposal | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    service_id: str


class Login(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class Approval(BaseModel):
    action_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Dismissal(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class FinalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnosis: Diagnosis
    action: ActionProposal | None = None
