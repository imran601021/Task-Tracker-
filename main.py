"""
Task Tracker CLI — Optimized & Production-Ready
------------------------------------------------
Senior Dev Refactor:
  - Fixed: notify command was never handled in main()
  - Fixed: notification loop reloads tasks from disk each cycle (no stale data)
  - Fixed: date input validation with friendly error messages
  - Fixed: corrupted JSON handled gracefully on startup
  - Fixed: removed `from rich import print` (shadows built-in, redundant)
  - Fixed: all naming unified to snake_case (Python standard)
  - Fixed: TASK_FILE now absolute path (resolved relative to script)
  - Added: IN_PROGRESS status (TODO → IN_PROGRESS → DONE)
  - Added: priority field (HIGH / MEDIUM / LOW) with color coding
  - Added: --status and --priority filters on list command
  - Added: `update` command to edit description/times on existing tasks
  - Added: `view` command — interactive task card with instant keypress editing
  - Added: `add` command now fully interactive — no flags needed, prompts step by step
"""

import os
import json
import logging
import argparse
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.logging import RichHandler

try:
    import readchar
    READCHAR_AVAILABLE = True
except ImportError:
    READCHAR_AVAILABLE = False

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

    def prompt_add_task(self):
        """
        Fully interactive task creation — asks questions one by one.
        User just runs `python main.py add` with no flags at all.
        Retries on invalid input instead of crashing.
        """
        console.print(Panel(
            "[bold cyan]Let's create a new task![/bold cyan]\n[dim]Press Ctrl+C anytime to cancel.[/dim]",
            border_style="cyan",
            padding=(0, 2),
        ))

        try:
            # --- Description ---
            while True:
                description = console.input("\n[bold yellow]➤ Task description :[/bold yellow] ").strip()
                if description:
                    break
                console.print("[red]  Description can't be empty. Try again.[/red]")

            # --- Start Time ---
            while True:
                start_str = console.input("[bold yellow]➤ Start time        :[/bold yellow] [dim](YYYY-MM-DD HH:MM)[/dim] ").strip()
                try:
                    parse_date(start_str)
                    break
                except ValueError:
                    console.print("[red]  Invalid format. Example: 2025-06-01 09:00[/red]")

            # --- End Time ---
            while True:
                end_str = console.input("[bold yellow]➤ End time          :[/bold yellow] [dim](YYYY-MM-DD HH:MM)[/dim] ").strip()
                try:
                    parse_date(end_str)
                    break
                except ValueError:
                    console.print("[red]  Invalid format. Example: 2025-06-01 11:00[/red]")

            # --- Priority ---
            priority_map = {"h": "HIGH", "m": "MEDIUM", "l": "LOW"}
            while True:
                p_input = console.input("[bold yellow]➤ Priority          :[/bold yellow] [dim](H = High, M = Medium, L = Low)[/dim] ").strip().lower()
                if p_input in priority_map:
                    priority = priority_map[p_input]
                    break
                console.print("[red]  Invalid. Type H, M, or L.[/red]")

            # --- Reminder ---
            while True:
                r_input = console.input("[bold yellow]➤ Set reminder?     :[/bold yellow] [dim](y / n)[/dim] ").strip().lower()
                if r_input in ("y", "n"):
                    reminder = r_input == "y"
                    break
                console.print("[red]  Please type y or n.[/red]")

            # --- Confirm ---
            console.print("\n[bold]  Summary:[/bold]")
            console.print(f"  Description : [cyan]{description}[/cyan]")
            console.print(f"  Start       : [cyan]{start_str}[/cyan]")
            console.print(f"  End         : [cyan]{end_str}[/cyan]")
            console.print(f"  Priority    : [cyan]{priority}[/cyan]")
            console.print(f"  Reminder    : [cyan]{'🔔 On' if reminder else '🔕 Off'}[/cyan]")

            confirm = console.input("\n[bold yellow]➤ Confirm? (y / n)  :[/bold yellow] ").strip().lower()
            if confirm != "y":
                console.print("[dim]  Cancelled. Task not saved.[/dim]")
                return

            # --- Save ---
            self.add_task(description, start_str, end_str, reminder, priority)

        except KeyboardInterrupt:
            console.print("\n[dim]  Cancelled.[/dim]")

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

    def view_task(self, task_id: int):
        """
        Interactive task detail view.
        Shows a rich task card, then lets the user edit any field
        with a single keypress — no flags, no re-typing the command.
        """
        if not READCHAR_AVAILABLE:
            console.print("[bold red]✘ readchar not installed. Run: pip install readchar[/bold red]")
            return

        task = find_task(self.tasks, task_id)
        if not task:
            console.print(f"[bold red]✘ Task ID {task_id} not found.[/bold red]")
            return

        while True:
            # Always reload from disk so the card shows latest data
            self.load_tasks()
            task = find_task(self.tasks, task_id)
            if not task:
                console.print(f"[bold red]✘ Task {task_id} no longer exists.[/bold red]")
                return

            console.clear()
            self._render_task_card(task)
            self._render_menu()

            key = readchar.readkey()

            if key == 'd':
                console.print("\n[bold cyan]New description (Enter to confirm):[/bold cyan] ", end="")
                new_desc = input().strip()
                if new_desc:
                    task.description = new_desc
                    task.updated_at = now_str()
                    self.save_tasks()
                    console.print("[bold green]✔ Description updated.[/bold green]")
                else:
                    console.print("[dim]No changes made.[/dim]")

            elif key == 's':
                console.print("\n[bold cyan]New status — choose:[/bold cyan]")
                console.print("  [red][1][/red] TODO   [yellow][2][/yellow] IN_PROGRESS   [green][3][/green] DONE")
                console.print("Press 1, 2 or 3: ", end="")
                status_key = readchar.readkey()
                status_map = {"1": "TODO", "2": "IN_PROGRESS", "3": "DONE"}
                if status_key in status_map:
                    task.status = status_map[status_key]
                    task.updated_at = now_str()
                    self.save_tasks()
                    console.print(f"\n[bold green]✔ Status → {task.status}[/bold green]")
                else:
                    console.print("\n[dim]Invalid key. No changes made.[/dim]")

            elif key == 'p':
                console.print("\n[bold cyan]New priority — choose:[/bold cyan]")
                console.print("  [bold red][1][/bold red] HIGH   [yellow][2][/yellow] MEDIUM   [cyan][3][/cyan] LOW")
                console.print("Press 1, 2 or 3: ", end="")
                priority_key = readchar.readkey()
                priority_map = {"1": "HIGH", "2": "MEDIUM", "3": "LOW"}
                if priority_key in priority_map:
                    task.priority = priority_map[priority_key]
                    task.updated_at = now_str()
                    self.save_tasks()
                    console.print(f"\n[bold green]✔ Priority → {task.priority}[/bold green]")
                else:
                    console.print("\n[dim]Invalid key. No changes made.[/dim]")

            elif key == 't':
                console.print("\n[bold cyan]Edit times:[/bold cyan]")
                console.print(f"  Current start : [yellow]{task.start_time}[/yellow]")
                console.print(f"  Current end   : [yellow]{task.end_time}[/yellow]")
                console.print("  New start time (YYYY-MM-DD HH:MM) — press Enter to skip: ", end="")
                new_start = input().strip()
                console.print("  New end time   (YYYY-MM-DD HH:MM) — press Enter to skip: ", end="")
                new_end = input().strip()

                changed = False
                if new_start:
                    try:
                        parse_date(new_start)
                        task.start_time = new_start
                        changed = True
                    except ValueError as e:
                        console.print(f"[bold red]✘ {e}[/bold red]")

                if new_end:
                    try:
                        parse_date(new_end)
                        task.end_time = new_end
                        changed = True
                    except ValueError as e:
                        console.print(f"[bold red]✘ {e}[/bold red]")

                if changed:
                    task.updated_at = now_str()
                    self.save_tasks()
                    console.print("[bold green]✔ Times updated.[/bold green]")
                else:
                    console.print("[dim]No changes made.[/dim]")

            elif key == 'r':
                task.reminder_enabled = not task.reminder_enabled
                task.updated_at = now_str()
                self.save_tasks()
                state = "🔔 ON" if task.reminder_enabled else "🔕 OFF"
                console.print(f"\n[bold green]✔ Reminder toggled → {state}[/bold green]")

            elif key == 'x':
                console.print("\n[bold red]⚠ Delete this task? Press 'y' to confirm, any other key to cancel.[/bold red]")
                confirm = readchar.readkey()
                if confirm == 'y':
                    self.tasks.remove(task)
                    self.save_tasks()
                    console.print("[bold yellow]🗑 Task deleted.[/bold yellow]")
                    return
                else:
                    console.print("[dim]Cancelled.[/dim]")

            elif key in ('q', readchar.key.CTRL_C, readchar.key.ESC):
                console.print("\n[dim]Exiting view.[/dim]")
                return

            # Brief pause so the user can read the confirmation message
            time.sleep(0.8)

    def _render_task_card(self, task: "Task"):
        """Render a beautiful detail card for a single task."""
        s_color = STATUS_COLORS.get(task.status, "white")
        p_color = PRIORITY_COLORS.get(task.priority, "white")
        reminder_str = "🔔 On" if task.reminder_enabled else "🔕 Off"

        content = (
            f"[bold]Description :[/bold] {task.description}\n"
            f"[bold]Status      :[/bold] [{s_color}]{task.status}[/{s_color}]\n"
            f"[bold]Priority    :[/bold] [{p_color}]{task.priority}[/{p_color}]\n"
            f"[bold]Start Time  :[/bold] {task.start_time}\n"
            f"[bold]End Time    :[/bold] {task.end_time}\n"
            f"[bold]Reminder    :[/bold] {reminder_str}\n"
            f"[bold]Created     :[/bold] [dim]{task.created_at}[/dim]\n"
            f"[bold]Updated     :[/bold] [dim]{task.updated_at}[/dim]"
        )

        console.print(
            Panel(
                content,
                title=f"[bold cyan]📋 Task #{task.task_id}[/bold cyan]",
                border_style="cyan",
                padding=(1, 3),
            )
        )

    def _render_menu(self):
        """Render the keypress action menu."""
        menu = Text()
        menu.append("\n  What would you like to do?\n\n", style="bold")
        menu.append("  [d]", style="bold yellow") ; menu.append("  Edit Description\n")
        menu.append("  [s]", style="bold yellow") ; menu.append("  Change Status\n")
        menu.append("  [p]", style="bold yellow") ; menu.append("  Change Priority\n")
        menu.append("  [t]", style="bold yellow") ; menu.append("  Edit Times\n")
        menu.append("  [r]", style="bold yellow") ; menu.append("  Toggle Reminder\n")
        menu.append("  [x]", style="bold red")    ; menu.append("  Delete Task\n")
        menu.append("  [q]", style="bold white")  ; menu.append("  Quit\n")

        console.print(
            Panel(menu, border_style="dim", padding=(0, 2))
        )

    def check_notifications(self):
        """
        Notification loop — two triggers per task:
          1. 🔔 1 minute WARNING  — fires when 0 < remaining <= 60 seconds
          2. 🔔 EXACT TIME alert  — fires when -30 <= remaining <= 0 seconds
             (30s window handles the 30s sleep drift so we never miss exact time)

        Uses two separate tracking sets so both alerts always fire independently.
        Reloads tasks from disk every cycle so new tasks are always picked up.
        """
        if not PLYER_AVAILABLE:
            console.print(
                "[bold red]✘ plyer is not installed. Run: pip install plyer[/bold red]"
            )
            return

        console.print("[bold cyan]🔔 Notification service running... (Ctrl+C to stop)[/bold cyan]")
        console.print("[dim]  Will alert 1 minute before AND at the exact end time of each task.[/dim]\n")

        # Two separate sets — so both notifications always fire independently
        warned_ids = set()   # Tracks tasks that got the "1 min warning"
        alerted_ids = set()  # Tracks tasks that got the "time's up" alert

        try:
            while True:
                self.load_tasks()
                now = datetime.now()

                for task in self.tasks:
                    # Skip tasks that don't qualify
                    if (
                        task.status == "DONE"
                        or not task.reminder_enabled
                        or task.end_time == "N/A"
                    ):
                        continue

                    try:
                        end_dt = parse_date(task.end_time)
                        remaining = (end_dt - now).total_seconds()

                        # --- Trigger 1: 1 minute warning ---
                        if 0 < remaining <= 60 and task.task_id not in warned_ids:
                            plyer_notification.notify(
                                title="⏰ Task Ending Soon",
                                message=f"'{task.description}' ends in under a minute!",
                                timeout=10,
                            )
                            warned_ids.add(task.task_id)
                            logger.info(f"[WARNING] 1-min alert sent → Task ID {task.task_id}")

                        # --- Trigger 2: Exact end time ---
                        # Window of -30s to 0s accounts for the 30s sleep cycle
                        elif -30 <= remaining <= 0 and task.task_id not in alerted_ids:
                            plyer_notification.notify(
                                title="🔴 Task Time's Up",
                                message=f"'{task.description}' has reached its end time!",
                                timeout=15,
                            )
                            alerted_ids.add(task.task_id)
                            logger.info(f"[TIME'S UP] End-time alert sent → Task ID {task.task_id}")

                    except ValueError:
                        logger.warning(
                            f"Task ID {task.task_id} has invalid end_time: '{task.end_time}'"
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
    subparsers.add_parser("add", help="Add a new task (interactive)")

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

    # view — interactive task card
    view_p = subparsers.add_parser("view", help="View and interactively edit a task")
    view_p.add_argument("task_id", type=int, help="Task ID to view")

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
            manager.prompt_add_task()
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
        case "view":
            manager.view_task(args.task_id)
        case "notify":
            manager.check_notifications()


if __name__ == "__main__":
    main()