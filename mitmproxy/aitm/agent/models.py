"""Agent-system models. Identity, tasks, scopes."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Agent:
    id: str
    name: str = ""
    kind: str = "local"
    scopes: list = field(default_factory=list)
    created_at: int = 0

@dataclass
class AgentTask:
    id: str
    agentId: str = ""
    goal: str = ""
    state: str = "active"
    created_at: int = 0

UNKNOWN_AGENT = "agent_unknown"
