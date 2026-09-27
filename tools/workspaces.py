import webbrowser
from .applications import open_approved_application
from .database import database_connection
from .files import open_approved_folder
from .websites import normalize_website_url


def _name_list(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    names = []
    seen = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            name = value.strip()
            key = name.casefold()
            if key not in seen:
                names.append(name)
                seen.add(key)
    return names


def _website_list(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    urls = []
    seen = set()
    for value in values:
        url = normalize_website_url(value)
        key = url.casefold()
        if key not in seen:
            urls.append(url)
            seen.add(key)
    return urls


def _workspace_data(connection, workspace_row):
    workspace_id = workspace_row["id"]
    applications = connection.execute(
        """SELECT a.name FROM approved_applications AS a
           JOIN workspace_applications AS wa ON wa.application_id = a.id
           WHERE wa.workspace_id = ? ORDER BY a.name COLLATE NOCASE""",
        (workspace_id,),
    ).fetchall()
    folders = connection.execute(
        """SELECT f.name FROM approved_folders AS f
           JOIN workspace_folders AS wf ON wf.folder_id = f.id
           WHERE wf.workspace_id = ? ORDER BY f.name COLLATE NOCASE""",
        (workspace_id,),
    ).fetchall()
    websites = connection.execute(
        "SELECT url FROM workspace_websites WHERE workspace_id = ? ORDER BY url",
        (workspace_id,),
    ).fetchall()
    return {
        "id": workspace_id,
        "name": workspace_row["name"],
        "applications": [row["name"] for row in applications],
        "folders": [row["name"] for row in folders],
        "websites": [row["url"] for row in websites],
        "is_active": bool(workspace_row["is_active"]),
    }


def _approved_ids(connection, table, names):
    if table not in {"approved_applications", "approved_folders"}:
        raise ValueError("Unsupported approved item type")
    id_column = "id"
    name_column = "name"
    results = []
    for name in names:
        row = connection.execute(
            f"SELECT {id_column} FROM {table} WHERE {name_column} = ? COLLATE NOCASE AND enabled = 1",
            (name,),
        ).fetchone()
        if row is None:
            return None, name
        results.append(row[id_column])
    return results, None


def create_workspace(name, applications=None, folders=None, websites=None):
    """Create a workspace that refers to locally approved applications and folders by name."""
    name = name.strip()
    if not name:
        return {"ok": False, "message": "A workspace name is required."}
    applications = _name_list(applications)
    folders = _name_list(folders)
    try:
        websites = _website_list(websites)
    except ValueError as error:
        return {"ok": False, "message": str(error)}

    with database_connection() as connection:
        if connection.execute(
            "SELECT 1 FROM workspaces WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone():
            return {"ok": False, "message": f"A workspace named {name} already exists."}

        application_ids, missing_application = _approved_ids(
            connection, "approved_applications", applications
        )
        if missing_application:
            return {
                "ok": False,
                "message": f"Application {missing_application} is not approved. Add it in local settings first.",
            }
        folder_ids, missing_folder = _approved_ids(connection, "approved_folders", folders)
        if missing_folder:
            return {
                "ok": False,
                "message": f"Folder {missing_folder} is not approved. Add it in local settings first.",
            }

        cursor = connection.execute("INSERT INTO workspaces (name) VALUES (?)", (name,))
        workspace_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO workspace_applications (workspace_id, application_id) VALUES (?, ?)",
            [(workspace_id, item_id) for item_id in application_ids],
        )
        connection.executemany(
            "INSERT INTO workspace_folders (workspace_id, folder_id) VALUES (?, ?)",
            [(workspace_id, item_id) for item_id in folder_ids],
        )
        connection.executemany(
            "INSERT INTO workspace_websites (workspace_id, url) VALUES (?, ?)",
            [(workspace_id, url) for url in websites],
        )
        row = connection.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        return {"ok": True, **_workspace_data(connection, row)}


def get_workspace(name):
    """Get a workspace by its name, including linked item names but not filesystem paths."""
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM workspaces WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return _workspace_data(connection, row) if row else None


def get_active_workspace():
    """Return the active workspace with its linked item names."""
    with database_connection() as connection:
        row = connection.execute("SELECT * FROM workspaces WHERE is_active = 1").fetchone()
        return _workspace_data(connection, row) if row else None


def list_workspaces():
    """Return saved workspace names."""
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT name FROM workspaces ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [row["name"] for row in rows]


def open_workspace(name):
    """Activate a workspace and open its linked approved apps, folders, and websites locally."""
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM workspaces WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is None:
            return {"ok": False, "message": f"No saved workspace named {name} was found."}

        active = connection.execute(
            "SELECT * FROM workspaces WHERE is_active = 1"
        ).fetchone()
        if active is not None:
            if active["id"] == row["id"]:
                return {
                    "ok": True,
                    "already_active": True,
                    "name": row["name"],
                    "opened_applications": [],
                    "opened_folders": [],
                    "opened_websites": 0,
                    "issues": [],
                    "message": f"Workspace {row['name']} is already active.",
                }
            return {
                "ok": False,
                "message": f"Workspace {active['name']} is already active.",
            }

        connection.execute("UPDATE workspaces SET is_active = 1 WHERE id = ?", (row["id"],))
        workspace = _workspace_data(connection, row)

    opened_applications = []
    opened_folders = []
    opened_websites = 0
    issues = []

    for application_name in workspace["applications"]:
        result = open_approved_application(application_name)
        if result["ok"]:
            opened_applications.append(application_name)
        else:
            issues.append(result["message"])

    for folder_name in workspace["folders"]:
        result = open_approved_folder(folder_name)
        if result["ok"]:
            opened_folders.append(folder_name)
        else:
            issues.append(result["message"])

    for url in workspace["websites"]:
        try:
            if webbrowser.open(url, new=2):
                opened_websites += 1
            else:
                issues.append("A saved website could not be opened.")
        except (OSError, webbrowser.Error):
            issues.append("A saved website could not be opened.")

    return {
        "ok": True,
        "already_active": False,
        "name": workspace["name"],
        "opened_applications": opened_applications,
        "opened_folders": opened_folders,
        "opened_websites": opened_websites,
        "issues": issues,
        "message": f"Activated workspace {workspace['name']}.",
    }


def update_workspace(name, applications=None, folders=None, websites=None):
    """Replace a workspace's linked approved app, folder, or website names."""
    with database_connection() as connection:
        row = connection.execute(
            "SELECT id FROM workspaces WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row is None:
            return None
        workspace_id = row["id"]

        # Validate every replacement before changing anything, so updates are atomic.
        application_ids = None
        folder_ids = None
        website_urls = None
        if applications is not None:
            application_ids, missing = _approved_ids(
                connection, "approved_applications", _name_list(applications)
            )
            if missing:
                return {"ok": False, "message": f"Application {missing} is not approved."}
        if folders is not None:
            folder_ids, missing = _approved_ids(
                connection, "approved_folders", _name_list(folders)
            )
            if missing:
                return {"ok": False, "message": f"Folder {missing} is not approved."}
        if websites is not None:
            try:
                website_urls = _website_list(websites)
            except ValueError as error:
                return {"ok": False, "message": str(error)}

        if application_ids is not None:
            connection.execute(
                "DELETE FROM workspace_applications WHERE workspace_id = ?", (workspace_id,)
            )
            connection.executemany(
                "INSERT INTO workspace_applications (workspace_id, application_id) VALUES (?, ?)",
                [(workspace_id, item_id) for item_id in application_ids],
            )
        if folder_ids is not None:
            connection.execute(
                "DELETE FROM workspace_folders WHERE workspace_id = ?", (workspace_id,)
            )
            connection.executemany(
                "INSERT INTO workspace_folders (workspace_id, folder_id) VALUES (?, ?)",
                [(workspace_id, item_id) for item_id in folder_ids],
            )
        if websites is not None:
            connection.execute(
                "DELETE FROM workspace_websites WHERE workspace_id = ?", (workspace_id,)
            )
            connection.executemany(
                "INSERT INTO workspace_websites (workspace_id, url) VALUES (?, ?)",
                [(workspace_id, url) for url in website_urls],
            )
        row = connection.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return {"ok": True, **_workspace_data(connection, row)}


def close_workspace():
    """Clear the active workspace. Not currently exposed to Gemini."""
    with database_connection() as connection:
        cursor = connection.execute("UPDATE workspaces SET is_active = 0 WHERE is_active = 1")
        return cursor.rowcount > 0
