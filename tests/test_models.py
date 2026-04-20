"""Tests for domain models — state machine transitions."""

import pytest
from orchestrator.models import Task, Subtask, TaskStatus, InvalidTransitionError


class TestTaskStateMachine:
    def test_valid_transition_pending_to_decomposing(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        assert task.status == TaskStatus.DECOMPOSING

    def test_valid_transition_decomposing_to_dispatched(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        assert task.status == TaskStatus.DISPATCHED

    def test_valid_transition_dispatched_to_in_progress(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        task.transition(TaskStatus.IN_PROGRESS)
        assert task.status == TaskStatus.IN_PROGRESS

    def test_valid_transition_in_progress_to_completed(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        task.transition(TaskStatus.IN_PROGRESS)
        task.transition(TaskStatus.COMPLETED)
        assert task.status == TaskStatus.COMPLETED

    def test_valid_transition_in_progress_to_failed(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        task.transition(TaskStatus.IN_PROGRESS)
        task.transition(TaskStatus.FAILED)
        assert task.status == TaskStatus.FAILED

    def test_valid_transition_in_progress_to_partially_failed(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        task.transition(TaskStatus.IN_PROGRESS)
        task.transition(TaskStatus.PARTIALLY_FAILED)
        assert task.status == TaskStatus.PARTIALLY_FAILED

    def test_invalid_transition_pending_to_completed(self):
        task = Task(tenant_id="t1")
        with pytest.raises(InvalidTransitionError):
            task.transition(TaskStatus.COMPLETED)

    def test_invalid_transition_completed_to_pending(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        task.transition(TaskStatus.IN_PROGRESS)
        task.transition(TaskStatus.COMPLETED)
        with pytest.raises(InvalidTransitionError):
            task.transition(TaskStatus.PENDING)

    def test_invalid_transition_failed_is_terminal(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.FAILED)
        with pytest.raises(InvalidTransitionError):
            task.transition(TaskStatus.PENDING)

    def test_cancel_from_pending(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.CANCELLED)
        assert task.status == TaskStatus.CANCELLED

    def test_cancel_from_in_progress(self):
        task = Task(tenant_id="t1")
        task.transition(TaskStatus.DECOMPOSING)
        task.transition(TaskStatus.DISPATCHED)
        task.transition(TaskStatus.IN_PROGRESS)
        task.transition(TaskStatus.CANCELLED)
        assert task.status == TaskStatus.CANCELLED

    def test_transition_updates_timestamp(self):
        task = Task(tenant_id="t1")
        original = task.updated_at
        task.transition(TaskStatus.DECOMPOSING)
        assert task.updated_at >= original


class TestSubtask:
    def test_default_status_is_pending(self):
        sub = Subtask(task_id="t1", tenant_id="tenant1")
        assert sub.status == TaskStatus.PENDING

    def test_default_retry_count(self):
        sub = Subtask(task_id="t1", tenant_id="tenant1")
        assert sub.retry_count == 0
        assert sub.max_retries == 3

    def test_unique_ids(self):
        s1 = Subtask(task_id="t1", tenant_id="tenant1")
        s2 = Subtask(task_id="t1", tenant_id="tenant1")
        assert s1.subtask_id != s2.subtask_id
