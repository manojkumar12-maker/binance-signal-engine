"""Agent status model and helpers."""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AgentStatus:
    name: str
    status: str = "IDLE"
    last_activity: Optional[float] = None
    last_success: Optional[float] = None
    error_message: str = ""
    tasks_completed: int = 0
    current_activity: str = ""

    def to_dict(self):
        return asdict(self)