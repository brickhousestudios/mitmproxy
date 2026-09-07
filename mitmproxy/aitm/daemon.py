"""Daemon: owns store + pipeline + control socket."""
from __future__ import annotations
import os
import time
from .agent.registry import AgentRegistry
from .browser.cdp import CdpWatcher, list_tabs
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
        self.cdp_url = os.environ.get("AITM_CDP", "http://127.0.0.1:9222")
        self.watcher: CdpWatcher | None = None

    def start(self) -> None:
        self.pipeline.start()
        self.control.start()

    def stop(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
        self.pipeline.stop()
        self.control.stop()
        self.store.close()

    def submit(self, obs: dict) -> bool:
        return self.pipeline.submit(obs)
    def handle_control(self, req: dict) -> dict:
        op = str(req.get("op", ""))
        args = req.get("args", {}) if isinstance(req.get("args"), dict) else {}
        if op == "posture":
            return {"ok": True, "result": {"stats": self.pipeline.stats,
                "queue_depth": self.pipeline.q.qsize()}}
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
        if op == "set_aim":
            hosts = args.get("hosts") or []
            paths = args.get("paths") or []
            self.pipeline.aim.tabs = []
            self.pipeline.aim.hosts = [h.strip().lower().lstrip(".") for h in hosts if h]
            self.pipeline.aim.paths = [p for p in paths if p]
            return {"ok": True, "result": self.pipeline.aim.describe()}
        if op == "clear_aim":
            self.pipeline.aim.hosts = []
            self.pipeline.aim.paths = []
            self.pipeline.aim.tabs = []
            return {"ok": True, "result": self.pipeline.aim.describe()}
        if op == "aim":
            d = self.pipeline.aim.describe()
            d["missed"] = self.pipeline.drops.get("aim_miss", 0)
            return {"ok": True, "result": d}
        if op == "tabs":
            return {"ok": True, "result": list_tabs(self.cdp_url)}
        if op == "aim_tab":
            want = str(args.get("target", ""))
            tabs = list_tabs(self.cdp_url)
            tab = next((x for x in tabs if x["id"] == want or want in (x["url"], x["title"])), None)
            if tab is None:
                return {"ok": False, "error": f"no such tab: {want[:80]}"}
            if self.watcher is None:
                self.watcher = CdpWatcher(self.pipeline.submit, self.cdp_url)
                self.watcher.start()
                for _ in range(50):
                    if self.watcher.loop is not None:
                        break
                    time.sleep(0.1)
            res = self.watcher.aim_tab_sync(tab["id"], tab["title"], tab["url"]) if self.watcher else {}
            if not res.get("attached"):
                return {"ok": False, "error": str(res.get("error", "attach failed"))[:200]}
            self.pipeline.aim.tabs = [tab["id"]]
            self.pipeline.aim.hosts = []
            self.pipeline.aim.paths = []
            out = self.pipeline.aim.describe()
            out["tab"] = tab
            return {"ok": True, "result": out}
        return {"ok": False, "error": f"unknown op: {op}"}
