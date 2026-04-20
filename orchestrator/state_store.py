"""State management — Redis for hot state, PostgreSQL for durable persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

import redis.asyncio as redis
import asyncpg

from .models import Task, Subtask, TaskStatus

logger = logging.getLogger(__name__)


class StateStore:
    """Dual-layer state: Redis (fast reads/writes) + Postgres (durability)."""

    def __init__(self, redis_url: str, pg_dsn: str) -> None:
        self._redis_url = redis_url
        self._pg_dsn = pg_dsn
        self._redis: redis.Redis | None = None
        self._pg_pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._redis = redis.from_url(self._redis_url, decode_responses=True)
        self._pg_pool = await asyncpg.create_pool(self._pg_dsn, min_size=5, max_size=20)
        logger.info("StateStore connected to Redis and PostgreSQL")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
        if self._pg_pool:
            await self._pg_pool.close()

    # ── Redis key helpers ──────────────────────────────────────

    @staticmethod
    def _task_key(tenant_id: str, task_id: str) -> str:
        return f"tenant:{tenant_id}:task:{task_id}"

    @staticmethod
    def _subtask_key(tenant_id: str, task_id: str, subtask_id: str) -> str:
        return f"tenant:{tenant_id}:task:{task_id}:sub:{subtask_id}"

    # ── Task state operations ──────────────────────────────────

    async def save_task(self, task: Task) -> None:
        key = self._task_key(task.tenant_id, task.task_id)
        data = self._serialize_task(task)

        pipe = self._redis.pipeline()
        pipe.hset(key, mapping=data)
        pipe.expire(key, task.payload.get("ttl_seconds", 3600))
        await pipe.execute()

        # Durable write to Postgres
        await self._pg_pool.execute(
            """
            INSERT INTO tasks (task_id, tenant_id, idempotency_key, status, priority,
                               payload, result, metadata, error_detail, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (task_id) DO UPDATE SET
                status = EXCLUDED.status,
                result = EXCLUDED.result,
                error_detail = EXCLUDED.error_detail,
                updated_at = EXCLUDED.updated_at
            """,
            task.task_id, task.tenant_id, task.idempotency_key,
            task.status.value, task.priority,
            json.dumps(task.payload), json.dumps(task.result) if task.result else None,
            json.dumps(task.metadata), task.error_detail,
            task.created_at, task.updated_at,
        )

    async def get_task(self, tenant_id: str, task_id: str) -> Task | None:
        key = self._task_key(tenant_id, task_id)
        data = await self._redis.hgetall(key)
        if data:
            return self._deserialize_task(data)

        # Fallback to Postgres if evicted from Redis
        row = await self._pg_pool.fetchrow(
            "SELECT * FROM tasks WHERE task_id = $1 AND tenant_id = $2",
            task_id, tenant_id,
        )
        if row:
            task = Task(
                task_id=str(row["task_id"]),
                tenant_id=str(row["tenant_id"]),
                status=TaskStatus(row["status"]),
                priority=row["priority"],
                payload=json.loads(row["payload"]),
                result=json.loads(row["result"]) if row["result"] else None,
            )
            # Re-hydrate into Redis
            await self.save_task(task)
            return task
        return None

    async def update_task_status(
        self, tenant_id: str, task_id: str, new_status: TaskStatus
    ) -> Task:
        task = await self.get_task(tenant_id, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found for tenant {tenant_id}")
        task.transition(new_status)
        await self.save_task(task)
        await self._write_audit(tenant_id, task_id, None, "STATUS_CHANGE", new_status.value)
        return task

    # ── Subtask operations ─────────────────────────────────────

    async def save_subtask(self, subtask: Subtask) -> None:
        key = self._subtask_key(subtask.tenant_id, subtask.task_id, subtask.subtask_id)
        data = {
            "subtask_id": subtask.subtask_id,
            "task_id": subtask.task_id,
            "tenant_id": subtask.tenant_id,
            "agent_type": subtask.agent_type,
            "sequence_order": str(subtask.sequence_order),
            "depends_on": json.dumps(subtask.depends_on),
            "status": subtask.status.value,
            "input_payload": json.dumps(subtask.input_payload),
            "output_payload": json.dumps(subtask.output_payload) if subtask.output_payload else "",
            "retry_count": str(subtask.retry_count),
            "max_retries": str(subtask.max_retries),
        }
        await self._redis.hset(key, mapping=data)

    async def get_pending_subtasks(self, tenant_id: str, task_id: str) -> list[Subtask]:
        """Return subtasks whose dependencies are all COMPLETED."""
        pattern = f"tenant:{tenant_id}:task:{task_id}:sub:*"
        subtasks: list[Subtask] = []
        async for key in self._redis.scan_iter(match=pattern):
            data = await self._redis.hgetall(key)
            if data.get("status") != TaskStatus.PENDING.value:
                continue
            deps = json.loads(data.get("depends_on", "[]"))
            if await self._all_deps_completed(tenant_id, task_id, deps):
                subtasks.append(self._deserialize_subtask(data))
        return subtasks

    async def _all_deps_completed(
        self, tenant_id: str, task_id: str, dep_ids: list[str]
    ) -> bool:
        for dep_id in dep_ids:
            key = self._subtask_key(tenant_id, task_id, dep_id)
            status = await self._redis.hget(key, "status")
            if status != TaskStatus.COMPLETED.value:
                return False
        return True

    # ── Audit log ──────────────────────────────────────────────

    async def _write_audit(
        self,
        tenant_id: str,
        task_id: str,
        subtask_id: str | None,
        event_type: str,
        detail: str,
    ) -> None:
        await self._pg_pool.execute(
            """
            INSERT INTO audit_log (tenant_id, task_id, subtask_id, event_type, detail)
            VALUES ($1, $2, $3, $4, $5)
            """,
            tenant_id, task_id, subtask_id, event_type, json.dumps({"info": detail}),
        )

    # ── Serialization helpers ──────────────────────────────────

    @staticmethod
    def _serialize_task(task: Task) -> dict[str, str]:
        return {
            "task_id": task.task_id,
            "tenant_id": task.tenant_id,
            "status": task.status.value,
            "priority": str(task.priority),
            "payload": json.dumps(task.payload),
            "result": json.dumps(task.result) if task.result else "",
            "error_detail": task.error_detail or "",
        }

    @staticmethod
    def _deserialize_task(data: dict[str, str]) -> Task:
        return Task(
            task_id=data["task_id"],
            tenant_id=data["tenant_id"],
            status=TaskStatus(data["status"]),
            priority=int(data.get("priority", 5)),
            payload=json.loads(data.get("payload", "{}")),
            result=json.loads(data["result"]) if data.get("result") else None,
            error_detail=data.get("error_detail") or None,
        )

    @staticmethod
    def _deserialize_subtask(data: dict[str, str]) -> Subtask:
        return Subtask(
            subtask_id=data["subtask_id"],
            task_id=data["task_id"],
            tenant_id=data["tenant_id"],
            agent_type=data["agent_type"],
            sequence_order=int(data.get("sequence_order", 0)),
            depends_on=json.loads(data.get("depends_on", "[]")),
            status=TaskStatus(data["status"]),
            input_payload=json.loads(data.get("input_payload", "{}")),
            output_payload=json.loads(data["output_payload"]) if data.get("output_payload") else None,
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
        )
