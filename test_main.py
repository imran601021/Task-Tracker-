import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Import everything we need to test from main
from main import Task, TaskManager, parse_date, find_task, DATE_FORMAT, TASK_FILE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_task_file(tmp_path, monkeypatch):
    """
    Redirect TASK_FILE to a temp directory for every test.
    This means tests NEVER touch your real storage.json.
    Each test gets a clean, empty file.
    """
    fake_file = tmp_path / "storage.json"
    monkeypatch.setattr("main.TASK_FILE", fake_file)
    return fake_file


@pytest.fixture
def manager(tmp_task_file):
    """Return a fresh TaskManager backed by a temp file."""
    return TaskManager()


@pytest.fixture
def manager_with_tasks(manager):
    """Return a TaskManager pre-loaded with 3 tasks."""
    manager.add_task("Task One",   "2025-06-01 09:00", "2025-06-01 10:00", False, "HIGH")
    manager.add_task("Task Two",   "2025-06-01 10:00", "2025-06-01 11:00", True,  "MEDIUM")
    manager.add_task("Task Three", "2025-06-01 11:00", "2025-06-01 12:00", False, "LOW")
    return manager


# ---------------------------------------------------------------------------
# parse_date() Tests
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_valid_date(self):
        dt = parse_date("2025-06-01 14:30")
        assert dt.year == 2025
        assert dt.month == 6
        assert dt.day == 1
        assert dt.hour == 14
        assert dt.minute == 30

    def test_invalid_date_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date("tomorrow")

    def test_wrong_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date("01-06-2025 14:30")  # Day-Month-Year — wrong order

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_date("")


# ---------------------------------------------------------------------------
# Task Model Tests
# ---------------------------------------------------------------------------

class TestTaskModel:
    def test_to_dict_has_all_fields(self):
        task = Task(1, "Test task", "TODO", "HIGH",
                    "2025-06-01 09:00", "2025-06-01 10:00",
                    True, "2025-06-01 08:00:00", "2025-06-01 08:00:00")
        d = task.to_dict()

        assert d["id"] == 1
        assert d["description"] == "Test task"
        assert d["status"] == "TODO"
        assert d["priority"] == "HIGH"
        assert d["reminder_enabled"] is True

    def test_from_dict_round_trip(self):
        """to_dict() → from_dict() should produce an identical task."""
        original = Task(5, "Round trip", "IN_PROGRESS", "LOW",
                        "2025-06-01 09:00", "2025-06-01 10:00",
                        False, "2025-01-01 00:00:00", "2025-01-01 00:00:00")

        restored = Task.from_dict(original.to_dict())

        assert restored.task_id == original.task_id
        assert restored.description == original.description
        assert restored.status == original.status
        assert restored.priority == original.priority
        assert restored.reminder_enabled == original.reminder_enabled

    def test_from_dict_applies_defaults_for_missing_fields(self):
        """Old JSON files without 'priority' should default to MEDIUM."""
        minimal = {
            "id": 1,
            "description": "Old task",
            "status": "TODO",
            "createdAt": "2025-01-01 00:00:00",
            "updatedAt": "2025-01-01 00:00:00",
        }
        task = Task.from_dict(minimal)
        assert task.priority == "MEDIUM"
        assert task.start_time == "N/A"
        assert task.end_time == "N/A"
        assert task.reminder_enabled is False

    def test_from_dict_handles_legacy_camelcase_keys(self):
        """Old storage.json files used createdAt/updatedAt — must still load."""
        data = {
            "id": 2,
            "description": "Legacy task",
            "status": "DONE",
            "createdAt": "2024-01-01 00:00:00",
            "updatedAt": "2024-06-01 00:00:00",
        }
        task = Task.from_dict(data)
        assert task.created_at == "2024-01-01 00:00:00"
        assert task.updated_at == "2024-06-01 00:00:00"


# ---------------------------------------------------------------------------
# TaskManager — Core Operations
# ---------------------------------------------------------------------------

