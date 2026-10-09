import time
import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Service(Base):
    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    container_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(256))
    monitored: Mapped[bool] = mapped_column(Boolean, default=False)
    remediation_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen: Mapped[float] = mapped_column(Float, default=time.time)


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), index=True)
    at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "incident_title_search", text("to_tsvector('english', title)"), postgresql_using="gin"
        ).ddl_if(dialect="postgresql"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    state: Mapped[str] = mapped_column(String(32), default="DETECTED", index=True)
    # Unique while active; NULL allows later incidents after cooldown.
    active_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    detection: Mapped[dict] = mapped_column(JSON, default=dict)
    diagnosis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True, index=True
    )
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    args: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[float] = mapped_column(Float)
    at: Mapped[float] = mapped_column(Float, default=time.time)


class Remediation(Base):
    __tablename__ = "remediations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    container_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float] = mapped_column(Float)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    at: Mapped[float] = mapped_column(Float, default=time.time)


class Audit(Base):
    __tablename__ = "audit_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(80))
    operation: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON)
    at: Mapped[float] = mapped_column(Float, default=time.time)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Checkpoint(Base):
    __tablename__ = "agent_checkpoints"
    thread_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(100), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checkpoint_type: Mapped[str] = mapped_column(String(80))
    checkpoint_blob: Mapped[str] = mapped_column(Text)
    metadata_type: Mapped[str] = mapped_column(String(80))
    metadata_blob: Mapped[str] = mapped_column(Text)


class CheckpointWrite(Base):
    __tablename__ = "agent_checkpoint_writes"
    thread_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(100), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(100))
    value_type: Mapped[str] = mapped_column(String(80))
    value_blob: Mapped[str] = mapped_column(Text)
