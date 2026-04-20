"""Agent Worker — base class for specialized agents consuming from the event bus.

Each agent type (RAG, Code, DataRouter, etc.) subclasses BaseAgentWorker
and implements `execute()`. The base class handles:
  - Kafka consumption from task.dispatch
  - Message filtering by agent_type
  - Result publishing to task.result
  - Heartbeat registration
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .event_bus import TOPIC_DISPATCH, TOPIC_RESULT
from .models import TaskStatus

logger = logging.getLogger(__name__)


class BaseAgentWorker(ABC):
    """Subclass this and implement `execute()` for each agent type."""

    agent_type: str = ""  # override in subclass

    def __init__(self, bootstrap_servers: str) -> None:
        self._servers = bootstrap_servers
        self._instance_id = f"{self.agent_type}-{uuid.uuid4().hex[:8]}"
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None
        self._running = False

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",
        )
        self._consumer = AIOKafkaConsumer(
            TOPIC_DISPATCH,
            bootstrap_servers=self._servers,
            group_id=f"agent-{self.agent_type}",
            value_deserializer=lambda v: json.loads(v.decode()),
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._producer.start()
        await self._consumer.start()
        self._running = True
        logger.info("Agent worker %s started", self._instance_id)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()

    async def run(self) -> None:
        """Main consume loop — filters messages by agent_type."""
        await self.start()
        try:
            async for msg in self._consumer:
                payload = msg.value
                if payload.get("agent_type") != self.agent_type:
                    await self._consumer.commit()
                    continue

                result = await self._safe_execute(payload)
                await self._publish_result(payload, result)
                await self._consumer.commit()
        finally:
            await self.stop()

    async def _safe_execute(self, payload: dict) -> dict:
        """Wrap execute() with error handling."""
        try:
            output = await self.execute(payload["input"])
            return {"status": TaskStatus.COMPLETED.value, "output": output}
        except Exception as exc:
            logger.exception("Agent %s failed on subtask %s",
                             self._instance_id, payload.get("subtask_id"))
            return {
                "status": TaskStatus.FAILED.value,
                "error": str(exc),
            }

    async def _publish_result(self, original: dict, result: dict) -> None:
        message = {
            "tenant_id": original["tenant_id"],
            "task_id": original["task_id"],
            "subtask_id": original["subtask_id"],
            **result,
        }
        await self._producer.send_and_wait(TOPIC_RESULT, value=message)

    @abstractmethod
    async def execute(self, input_payload: dict) -> dict:
        """Implement the agent's core logic. Return the output dict."""
        ...


# ── Example: RAG Agent ─────────────────────────────────────

class RAGAgentWorker(BaseAgentWorker):
    """Example agent that performs RAG queries against the vector store."""

    agent_type = "rag"

    async def execute(self, input_payload: dict) -> dict:
        query = input_payload.get("params", {}).get("text", "")
        # In production, call the retriever + LLM here
        # For now, placeholder demonstrating the interface
        from retriever import retrieve
        from agent import ask

        chunks = retrieve(query)
        answer = ask(query)  # uses existing RAG pipeline
        return {
            "answer": answer,
            "sources": [c["metadata"]["source"] for c in chunks],
        }
