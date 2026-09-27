from datetime import datetime


activities = []


def record_activity(activity_type, details):
    activity = {"type": activity_type, "details": details, "timestamp": datetime.now()}
    activities.append(activity)
    return activity


def get_recent_activity(limit=10):
    return activities[-limit:]


def get_last_session():
    return activities[-1] if activities else None
