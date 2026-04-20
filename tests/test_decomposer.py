"""Tests for the task decomposer."""

import pytest
from orchestrator.models import Task, TaskStatus
from orchestrator.decomposer import decompose, _resolve_agent_type


class TestResolveAgentType:
    def test_rag_actions(self):
        assert _resolve_agent_type("query") == "rag"
        assert _resolve_agent_type("search") == "rag"
        assert _resolve_agent_type("context_lookup") == "rag"

    def test_code_actions(self):
        assert _resolve_agent_type("generate_code") == "code"
        assert _resolve_agent_type("refactor") == "code"
        assert _resolve_agent_type("review") == "code"

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError, match="No agent registered"):
            _resolve_agent_type("unknown_action")


class TestDecompose:
    def _make_task(self, steps: list[dict]) -> Task:
        return Task(tenant_id="t1", payload={"steps": steps})

    def test_single_step(self):
        task = self._make_task([{"action": "query", "params": {"text": "hello"}}])
        subtasks = decompose(task)
        assert len(subtasks) == 1
        assert subtasks[0].agent_type == "rag"
        assert subtasks[0].status == TaskStatus.PENDING
        assert subtasks[0].depends_on == []

    def test_multi_step_no_deps(self):
        task = self._make_task([
            {"action": "query", "params": {"text": "hello"}},
            {"action": "generate_code", "params": {"lang": "python"}},
        ])
        subtasks = decompose(task)
        assert len(subtasks) == 2
        assert subtasks[0].agent_type == "rag"
        assert subtasks[1].agent_type == "code"

    def test_multi_step_with_deps(self):
        task = self._make_task([
            {"action": "query", "params": {"text": "hello"}},
            {"action": "summarize", "params": {}, "depends_on_step": 0},
        ])
        subtasks = decompose(task)
        assert len(subtasks) == 2
        assert subtasks[1].depends_on == [subtasks[0].subtask_id]
        assert subtasks[1].status == TaskStatus.AWAITING_DEPS

    def test_forward_dependency_raises(self):
        task = self._make_task([
            {"action": "query", "params": {}, "depends_on_step": 1},
            {"action": "summarize", "params": {}},
        ])
        with pytest.raises(ValueError, match="hasn't been defined yet"):
            decompose(task)

    def test_unknown_action_raises(self):
        task = self._make_task([{"action": "fly_to_moon", "params": {}}])
        with pytest.raises(ValueError, match="No agent registered"):
            decompose(task)

    def test_empty_steps_raises(self):
        task = Task(tenant_id="t1", payload={})
        with pytest.raises(ValueError, match="missing 'steps'"):
            decompose(task)

    def test_task_transitions_to_decomposing(self):
        task = self._make_task([{"action": "query", "params": {}}])
        decompose(task)
        assert task.status == TaskStatus.DECOMPOSING
