"""Task Decomposer — breaks a complex payload into a DAG of subtasks."""

from __future__ import annotations

import logging
from .models import Task, Subtask, TaskStatus

logger = logging.getLogger(__name__)

# Registry of known agent types and what payload keys they handle
AGENT_ROUTING: dict[str, list[str]] = {
    "rag": ["query", "search", "context_lookup"],
    "code": ["generate_code", "refactor", "review"],
    "data_router": ["transform", "etl", "pipeline"],
    "summarizer": ["summarize", "digest", "compress"],
}


def _resolve_agent_type(action: str) -> str:
    """Map an action string to the agent type that handles it."""
    for agent_type, actions in AGENT_ROUTING.items():
        if action in actions:
            return agent_type
    raise ValueError(f"No agent registered for action: {action}")


def decompose(task: Task) -> list[Subtask]:
    """Decompose a task payload into ordered subtasks.

    Expected payload format:
    {
        "steps": [
            {
                "action": "query",
                "params": {"text": "..."},
                "depends_on_step": null | <int>   # index of a prior step
            },
            ...
        ]
    }

    Returns subtasks with dependency edges resolved to subtask IDs.
    """
    steps = task.payload.get("steps")
    if not steps:
        raise ValueError(f"Task {task.task_id} payload missing 'steps' field")

    task.transition(TaskStatus.DECOMPOSING)

    subtasks: list[Subtask] = []
    index_to_id: dict[int, str] = {}

    for idx, step in enumerate(steps):
        action = step["action"]
        agent_type = _resolve_agent_type(action)

        subtask = Subtask(
            task_id=task.task_id,
            tenant_id=task.tenant_id,
            agent_type=agent_type,
            sequence_order=idx,
            input_payload={
                "action": action,
                "params": step.get("params", {}),
            },
        )

        # Resolve dependency: step index -> subtask ID
        dep_step = step.get("depends_on_step")
        if dep_step is not None:
            if dep_step not in index_to_id:
                raise ValueError(
                    f"Step {idx} depends on step {dep_step} which hasn't been defined yet. "
                    f"Dependencies must reference earlier steps (DAG constraint)."
                )
            subtask.depends_on = [index_to_id[dep_step]]
            subtask.status = TaskStatus.AWAITING_DEPS

        index_to_id[idx] = subtask.subtask_id
        subtasks.append(subtask)

    logger.info(
        "Decomposed task %s into %d subtasks", task.task_id, len(subtasks)
    )
    return subtasks
