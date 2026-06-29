from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.domain.models import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def write(
        self,
        actor_teacher_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        child_id: int | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_teacher_id=actor_teacher_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            child_id=child_id,
            metadata_json=json.dumps(metadata or {}),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
