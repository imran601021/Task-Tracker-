import os
import json
import argparse
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import print

# Initialize console
console = Console()

# File for persistent storage
TASK_FILE = "storage.json"


class Task:
    def __init__(self, task_id, description, status, created_at, updated_at):
        self.task_id = task_id
        self.description = description
        self.status = status
        self.createdAt = created_at
        self.updatedAt = updated_at

    def to_dict(self):
        return {
            "id": self.task_id,
            "description": self.description,
            "status": self.status,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
        }


class TaskManager:
    def __init__(self):
        self.tasks = []
        self.load_tasks()

    # Load tasks from JSON
    def load_tasks(self):
        if os.path.exists(TASK_FILE):
            try:
                with open(TASK_FILE, "r") as file:
                    data = json.load(file)
                    self.tasks = [
                        Task(
                            task["id"],
                            task["description"],
                            task["status"],
                            task["createdAt"],
                            task["updatedAt"],
                        )
                        for task in data
                    ]
            except (json.JSONDecodeError, FileNotFoundError):
                console.print("[bold red]Error reading storage file. Resetting...[/bold red]")
                self.tasks = []
                self.save_tasks()
        else:
            self.tasks = []
            self.save_tasks()

    # Save tasks
    def save_tasks(self):
        with open(TASK_FILE, "w") as file:
            json.dump([task.to_dict() for task in self.tasks], file, indent=4)

    # Generate next ID safely
    def get_next_id(self):
        if not self.tasks:
            return 1
        return max(task.task_id for task in self.tasks) + 1

    # Add task
    def add_task(self, description):
        task_id = self.get_next_id()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_task = Task(task_id, description, "TODO", now, now)
        self.tasks.append(new_task)
        self.save_tasks()

        console.print(f"[bold green]✔ Task added successfully! (ID: {task_id})[/bold green]")

    # List tasks
    def list_tasks(self):
        if not self.tasks:
            console.print("[bold red]No tasks available.[/bold red]")
            return

        table = Table(title="📋 Task Tracker")

        table.add_column("ID", style="cyan", justify="center")
        table.add_column("Description", style="white")
        table.add_column("Status", justify="center")
        table.add_column("Created At", style="yellow")
        table.add_column("Updated At", style="magenta")

        for task in self.tasks:
            status_color = "green" if task.status == "DONE" else "red"

            table.add_row(
                str(task.task_id),
                task.description,
                f"[{status_color}]{task.status}[/{status_color}]",
                task.createdAt,
                task.updatedAt,
            )

        console.print(table)

    # Mark as complete
    def mark_complete(self, task_id):
        for task in self.tasks:
            if task.task_id == task_id:
                task.status = "DONE"
                task.updatedAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save_tasks()
                console.print(f"[bold green]✔ Task {task_id} marked as DONE.[/bold green]")
                return

        console.print(f"[bold red]Task ID {task_id} not found.[/bold red]")

    # Delete task
    def delete_task(self, task_id):
        for task in self.tasks:
            if task.task_id == task_id:
                self.tasks.remove(task)
                self.save_tasks()
                console.print(f"[bold yellow]🗑 Task {task_id} deleted.[/bold yellow]")
                return

        console.print(f"[bold red]Task ID {task_id} not found.[/bold red]")


def main():
    console.print("[bold cyan]🚀 Task Tracker CLI v2.0[/bold cyan]")

    parser = argparse.ArgumentParser(description="Task Tracker CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("description", type=str, help="Task description")

    # List command
    subparsers.add_parser("list", help="List all tasks")

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark task as complete")
    complete_parser.add_argument("task_id", type=int, help="Task ID")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("task_id", type=int, help="Task ID")

    args = parser.parse_args()

    manager = TaskManager()

    if args.command == "add":
        manager.add_task(args.description)
    elif args.command == "list":
        manager.list_tasks()
    elif args.command == "complete":
        manager.mark_complete(args.task_id)
    elif args.command == "delete":
        manager.delete_task(args.task_id)


if __name__ == "__main__":
    main()
