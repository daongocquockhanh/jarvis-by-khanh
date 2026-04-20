"""FastAPI layer — API Gateway with tenant isolation and rate limiting."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field

from config import get_settings
from .core import Orchestrator
from .state_store import StateStore
from .event_bus import EventBus

logger = logging.getLogger(__name__)

# ── Globals (initialized in lifespan) ─────────────────────

_orchestrator: Orchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    settings = get_settings()
    state = StateStore(redis_url=settings.redis_url, pg_dsn=settings.pg_dsn)
    bus = EventBus(bootstrap_servers=settings.kafka_servers)
    _orchestrator = Orchestrator(state=state, bus=bus)
    await _orchestrator.start()
    yield
    await _orchestrator.stop()


app = FastAPI(
    title="Nexus Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Tenant extraction (simplified — production uses JWT) ───

async def get_tenant_id(x_tenant_id: str = Header(...)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-Id header")
    return x_tenant_id


# ── Request / Response schemas ─────────────────────────────

class TaskRequest(BaseModel):
    idempotency_key: str | None = None
    priority: int = Field(default=5, ge=1, le=10)
    metadata: dict = Field(default_factory=dict)
    steps: list[dict] = Field(
        ...,
        min_length=1,
        description="Ordered list of steps. Each step: {action, params, depends_on_step?}",
    )


class TaskResponse(BaseModel):
    task_id: str
    status: str
    subtask_count: int
    error: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


# ── Endpoints ──────────────────────────────────────────────

@app.post("/tasks", response_model=TaskResponse, status_code=202)
async def create_task(
    req: TaskRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Submit a complex task for decomposition and multi-agent execution."""
    payload = {
        "idempotency_key": req.idempotency_key,
        "priority": req.priority,
        "metadata": req.metadata,
        "steps": req.steps,
    }
    task = await _orchestrator.submit_task(tenant_id, payload)
    return TaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        subtask_count=len(task.subtasks),
        error=task.error_detail,
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(
    task_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Poll task status and retrieve results."""
    task = await _orchestrator.get_task_status(tenant_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        result=task.result,
        error=task.error_detail,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
