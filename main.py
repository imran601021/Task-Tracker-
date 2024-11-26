import os
import json
from datetime import datetime
import argparse

# Global variables
TaskFile = "storage.json"
TaskTracker = []


class Task:
    def __init__(self,task_id, description, status, created_at, updated_at):
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


# Function to load tasks from the JSON file
def load_tasks():
    global TaskTracker
    if os.path.exists(TaskFile):
        try:
            with open(TaskFile, "r") as file:
                TaskTracker = [
                    Task(
                        task_id=task["id"],
                        description=task["description"],
                        status=task["status"],
                        created_at=task["createdAt"],
                        updated_at=task["updatedAt"],
                    )
                    for task in json.load(file)
                ]
        except (json.JSONDecodeError, FileNotFoundError):
            print("Error reading storage.json. Reinitializing the file.")
            TaskTracker = []
            save_tasks()
    else:
        TaskTracker = []
        save_tasks()


# Function to save tasks to the JSON file
def save_tasks():
    with open(TaskFile, "w") as file:
        json.dump([task.to_dict() for task in TaskTracker], file, indent=4)


# Function to add a task
def add_task(description):
    task_id = max([task.task_id for task in TaskTracker], default=0) + 1
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task = Task(task_id, description, "todo", created_at, created_at)
    TaskTracker.append(task)
    save_tasks()
    print(f"Task added: {description}")


# Function to list all tasks
def list_tasks():
    if not TaskTracker:
        print("No tasks available.")
        return
    print("Task List:")
    for task in TaskTracker:
        print(
            f"{task.task_id}. {task.description} - {task.status} "
            f"(Created: {task.createdAt}, Updated: {task.updatedAt})"
        )


# Function to mark a task as done
def mark_as_done(task_id):
    if 0 < task_id <= len(TaskTracker):
        task = TaskTracker[task_id - 1]
        task.status = "Done"
        task.updatedAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_tasks()
        print(f"Task {task_id} marked as Done.")
    else:
        print(f"Task ID {task_id} does not exist.")


# Function to delete a task
def delete_task(task_id):
    if 0 < task_id <= len(TaskTracker):
        TaskTracker.pop(task_id - 1)
        save_tasks()
        print(f"Task {task_id} deleted.")
    else:
        print(f"Task ID {task_id} does not exist.")


# Main function for command-line argument parsing
def main():
    parser = argparse.ArgumentParser(description="Task Tracker CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("description", type=str, help="Description of the task")

    # List command
    subparsers.add_parser("list", help="List all tasks")

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark a task as done")
    complete_parser.add_argument("task_id", type=int, help="ID of the task to mark as done")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("task_id", type=int, help="ID of the task to delete")

    # Parse arguments
    args = parser.parse_args()

    # Load tasks before processing
    load_tasks()

    # Execute the appropriate command
    if args.command == "add":
        add_task(args.description)
    elif args.command == "list":
        list_tasks()
    elif args.command == "complete":
        mark_as_done(args.task_id)
    elif args.command == "delete":
        delete_task(args.task_id)
    else:
        print("Invalid command. Use --help for available commands.")


if __name__ == "__main__":
    main()
