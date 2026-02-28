import os
import json
import logging
import argparse
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config & Logging
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()
TASK_FILE = BASE_DIR / "storage.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger(__name__)

console = Console()

# Valid values — single source of truth
VALID_STATUSES = {"TODO", "IN_PROGRESS", "DONE"}
VALID_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}
DATE_FORMAT = "%Y-%m-%d %H:%M"

STATUS_COLORS = {
    "TODO": "red",
    "IN_PROGRESS": "yellow",
    "DONE": "green",
}

PRIORITY_COLORS = {
    "HIGH": "bold red",
    "MEDIUM": "yellow",
    "LOW": "cyan",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date(date_str: str) -> datetime:
    """Parse date string and raise a friendly ValueError if format is wrong."""
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        raise ValueError(
            f"Invalid date format: '{date_str}'. Expected format: YYYY-MM-DD HH:MM  "
            f"(e.g. 2025-06-01 14:30)"
        )


def find_task(tasks: list, task_id: int):
    """Return task by ID or None."""
    return next((t for t in tasks if t.task_id == task_id), None)


# ---------------------------------------------------------------------------
# Task Model
# ---------------------------------------------------------------------------

class Task:
    def __init__(
        self,
        task_id: int,
        description: str,
        status: str,
        priority: str,
        start_time: str,
        end_time: str,
        reminder_enabled: bool,
        created_at: str,
        updated_at: str,
    ):
        self.task_id = task_id
        self.description = description
        self.status = status
        self.priority = priority
        self.start_time = start_time
        self.end_time = end_time
        self.reminder_enabled = reminder_enabled
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict:
        return {
            "id": self.task_id,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "reminder_enabled": self.reminder_enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Build a Task from a JSON dict — handles missing/old fields gracefully."""
        return cls(
            task_id=data["id"],
            description=data["description"],
            status=data.get("status", "TODO"),
            priority=data.get("priority", "MEDIUM"),
            start_time=data.get("start_time", "N/A"),
            end_time=data.get("end_time", "N/A"),
            reminder_enabled=data.get("reminder_enabled", False),
            created_at=data.get("created_at") or data.get("createdAt", now_str()),
            updated_at=data.get("updated_at") or data.get("updatedAt", now_str()),
        )


# ---------------------------------------------------------------------------
# Task Manager
# ---------------------------------------------------------------------------

class TaskManager:
    def __init__(self):
        self.tasks: list[Task] = []
        self.load_tasks()

    def load_tasks(self):
        """Load tasks from disk. Handles missing or corrupted JSON gracefully."""
        if not TASK_FILE.exists():
            return

        try:
            with open(TASK_FILE, "r") as f:
                data = json.load(f)
            self.tasks = [Task.from_dict(t) for t in data]
        except json.JSONDecodeError:
            logger.error(
                f"storage.json is corrupted and could not be parsed. "
                f"Starting with empty task list. Back up and fix: {TASK_FILE}"
            )
            self.tasks = []
        except Exception as e:
            logger.error(f"Unexpected error loading tasks: {e}")
            self.tasks = []

    def save_tasks(self):
        """Persist tasks to disk."""
        try:
            with open(TASK_FILE, "w") as f:
                json.dump([t.to_dict() for t in self.tasks], f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    def get_next_id(self) -> int:
        return max((t.task_id for t in self.tasks), default=0) + 1

    # -----------------------------------------------------------------------
    # Commands
    # -----------------------------------------------------------------------

    def add_task(self, description: str, start_time: str, end_time: str,
                 reminder: bool, priority: str):
        # Validate dates upfront
        try:
            parse_date(start_time)
            parse_date(end_time)
        except ValueError as e:
            console.print(f"[bold red]✘ {e}[/bold red]")
            return

        priority = priority.upper()
        if priority not in VALID_PRIORITIES:
            console.print(f"[bold red]✘ Invalid priority '{priority}'. Choose: HIGH, MEDIUM, LOW[/bold red]")
            return

        task = Task(
            task_id=self.get_next_id(),
            description=description,
            status="TODO",
            priority=priority,
            start_time=start_time,
            end_time=end_time,
            reminder_enabled=reminder,
            created_at=now_str(),
            updated_at=now_str(),
        )

        self.tasks.append(task)
        self.save_tasks()
        console.print(f"[bold green]✔ Task added (ID: {task.task_id}, Priority: {priority})[/bold green]")

    def list_tasks(self, filter_status: str = None, filter_priority: str = None):
        tasks = self.tasks

        if filter_status:
            filter_status = filter_status.upper()
            tasks = [t for t in tasks if t.status == filter_status]

        if filter_priority:
            filter_priority = filter_priority.upper()
            tasks = [t for t in tasks if t.priority == filter_priority]

        if not tasks:
            console.print("[bold red]No tasks found.[/bold red]")
            return

        table = Table(title="📋 Task Tracker", show_lines=True)
        table.add_column("ID", justify="center", style="bold")
        table.add_column("Description")
        table.add_column("Priority", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Start Time")
        table.add_column("End Time")
        table.add_column("Reminder", justify="center")
        table.add_column("Updated At")

        for task in sorted(tasks, key=lambda t: t.task_id):
            s_color = STATUS_COLORS.get(task.status, "white")
            p_color = PRIORITY_COLORS.get(task.priority, "white")
            reminder_icon = "🔔" if task.reminder_enabled else "—"

            table.add_row(
                str(task.task_id),
                task.description,
                f"[{p_color}]{task.priority}[/{p_color}]",
                f"[{s_color}]{task.status}[/{s_color}]",
                task.start_time,
                task.end_time,
                reminder_icon,
                task.updated_at,
            )

        console.print(table)
        console.print(f"[dim]Showing {len(tasks)} task(s)[/dim]")

    def update_status(self, task_id: int, new_status: str):
        new_status = new_status.upper()
        if new_status not in VALID_STATUSES:
            console.print(f"[bold red]✘ Invalid status. Choose: {', '.join(VALID_STATUSES)}[/bold red]")
            return

        task = find_task(self.tasks, task_id)
        if not task:
            console.print(f"[bold red]✘ Task ID {task_id} not found.[/bold red]")
            return

        task.status = new_status
        task.updated_at = now_str()
        self.save_tasks()
        s_color = STATUS_COLORS.get(new_status, "white")
        console.print(f"[bold green]✔ Task {task_id} → [{s_color}]{new_status}[/{s_color}][/bold green]")

    def mark_complete(self, task_id: int):
        """Shortcut to mark a task DONE."""
        self.update_status(task_id, "DONE")

    def update_task(self, task_id: int, description: str = None,
                    start_time: str = None, end_time: str = None,
                    priority: str = None):
        task = find_task(self.tasks, task_id)
        if not task:
            console.print(f"[bold red]✘ Task ID {task_id} not found.[/bold red]")
            return

        if description:
            task.description = description

        if priority:
            priority = priority.upper()
            if priority not in VALID_PRIORITIES:
                console.print(f"[bold red]✘ Invalid priority '{priority}'. Choose: HIGH, MEDIUM, LOW[/bold red]")
                return
            task.priority = priority

        if start_time:
            try:
                parse_date(start_time)
                task.start_time = start_time
            except ValueError as e:
                console.print(f"[bold red]✘ {e}[/bold red]")
                return

        if end_time:
            try:
                parse_date(end_time)
                task.end_time = end_time
            except ValueError as e:
                console.print(f"[bold red]✘ {e}[/bold red]")
                return

        task.updated_at = now_str()
        self.save_tasks()
        console.print(f"[bold green]✔ Task {task_id} updated.[/bold green]")

    def delete_task(self, task_id: int):
        task = find_task(self.tasks, task_id)
        if not task:
            console.print(f"[bold red]✘ Task ID {task_id} not found.[/bold red]")
            return

        self.tasks.remove(task)
        self.save_tasks()
        console.print(f"[bold yellow]🗑 Task {task_id} deleted.[/bold yellow]")

    def check_notifications(self):
        """
        Notification loop — reloads tasks from disk every cycle
        so newly added tasks are always picked up.
        """
        if not PLYER_AVAILABLE:
            console.print(
                "[bold red]✘ plyer is not installed. Run: pip install plyer[/bold red]"
            )
            return

        console.print("[bold cyan]🔔 Notification service running... (Ctrl+C to stop)[/bold cyan]")

        notified_ids = set()  # Track already-notified tasks to avoid spam

        try:
            while True:
                # Reload from disk every cycle — picks up new tasks added elsewhere
                self.load_tasks()
                now = datetime.now()

                for task in self.tasks:
                    if (
                        task.status != "DONE"
                        and task.reminder_enabled
                        and task.end_time != "N/A"
                        and task.task_id not in notified_ids
                    ):
                        try:
                            end_dt = parse_date(task.end_time)
                            remaining = (end_dt - now).total_seconds()

                            if 0 < remaining <= 60:
                                plyer_notification.notify(
                                    title="⏰ Task Ending Soon",
                                    message=f"'{task.description}' ends in under a minute!",
                                    timeout=10,
                                )
                                notified_ids.add(task.task_id)
                                logger.info(f"Notification sent for task ID {task.task_id}")

                        except ValueError:
                            logger.warning(
                                f"Task ID {task.task_id} has invalid end_time format: '{task.end_time}'"
                            )

                time.sleep(30)

        except KeyboardInterrupt:
            console.print("\n[bold yellow]🔔 Notification service stopped.[/bold yellow]")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="📋 Task Tracker CLI — Manage your tasks from the terminal.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = subparsers.add_parser("add", help="Add a new task")
    add_p.add_argument("description", help="Task description")
    add_p.add_argument("--start", required=True, help="Start time (YYYY-MM-DD HH:MM)")
    add_p.add_argument("--end", required=True, help="End time (YYYY-MM-DD HH:MM)")
    add_p.add_argument("--remind", action="store_true", help="Enable reminder notification")
    add_p.add_argument(
        "--priority", default="MEDIUM",
        choices=["HIGH", "MEDIUM", "LOW"],
        help="Task priority (default: MEDIUM)",
    )

    # list
    list_p = subparsers.add_parser("list", help="List all tasks")
    list_p.add_argument(
        "--status", choices=["TODO", "IN_PROGRESS", "DONE"],
        help="Filter by status",
    )
    list_p.add_argument(
        "--priority", choices=["HIGH", "MEDIUM", "LOW"],
        help="Filter by priority",
    )

    # complete
    comp_p = subparsers.add_parser("complete", help="Mark a task as DONE")
    comp_p.add_argument("task_id", type=int, help="Task ID to mark complete")

    # status
    status_p = subparsers.add_parser("status", help="Update task status")
    status_p.add_argument("task_id", type=int)
    status_p.add_argument(
        "new_status", choices=["TODO", "IN_PROGRESS", "DONE"],
        help="New status value",
    )

    # update
    upd_p = subparsers.add_parser("update", help="Edit an existing task's fields")
    upd_p.add_argument("task_id", type=int)
    upd_p.add_argument("--description", help="New description")
    upd_p.add_argument("--start", help="New start time (YYYY-MM-DD HH:MM)")
    upd_p.add_argument("--end", help="New end time (YYYY-MM-DD HH:MM)")
    upd_p.add_argument("--priority", choices=["HIGH", "MEDIUM", "LOW"], help="New priority")

    # delete
    del_p = subparsers.add_parser("delete", help="Delete a task")
    del_p.add_argument("task_id", type=int, help="Task ID to delete")

    # notify
    subparsers.add_parser("notify", help="Start the background notification service")

    return parser


def main():
    console.print("[bold cyan]🚀 Task Tracker CLI[/bold cyan]")

    parser = build_parser()
    args = parser.parse_args()
    manager = TaskManager()

    match args.command:
        case "add":
            manager.add_task(
                args.description, args.start, args.end,
                args.remind, args.priority,
            )
        case "list":
            manager.list_tasks(
                filter_status=args.status,
                filter_priority=args.priority,
            )
        case "complete":
            manager.mark_complete(args.task_id)
        case "status":
            manager.update_status(args.task_id, args.new_status)
        case "update":
            manager.update_task(
                args.task_id,
                description=args.description,
                start_time=args.start,
                end_time=args.end,
                priority=args.priority,
            )
        case "delete":
            manager.delete_task(args.task_id)
        case "notify":
            manager.check_notifications()


if __name__ == "__main__":
    main()