from .activity import get_recent_activity
from .tasks import get_tasks
from .workspaces import get_active_workspace


def get_current_context():
    return {
        "active_workspace": get_active_workspace(),
        "recent_activity": get_recent_activity(),
        "tasks": get_tasks(),
    }
