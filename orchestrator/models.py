"""Domain models for the orchestration platform."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    DECOMPOSING = "DECOMPOSING"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_DEPS = "AWAITING_DEPS"
    COMPLETED = "COMPLETED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid state transitions — enforced by the state machine
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.DECOMPOSING, TaskStatus.CANCELLED},
    TaskStatus.DECOMPOSING: {TaskStatus.DISPATCHED, TaskStatus.FAILED},
    TaskStatus.DISPATCHED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {
        TaskStatus.COMPLETED,
        TaskStatus.PARTIALLY_FAILED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.AWAITING_DEPS: {TaskStatus.DISPATCHED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.PARTIALLY_FAILED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class Subtask:
    subtask_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    tenant_id: str = ""
    agent_type: str = ""
    sequence_order: int = 0
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    input_payload: dict = field(default_factory=dict)
    output_payload: dict | None = None
    error_detail: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    idempotency_key: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    payload: dict = field(default_factory=dict)
    result: dict | None = None
    metadata: dict = field(default_factory=dict)
    error_detail: str | None = None
    subtasks: list[Subtask] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def transition(self, new_status: TaskStatus) -> None:
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition task {self.task_id} "
                f"from {self.status} to {new_status}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)


class InvalidTransitionError(Exception):
    pass