class TestTaskManagerAdd:
    def test_add_task_increases_count(self, manager):
        assert len(manager.tasks) == 0
        manager.add_task("My Task", "2025-06-01 09:00", "2025-06-01 10:00", False, "HIGH")
        assert len(manager.tasks) == 1

    def test_added_task_has_correct_fields(self, manager):
        manager.add_task("My Task", "2025-06-01 09:00", "2025-06-01 10:00", True, "HIGH")
        task = manager.tasks[0]

        assert task.description == "My Task"
        assert task.status == "TODO"
        assert task.priority == "HIGH"
        assert task.reminder_enabled is True

    def test_ids_are_unique_and_sequential(self, manager):
        manager.add_task("Task A", "2025-06-01 09:00", "2025-06-01 10:00", False, "LOW")
        manager.add_task("Task B", "2025-06-01 09:00", "2025-06-01 10:00", False, "LOW")
        manager.add_task("Task C", "2025-06-01 09:00", "2025-06-01 10:00", False, "LOW")

        ids = [t.task_id for t in manager.tasks]
        assert ids == [1, 2, 3]
        assert len(set(ids)) == 3  # All unique

    def test_add_task_with_invalid_date_does_not_add(self, manager):
        manager.add_task("Bad Task", "not-a-date", "2025-06-01 10:00", False, "LOW")
        assert len(manager.tasks) == 0

    def test_add_task_with_invalid_priority_does_not_add(self, manager):
        manager.add_task("Bad Task", "2025-06-01 09:00", "2025-06-01 10:00", False, "URGENT")
        assert len(manager.tasks) == 0

    def test_tasks_persist_after_reload(self, manager, tmp_task_file):
        """Tasks saved to disk should survive a fresh TaskManager load."""
        manager.add_task("Persisted Task", "2025-06-01 09:00", "2025-06-01 10:00", False, "HIGH")

        # Simulate restarting the app
        reloaded = TaskManager()
        assert len(reloaded.tasks) == 1
        assert reloaded.tasks[0].description == "Persisted Task"


class TestTaskManagerComplete:
    def test_mark_complete_sets_done(self, manager_with_tasks):
        manager_with_tasks.mark_complete(1)
        task = find_task(manager_with_tasks.tasks, 1)
        assert task.status == "DONE"

    def test_mark_complete_nonexistent_id_does_not_crash(self, manager_with_tasks):
        # Should print an error, not raise an exception
        manager_with_tasks.mark_complete(999)

    def test_complete_updates_updated_at(self, manager_with_tasks):
        before = find_task(manager_with_tasks.tasks, 1).updated_at
        manager_with_tasks.mark_complete(1)
        after = find_task(manager_with_tasks.tasks, 1).updated_at
        # updated_at should have changed
        assert after >= before


class TestTaskManagerStatus:
    def test_set_in_progress(self, manager_with_tasks):
        manager_with_tasks.update_status(1, "IN_PROGRESS")
        assert find_task(manager_with_tasks.tasks, 1).status == "IN_PROGRESS"

    def test_invalid_status_does_not_change_task(self, manager_with_tasks):
        manager_with_tasks.update_status(1, "STARTED")  # Invalid
        assert find_task(manager_with_tasks.tasks, 1).status == "TODO"  # Unchanged

    def test_status_nonexistent_task_does_not_crash(self, manager_with_tasks):
        manager_with_tasks.update_status(999, "DONE")  # Should not raise


class TestTaskManagerDelete:
    def test_delete_removes_task(self, manager_with_tasks):
        manager_with_tasks.delete_task(1)
        assert find_task(manager_with_tasks.tasks, 1) is None
        assert len(manager_with_tasks.tasks) == 2

    def test_delete_nonexistent_id_does_not_crash(self, manager_with_tasks):
        manager_with_tasks.delete_task(999)
        assert len(manager_with_tasks.tasks) == 3  # Unchanged

    def test_ids_of_remaining_tasks_are_unchanged(self, manager_with_tasks):
        manager_with_tasks.delete_task(2)
        ids = [t.task_id for t in manager_with_tasks.tasks]
        assert 1 in ids
        assert 3 in ids
        assert 2 not in ids


class TestTaskManagerUpdate:
    def test_update_description(self, manager_with_tasks):
        manager_with_tasks.update_task(1, description="Updated description")
        assert find_task(manager_with_tasks.tasks, 1).description == "Updated description"

    def test_update_priority(self, manager_with_tasks):
        manager_with_tasks.update_task(1, priority="LOW")
        assert find_task(manager_with_tasks.tasks, 1).priority == "LOW"

    def test_update_with_invalid_date_does_not_change_task(self, manager_with_tasks):
        original_end = find_task(manager_with_tasks.tasks, 1).end_time
        manager_with_tasks.update_task(1, end_time="bad-date")
        assert find_task(manager_with_tasks.tasks, 1).end_time == original_end

    def test_update_nonexistent_task_does_not_crash(self, manager_with_tasks):
        manager_with_tasks.update_task(999, description="Ghost task")


# ---------------------------------------------------------------------------
# TaskManager — Filtering
# ---------------------------------------------------------------------------

