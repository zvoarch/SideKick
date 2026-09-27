"""Privacy-limited activity history stored in the local SQLite database."""

from datetime import datetime, timedelta, timezone

from .database import ACTIVITY_RETENTION_DAYS, database_connection

ALLOWED_ACTIVITY_TYPES = {"application_opened", "workspace_opened"}
DEFAULT_ACTIVITY_LIMIT = 5
MAX_ACTIVITY_LIMIT = 10


def _retention_cutoff():
    return (
        datetime.now(timezone.utc) - timedelta(days=ACTIVITY_RETENTION_DAYS)
    ).isoformat(timespec="seconds")


def _purge_old_activity(connection):
    connection.execute(
        "DELETE FROM activity_log WHERE occurred_at < ?",
        (_retention_cutoff(),),
    )


def _safe_subject(subject):
    """Store a display name only, never a directory path supplied by a caller."""
    if not isinstance(subject, str):
        raise ValueError("Activity history needs a display name.")
    subject = subject.strip()
    if not subject:
        raise ValueError("Activity history needs a display name.")
    if "/" in subject or "\\" in subject:
        subject = subject.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if len(subject) > 200:
        subject = subject[:200]
    if not subject:
        raise ValueError("Activity history needs a display name.")
    return subject


def record_activity(activity_type, details):
    """Record only a successful app or workspace open; never store paths/content."""
    if activity_type not in ALLOWED_ACTIVITY_TYPES:
        raise ValueError("Only application and workspace opens can be recorded.")
    subject = _safe_subject(details)
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database_connection() as connection:
        _purge_old_activity(connection)
        connection.execute(
            "INSERT INTO activity_log (activity_type, subject, occurred_at) VALUES (?, ?, ?)",
            (activity_type, subject, occurred_at),
        )
    return {"type": activity_type, "details": subject, "timestamp": occurred_at}


def get_recent_activity(limit=DEFAULT_ACTIVITY_LIMIT):
    """Return a bounded newest-first list of the app/workspace opens we recorded."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_ACTIVITY_LIMIT
    limit = max(0, min(limit, MAX_ACTIVITY_LIMIT))

    with database_connection() as connection:
        _purge_old_activity(connection)
        rows = connection.execute(
            """SELECT activity_type, subject, occurred_at FROM activity_log
               ORDER BY occurred_at DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [
        {"type": row["activity_type"], "details": row["subject"],
         "timestamp": row["occurred_at"]}
        for row in rows
    ]


def get_last_session():
    """Return the most recent recorded event, if there is one."""
    activity = get_recent_activity(1)
    return activity[0] if activity else None
