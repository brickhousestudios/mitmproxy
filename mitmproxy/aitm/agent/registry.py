"""Agent/task registry. Attribution root for all semantic state."""
from __future__ import annotations
import json
import time
import uuid
from .models import UNKNOWN_AGENT

SCHEMA_EXTRA = """
CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY, name TEXT, kind TEXT, scopes TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, agent TEXT, goal TEXT, state TEXT, created INTEGER);
"""

class AgentRegistry:
    def __init__(self, store):
        self.store = store
        store.db.executescript(SCHEMA_EXTRA)
        store.db.commit()

    def register(self, name: str, kind: str = "local", scopes: list | None = None) -> dict:
        agent = {
            "id": "agent_" + uuid.uuid4().hex[:12],
            "name": name, "kind": kind,
            "scopes": scopes or ["observe", "query"],
            "created_at": int(time.time()),
        }
        self.store._q("INSERT OR IGNORE INTO agents VALUES(?,?,?,?,?)", (
            agent["id"], name, kind, json.dumps(agent["scopes"]), agent["created_at"]))
        return agent
    def get(self, agent_id: str) -> dict | None:
        rows = self.store.fetch("SELECT id, name, kind, scopes, created FROM agents WHERE id=?", (agent_id,))
        if not rows:
            return None
        i, name, kind, scopes, created = rows[0]
        return {"id": i, "name": name, "kind": kind, "scopes": json.loads(scopes), "created_at": created}

    def start_task(self, agent_id: str, goal: str = "") -> dict:
        task = {
            "id": "task_" + uuid.uuid4().hex[:12],
            "agentId": agent_id, "goal": goal[:512],
            "state": "active", "created_at": int(time.time()),
        }
        self.store._q("INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?)", (
            task["id"], agent_id, task["goal"], "active", task["created_at"]))
        return task

    def resolve(self, obs: dict) -> tuple[str, str | None]:
        agent = str(obs.get("agentId", "") or UNKNOWN_AGENT)
        task = obs.get("taskId")
        return agent, (str(task) if task else None)
