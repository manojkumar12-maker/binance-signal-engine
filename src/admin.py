"""Admin agent: overview, controls, and action history."""
import time
from .storage import Storage


class AdminManager:
    def __init__(self, storage: Storage):
        self.storage = storage

    def overview(self, status: dict) -> dict:
        return {
            "system": status,
            "agents": self.storage.get_agent_statuses(),
            "recent_actions": self.storage.recent_admin_actions(limit=20),
        }

    def agent_statuses(self):
        return self.storage.get_agent_statuses()

    def record_action(self, action, actor="admin", details=""):
        self.storage.log_admin_action(action, actor=actor, details=details)
        self.storage.log_event("ADMIN", "", "admin_action", action, details)