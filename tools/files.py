import os
from pathlib import Path

from rapidfuzz import fuzz

if __package__:
    from .database import database_connection
else:
    from database import database_connection, initialize_database

    initialize_database()


def add_approved_folder(name, path):
    """Add or update a locally approved folder. Intended for local settings UI."""
    name = name.strip()
    path = os.path.normpath(os.path.expandvars(os.path.expanduser(path.strip())))
    with database_connection() as connection:
        connection.execute(
            """INSERT INTO approved_folders (name, path, enabled) VALUES (?, ?, 1)
               ON CONFLICT(name) DO UPDATE SET path = excluded.path, enabled = 1""",
            (name, path),
        )
        row = connection.execute(
            "SELECT * FROM approved_folders WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return _folder_data(row)


def _folder_data(row):
    return {"id": row["id"], "name": row["name"], "path": row["path"],
            "enabled": bool(row["enabled"])}


def get_approved_folder(name):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM approved_folders WHERE name = ? COLLATE NOCASE AND enabled = 1",
            (name,),
        ).fetchone()
        return _folder_data(row) if row else None


def list_approved_folders(include_disabled=False):
    with database_connection() as connection:
        query = "SELECT * FROM approved_folders"
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY name COLLATE NOCASE"
        return [_folder_data(row) for row in connection.execute(query).fetchall()]


def set_approved_folder_enabled(name, enabled):
    with database_connection() as connection:
        cursor = connection.execute(
            "UPDATE approved_folders SET enabled = ? WHERE name = ? COLLATE NOCASE",
            (int(bool(enabled)), name),
        )
        return cursor.rowcount > 0


def open_approved_folder(name):
    """Open an enabled approved folder by name; the local path never leaves Python."""
    folder = get_approved_folder(name)
    if folder is None:
        return {"ok": False, "message": f"{name} is not an approved folder."}
    try:
        os.startfile(folder["path"])
    except (OSError, AttributeError):
        return {"ok": False, "message": f"Windows could not open folder {folder['name']}."}
    return {"ok": True, "folder": folder["name"]}


SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".idea", ".vscode", "node_modules",
}


def get_search_locations():
    """Return only enabled folders explicitly approved for local search."""
    locations = [Path(folder["path"]) for folder in list_approved_folders()]
    unique = []
    seen = set()
    for path in locations:
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized not in seen and path.exists() and path.is_dir():
            seen.add(normalized)
            unique.append(path)
    return unique


def search_files(query, threshold=60):
    matches = []

    def search_directory(directory):
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.lower() in SKIP_DIRS:
                            continue
                        score = fuzz.ratio(query.lower(), entry.name.lower())
                        if score >= threshold:
                            matches.append({"name": entry.name, "path": entry.path,
                                            "score": score, "type": "folder"})
                        search_directory(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        score = fuzz.ratio(query.lower(), entry.name.lower())
                        if score >= threshold:
                            matches.append({"name": entry.name, "path": entry.path,
                                            "score": score, "type": "file"})
        except (PermissionError, OSError):
            pass

    for location in get_search_locations():
        search_directory(location)
    matches.sort(key=lambda match: match["score"], reverse=True)
    return matches[:5]


def open_from_path(path):
    """Open a path directly for local Python callers; this is not a Gemini tool."""
    os.startfile(path)
