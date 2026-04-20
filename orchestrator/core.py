"""Orchestrator Core Loop — the central nervous system of the platform.

Responsibilities:
  1. Accept incoming task payloads (via API or direct call)
  2. Decompose tasks into subtask DAGs
  3. Dispatch ready subtasks to the event bus
  4. Consume agent results and advance the state machine
  5. Aggregate final results when all subtasks complete
"""

from __future__ import annotations

import asyncio
import logging

from .models import Task, Subtask, TaskStatus, InvalidTransitionError
from .state_store import StateStore
from .event_bus import EventBus
from .decomposer import decompose

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, state: StateStore, bus: EventBus) -> None:
        self._state = state
        self._bus = bus
        self._result_listener: asyncio.Task | None = None

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        await self._state.connect()
        await self._bus.start()
        self._result_listener = asyncio.create_task(
            self._bus.consume_results(self._handle_result)
        )
        logger.info("Orchestrator started")

    async def stop(self) -> None:
        if self._result_listener:
            self._result_listener.cancel()
            try:
                await self._result_listener
            except asyncio.CancelledError:
                pass
        await self._bus.stop()
        await self._state.close()
        logger.info("Orchestrator stopped")

    # ── Public API ─────────────────────────────────────────────

    async def submit_task(self, tenant_id: str, payload: dict) -> Task:
        """Entry point: accept a complex task, decompose, and dispatch."""
        task = Task(tenant_id=tenant_id, payload=payload)
        task.idempotency_key = payload.get("idempotency_key")
        task.priority = payload.get("priority", 5)
        task.metadata = payload.get("metadata", {})

        # 1. Persist the initial task
        await self._state.save_task(task)
        logger.info("Task %s submitted by tenant %s", task.task_id, tenant_id)

        # 2. Decompose into subtask DAG
        try:
            subtasks = decompose(task)
        except (ValueError, KeyError) as exc:
            task.transition(TaskStatus.FAILED)
            task.error_detail = str(exc)
            await self._state.save_task(task)
            logger.error("Decomposition failed for task %s: %s", task.task_id, exc)
            return task

        # 3. Persist all subtasks
        for sub in subtasks:
            await self._state.save_subtask(sub)
        task.subtasks = subtasks
        task.transition(TaskStatus.DISPATCHED)
        await self._state.save_task(task)

        # 4. Dispatch subtasks that have no pending dependencies
        await self._dispatch_ready(tenant_id, task.task_id)

        return task

    async def get_task_status(self, tenant_id: str, task_id: str) -> Task | None:
        return await self._state.get_task(tenant_id, task_id)

    # ── Internal: dispatch subtasks whose deps are met ─────────

    async def _dispatch_ready(self, tenant_id: str, task_id: str) -> None:
        ready = await self._state.get_pending_subtasks(tenant_id, task_id)
        if not ready:
            return

        # Update parent task to IN_PROGRESS on first dispatch
        task = await self._state.get_task(tenant_id, task_id)
        if task and task.status == TaskStatus.DISPATCHED:
            try:
                await self._state.update_task_status(
                    tenant_id, task_id, TaskStatus.IN_PROGRESS
                )
            except InvalidTransitionError:
                pass  # already transitioned by a concurrent dispatch

        for sub in ready:
            sub.status = TaskStatus.DISPATCHED
            await self._state.save_subtask(sub)
            await self._bus.dispatch_subtask(
                tenant_id=tenant_id,
                subtask_id=sub.subtask_id,
                payload={
                    "task_id": sub.task_id,
                    "agent_type": sub.agent_type,
                    "input": sub.input_payload,
                    "retry_count": sub.retry_count,
                },
            )
            logger.info(
                "Dispatched subtask %s (agent=%s) for task %s",
                sub.subtask_id, sub.agent_type, task_id,
            )

    # ── Internal: handle agent result messages ─────────────────

    async def _handle_result(self, message: dict) -> None:
        """Process a result published by an agent on task.result topic.

        Expected message format:
        {
            "tenant_id": "...",
            "task_id": "...",
            "subtask_id": "...",
            "status": "COMPLETED" | "FAILED",
            "output": { ... },
            "error": "..." (optional)
        }
        """
        tenant_id = message["tenant_id"]
        task_id = message["task_id"]
        subtask_id = message["subtask_id"]
        result_status = TaskStatus(message["status"])

        logger.info(
            "Received result for subtask %s: %s", subtask_id, result_status
        )

        # Update subtask state
        key = self._state._subtask_key(tenant_id, task_id, subtask_id)
        sub_data = await self._state._redis.hgetall(key)
        if not sub_data:
            logger.error("Subtask %s not found in state store", subtask_id)
            return

        sub = self._state._deserialize_subtask(sub_data)

        if result_status == TaskStatus.COMPLETED:
            sub.status = TaskStatus.COMPLETED
            sub.output_payload = message.get("output", {})
        elif result_status == TaskStatus.FAILED:
            if sub.retry_count < sub.max_retries:
                # Retry: re-dispatch the subtask
                sub.retry_count += 1
                sub.status = TaskStatus.PENDING
                await self._state.save_subtask(sub)
                logger.warning(
                    "Retrying subtask %s (attempt %d/%d)",
                    subtask_id, sub.retry_count, sub.max_retries,
                )
                await self._dispatch_ready(tenant_id, task_id)
                return
            else:
                sub.status = TaskStatus.FAILED
                sub.error_detail = message.get("error", "Unknown agent error")

        await self._state.save_subtask(sub)

        # Check if this unblocks downstream subtasks
        await self._dispatch_ready(tenant_id, task_id)

        # Check if parent task is complete
        await self._try_finalize_task(tenant_id, task_id)

    async def _try_finalize_task(self, tenant_id: str, task_id: str) -> None:
        """Check all subtasks — finalize the parent task if all are terminal."""
        pattern = f"tenant:{tenant_id}:task:{task_id}:sub:*"
        all_completed = True
        any_failed = False
        results: list[dict] = []

        async for key in self._state._redis.scan_iter(match=pattern):
            data = await self._state._redis.hgetall(key)
            status = TaskStatus(data["status"])

            if status == TaskStatus.COMPLETED:
                output = data.get("output_payload")
                if output:
                    import json
                    results.append(json.loads(output))
            elif status == TaskStatus.FAILED:
                any_failed = True
            else:
                all_completed = False
                break  # still in progress

        if not all_completed:
            return

        task = await self._state.get_task(tenant_id, task_id)
        if task is None:
            return

        if any_failed:
            new_status = TaskStatus.PARTIALLY_FAILED if results else TaskStatus.FAILED
        else:
            new_status = TaskStatus.COMPLETED

        try:
            task.transition(new_status)
        except InvalidTransitionError:
            return  # already finalized

        task.result = {"subtask_results": results}
        await self._state.save_task(task)
        logger.info("Task %s finalized with status %s", task_id, new_status)
