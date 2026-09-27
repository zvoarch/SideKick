import os
from .database import database_connection


def add_approved_application(name, path):
    """Add or update a locally approved application. Intended for local settings UI."""
    name = name.strip()
    path = os.path.normpath(os.path.expandvars(os.path.expanduser(path.strip())))
    with database_connection() as connection:
        connection.execute(
            """INSERT INTO approved_applications (name, path, enabled) VALUES (?, ?, 1)
               ON CONFLICT(name) DO UPDATE SET path = excluded.path, enabled = 1""",
            (name, path),
        )
        row = connection.execute(
            "SELECT * FROM approved_applications WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return _application_data(row)


def _application_data(row):
    return {"id": row["id"], "name": row["name"], "path": row["path"],
            "enabled": bool(row["enabled"])}


def get_approved_application(name):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM approved_applications WHERE name = ? COLLATE NOCASE AND enabled = 1",
            (name,),
        ).fetchone()
        return _application_data(row) if row else None


def _normalized_app_name(value):
    """Normalize a label or executable name for safe, exact alias matching."""
    value = os.path.basename(str(value).strip()).casefold()
    stem, _extension = os.path.splitext(value)
    return "".join(character for character in stem if character.isalnum())


def find_approved_application(name):
    """Find an enabled approved app by its label or executable name/alias."""
    app = get_approved_application(name)
    if app is not None:
        return app

    requested = _normalized_app_name(name)
    if not requested:
        return None

    # Edge is commonly registered from its executable as "msedge". Recognize
    # its familiar names while still requiring an explicitly approved Edge app.
    edge_names = {"edge", "msedge", "microsoftedge"}
    requested_names = edge_names if requested in edge_names else {requested}
    matches = []
    for application in list_approved_applications():
        label = _normalized_app_name(application["name"])
        executable = _normalized_app_name(application["path"])
        approved_names = edge_names if executable == "msedge" or label in edge_names else {label, executable}
        if requested_names & approved_names:
            matches.append(application)

    # Do not guess if multiple approved entries could match the alias.
    return matches[0] if len(matches) == 1 else None


def list_approved_applications(include_disabled=False):
    with database_connection() as connection:
        query = "SELECT * FROM approved_applications"
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY name COLLATE NOCASE"
        return [_application_data(row) for row in connection.execute(query).fetchall()]


def set_approved_application_enabled(name, enabled):
    with database_connection() as connection:
        cursor = connection.execute(
            "UPDATE approved_applications SET enabled = ? WHERE name = ? COLLATE NOCASE",
            (int(bool(enabled)), name),
        )
        return cursor.rowcount > 0


def open_application(path):
    """Open a path only when it matches an enabled locally approved application."""
    requested = os.path.normcase(os.path.abspath(os.path.expanduser(path)))
    for application in list_approved_applications():
        approved = os.path.normcase(os.path.abspath(os.path.expanduser(application["path"])))
        if approved == requested:
            os.startfile(application["path"])
            return application
    return None


def open_approved_application(name):
    """Open an enabled approved application by name without exposing its path."""
    application = find_approved_application(name)
    if application is None:
        approved_names = [app["name"] for app in list_approved_applications()]
        if approved_names:
            available = ", ".join(approved_names)
            return {
                "ok": False,
                "message": f"Couldn't match {name} to an approved application. "
                           f"Approved applications: {available}.",
            }
        return {"ok": False, "message": f"{name} is not an approved application."}
    try:
        opened = open_application(application["path"])
    except (OSError, AttributeError):
        return {"ok": False, "message": f"Windows could not open {application['name']}."}
    if opened is None:
        return {"ok": False, "message": f"{application['name']} is not approved."}
    return {"ok": True, "application": opened["name"],
            "message": f"Opened {opened['name']}."}
