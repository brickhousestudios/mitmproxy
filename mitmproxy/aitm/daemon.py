"""Daemon: owns store + pipeline + control socket."""
from __future__ import annotations
from .agent.registry import AgentRegistry
from .control.server import ControlServer
from .runtime.pipeline import Pipeline
from .store import paths
from .store.sqlite import Store

class Daemon:
    def __init__(self, db: str | None = None, sock: str | None = None, scope_allow=None):
        self.db_path = db or paths.db_path()
        self.sock_path = sock or paths.socket_path()
        self.store = Store(self.db_path)
        self.pipeline = Pipeline(self.store, scope_allow=scope_allow)
        self.control = ControlServer(self.sock_path, self)
        self.agents = AgentRegistry(self.store)

    def start(self) -> None:
        self.pipeline.start()
        self.control.start()

    def stop(self) -> None:
        self.pipeline.stop()
        self.control.stop()
        self.store.close()

    def submit(self, obs: dict) -> bool:
        return self.pipeline.submit(obs)
    def handle_control(self, req: dict) -> dict:
        op = str(req.get("op", ""))
        args = req.get("args", {}) if isinstance(req.get("args"), dict) else {}
        if op == "stats":
            return {"ok": True, "result": {
                "stats": self.pipeline.stats, "drops": self.pipeline.drops,
                "posture": self.pipeline.budget.posture(),
                "dedupe": {"hits": self.pipeline.dedupe.hits, "misses": self.pipeline.dedupe.misses},
            }}
        if op == "posture":
            return {"ok": True, "result": {"posture": self.pipeline.budget.posture()}}
        if op == "episodes":
            return {"ok": True, "result": self.store.fetch(
                "SELECT id, session, task, summary, state, obs FROM episodes ORDER BY obs DESC LIMIT ?",
                (int(args.get("limit", 50)),))}
        if op == "deltas":
            return {"ok": True, "result": self.store.fetch(
                "SELECT id, session, subject, kind, summary, confidence FROM deltas WHERE session=? ORDER BY rowid DESC LIMIT ?",
                (str(args.get("session", "")), int(args.get("limit", 100))))}
        if op == "counters":
            return {"ok": True, "result": self.store.fetch(
                "SELECT session, fp, bucket, n FROM counters WHERE session=? LIMIT ?",
                (str(args.get("session", "")), int(args.get("limit", 200))))}
        if op == "register_agent":
            return {"ok": True, "result": self.agents.register(
                str(args.get("name", "unnamed")), str(args.get("kind", "local")),
                args.get("scopes") if isinstance(args.get("scopes"), list) else None)}
        if op == "agent":
            a = self.agents.get(str(args.get("id", "")))
            return {"ok": a is not None, "result": a}
        if op == "start_task":
            return {"ok": True, "result": self.agents.start_task(
                str(args.get("agent", "")), str(args.get("goal", ""))[:512])}
        if op == "agent_episodes":
            return {"ok": True, "result": self.store.fetch(
                "SELECT id, session, task, summary, state, obs FROM episodes WHERE agent=? ORDER BY obs DESC LIMIT ?",
                (str(args.get("agent", "")), int(args.get("limit", 50))))}
        if op == "agent_summary":
            rows = self.store.fetch(
                "SELECT COUNT(*), COALESCE(SUM(obs),0) FROM episodes WHERE agent=?",
                (str(args.get("agent", "")),))
            latest = self.store.fetch(
                "SELECT summary FROM episodes WHERE agent=? ORDER BY obs DESC LIMIT 1",
                (str(args.get("agent", "")),))
            n, total = rows[0] if rows else (0, 0)
            return {"ok": True, "result": {"episodes": n, "observations": total,
                "latest": latest[0][0] if latest else ""}}
        return {"ok": False, "error": f"unknown op: {op}"}
