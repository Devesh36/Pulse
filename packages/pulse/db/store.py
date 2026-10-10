import time
from typing import cast

from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import sessionmaker

from pulse.core.schemas import TRANSITIONS, Settings, State
from pulse.db.models import Audit, Event, Incident, Setting


class Store:
    def __init__(self, url: str):
        args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=args, pool_pre_ping=True)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def settings(self) -> Settings:
        with self.session() as db:
            row = db.get(Setting, "runtime")
            return Settings.model_validate(row.value) if row else Settings()

    def event(self, kind: str, payload: dict, incident_id: str | None = None):
        with self.session.begin() as db:
            db.add(Event(kind=kind, payload=payload, incident_id=incident_id))

    def audit(self, operation: str, resource_id: str, details: dict, actor="operator"):
        with self.session.begin() as db:
            db.add(
                Audit(actor=actor, operation=operation, resource_id=resource_id, details=details)
            )

    def transition(self, incident_id: str, state: State, detail: dict | None = None):
        with self.session.begin() as db:
            incident = db.get(Incident, incident_id)
            if not incident:
                raise ValueError("Incident does not exist")
            old = State(incident.state)
            if state not in TRANSITIONS[old]:
                raise ValueError(f"Invalid transition: {old} → {state}")
            values = {"state": state.value, "updated_at": time.time()}
            if state in (State.RESOLVED, State.DISMISSED):
                values["active_key"] = None
            changed = db.execute(
                update(Incident)
                .where(Incident.id == incident_id, Incident.state == old.value)
                .values(**values)
            )
            if cast(CursorResult, changed).rowcount != 1:
                raise ValueError("Incident changed concurrently")
            db.add(
                Event(
                    incident_id=incident_id,
                    kind="incident.transition",
                    payload={"from": old.value, "to": state.value, **(detail or {})},
                )
            )

    def similar(self, service_id: str, kind: str, text: str = ""):
        with self.session() as db:
            query = select(Incident).where(Incident.service_id == service_id, Incident.kind == kind)
            if text and self.engine.dialect.name == "postgresql":
                from sqlalchemy import func

                query = query.where(
                    func.to_tsvector("english", Incident.title).op("@@")(
                        func.plainto_tsquery("english", text)
                    )
                )
            return db.scalars(query.order_by(Incident.created_at.desc()).limit(10)).all()


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
