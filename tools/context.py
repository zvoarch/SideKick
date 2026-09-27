from .tasks import get_tasks
from .workspaces import get_active_workspace


def get_current_context():
    return {
        "active_workspace": get_active_workspace(),
        "tasks": get_tasks(),
    }
