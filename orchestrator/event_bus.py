"""Kafka-backed event bus for dispatching subtasks and consuming agent results."""

from __future__ import annotations

import json
import logging
from typing import Callable, Awaitable

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

logger = logging.getLogger(__name__)

# Topic constants
TOPIC_DISPATCH = "task.dispatch"
TOPIC_RESULT = "task.result"
TOPIC_DLQ = "task.dlq"


class EventBus:
    """Async Kafka wrapper — publish subtasks, consume agent results."""

    def __init__(self, bootstrap_servers: str, group_id: str = "orchestrator") -> None:
        self._servers = bootstrap_servers
        self._group_id = group_id
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            acks="all",                     # durability: wait for all ISR
            enable_idempotence=True,        # exactly-once semantics
            max_batch_size=65536,
            linger_ms=10,                   # micro-batch for throughput
        )
        await self._producer.start()
        logger.info("Kafka producer started")

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
        if self._consumer:
            await self._consumer.stop()

    async def dispatch_subtask(
        self, tenant_id: str, subtask_id: str, payload: dict
    ) -> None:
        """Publish a subtask to the dispatch topic, keyed by tenant for ordering."""
        message = {
            "tenant_id": tenant_id,
            "subtask_id": subtask_id,
            **payload,
        }
        await self._producer.send_and_wait(
            TOPIC_DISPATCH,
            value=message,
            key=tenant_id,  # partition by tenant — ordering guarantee per tenant
        )
        logger.debug("Dispatched subtask %s for tenant %s", subtask_id, tenant_id)

    async def send_to_dlq(self, original_message: dict, error: str) -> None:
        """Route a permanently failed message to the dead-letter queue."""
        dlq_message = {
            "original": original_message,
            "error": error,
        }
        await self._producer.send_and_wait(TOPIC_DLQ, value=dlq_message)
        logger.warning("Sent message to DLQ: %s", error)

    async def consume_results(
        self,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        """Blocking consume loop — runs until cancelled.

        Each message is committed only AFTER the handler succeeds.
        On handler failure, the message is sent to DLQ after exhausting retries.
        """
        self._consumer = AIOKafkaConsumer(
            TOPIC_RESULT,
            bootstrap_servers=self._servers,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode()),
            enable_auto_commit=False,       # manual commit for at-least-once
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        logger.info("Kafka consumer started on topic %s", TOPIC_RESULT)

        try:
            async for msg in self._consumer:
                try:
                    await handler(msg.value)
                    await self._consumer.commit()
                except Exception:
                    logger.exception(
                        "Failed to handle result message, routing to DLQ"
                    )
                    await self.send_to_dlq(
                        msg.value, "Handler exception after max retries"
                    )
                    await self._consumer.commit()
        finally:
            await self._consumer.stop()
