from .database import database_connection


def create_task(name, description=None):
    """Save a task to the local database."""
    name = name.strip()
    if not name:
        return None
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (name, description) VALUES (?, ?)",
            (name, description),
        )
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _task_data(row)


def _task_data(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "completed": bool(row["completed"]),
        "created_at": row["created_at"],
    }


def get_tasks():
    """Return saved tasks, including completion status."""
    with database_connection() as connection:
        rows = connection.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [_task_data(row) for row in rows]


def complete_task(name):
    """Mark the newest unfinished task with this name as complete."""
    with database_connection() as connection:
        row = connection.execute(
            "SELECT id FROM tasks WHERE name = ? COLLATE NOCASE AND completed = 0 ORDER BY id DESC LIMIT 1",
            (name,),
        ).fetchone()
        if row is None:
            return None
        connection.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (row["id"],))
        updated = connection.execute("SELECT * FROM tasks WHERE id = ?", (row["id"],)).fetchone()
        return _task_data(updated)