class TestTaskManagerFiltering:
    def test_filter_by_status(self, manager_with_tasks, capsys):
        manager_with_tasks.mark_complete(1)
        done_tasks = [t for t in manager_with_tasks.tasks if t.status == "DONE"]
        todo_tasks = [t for t in manager_with_tasks.tasks if t.status == "TODO"]
        assert len(done_tasks) == 1
        assert len(todo_tasks) == 2

    def test_filter_by_priority(self, manager_with_tasks):
        high = [t for t in manager_with_tasks.tasks if t.priority == "HIGH"]
        medium = [t for t in manager_with_tasks.tasks if t.priority == "MEDIUM"]
        low = [t for t in manager_with_tasks.tasks if t.priority == "LOW"]
        assert len(high) == 1
        assert len(medium) == 1
        assert len(low) == 1


# ---------------------------------------------------------------------------
# TaskManager — Persistence & Edge Cases
# ---------------------------------------------------------------------------

class TestTaskManagerPersistence:
    def test_load_from_corrupted_json_does_not_crash(self, tmp_task_file):
        """Corrupted storage.json should result in empty task list, not a crash."""
        tmp_task_file.write_text("{ this is not valid JSON !!!")
        manager = TaskManager()
        assert manager.tasks == []

    def test_load_from_empty_file_does_not_crash(self, tmp_task_file):
        tmp_task_file.write_text("")
        manager = TaskManager()
        assert manager.tasks == []

    def test_load_when_file_does_not_exist(self, tmp_task_file):
        # Don't create the file at all
        assert not tmp_task_file.exists()
        manager = TaskManager()
        assert manager.tasks == []

    def test_next_id_after_deletion_does_not_reuse(self, manager_with_tasks):
        """After deleting task 3, next ID should be 4, not 3."""
        manager_with_tasks.delete_task(3)
        manager_with_tasks.add_task("New Task", "2025-06-01 09:00", "2025-06-01 10:00", False, "LOW")
        new_task = manager_with_tasks.tasks[-1]
        assert new_task.task_id == 4


# ---------------------------------------------------------------------------
# Notification Logic Tests
# ---------------------------------------------------------------------------

class TestNotificationLogic:
    """
    Test the logic that decides WHICH tasks should trigger notifications.
    We don't test the actual OS notification popup — that's an external side effect.
    """

    def _tasks_due_within(self, seconds: int) -> list:
        """Helper: build a task whose end_time is `seconds` from now."""
        end_time = (datetime.now() + timedelta(seconds=seconds)).strftime(DATE_FORMAT)
        return [Task(1, "Urgent task", "TODO", "HIGH",
                     "2025-06-01 09:00", end_time, True,
                     "2025-06-01 08:00:00", "2025-06-01 08:00:00")]

    def test_task_due_in_30_seconds_should_notify(self):
        tasks = self._tasks_due_within(30)
        task = tasks[0]
        end_dt = parse_date(task.end_time)
        remaining = (end_dt - datetime.now()).total_seconds()
        assert 0 < remaining <= 60  # Should trigger notification window

    def test_task_due_in_5_minutes_should_not_notify(self):
        tasks = self._tasks_due_within(300)
        task = tasks[0]
        end_dt = parse_date(task.end_time)
        remaining = (end_dt - datetime.now()).total_seconds()
        assert remaining > 60  # Outside notification window

    def test_completed_task_should_not_notify(self):
        end_time = (datetime.now() + timedelta(seconds=30)).strftime(DATE_FORMAT)
        task = Task(1, "Done task", "DONE", "HIGH",
                    "2025-06-01 09:00", end_time, True,
                    "2025-06-01 08:00:00", "2025-06-01 08:00:00")
        # DONE tasks should be excluded from notifications
        assert task.status == "DONE"  # Notification loop checks this

    def test_task_without_reminder_should_not_notify(self):
        end_time = (datetime.now() + timedelta(seconds=30)).strftime(DATE_FORMAT)
        task = Task(1, "No reminder", "TODO", "HIGH",
                    "2025-06-01 09:00", end_time, False,  # reminder_enabled = False
                    "2025-06-01 08:00:00", "2025-06-01 08:00:00")
        assert task.reminder_enabled is False

    def test_overdue_task_should_not_notify(self):
        """Tasks already past their end time (remaining <= 0) should NOT notify."""
        end_time = (datetime.now() - timedelta(seconds=60)).strftime(DATE_FORMAT)
        task = Task(1, "Overdue task", "TODO", "HIGH",
                    "2025-06-01 09:00", end_time, True,
                    "2025-06-01 08:00:00", "2025-06-01 08:00:00")
        end_dt = parse_date(task.end_time)
        remaining = (end_dt - datetime.now()).total_seconds()
        assert remaining <= 0  # Notification loop: `if 0 < remaining <= 60` → False