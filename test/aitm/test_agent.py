"""Agent-system tests: registry, attribution, agent-speaking API."""
import json
import os
import socket
import tempfile
import time
import uuid

from mitmproxy.aitm.daemon import Daemon

def _ctl(sock, op, args=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock)
    s.sendall(json.dumps({"op": op, "args": args or {}}).encode())
    res = json.loads(s.recv(65536).decode())
    s.close()
    return res

def test_agent_memory_loop():
    tmp = tempfile.mkdtemp()
    sock = os.path.join(tmp, "a.sock")
    d = Daemon(db=os.path.join(tmp, "a.db"), sock=sock)
    d.start()
    try:
        a = _ctl(sock, "register_agent", {"name": "scout"})
        assert a["ok"] and a["result"]["id"].startswith("agent_")
        t = _ctl(sock, "start_task", {"agent": a["result"]["id"], "goal": "map login flow"})
        assert t["ok"] and t["result"]["id"].startswith("task_")
        aid, tid = a["result"]["id"], t["result"]["id"]
        for i in range(5):
            d.submit({"id": "obs_" + uuid.uuid4().hex[:12], "source": "http",
                "timestamp": 1700000000000 + i, "sessionId": "sess_scout",
                "agentId": aid, "taskId": tid, "priority": "interesting",
                "metadata": {"method": "GET", "host": "app.example", "path": "/login", "status": 200}})
        deadline = time.time() + 5
        while d.pipeline.stats["ingested"] < 5 and time.time() < deadline:
            time.sleep(0.05)
        d.pipeline.flush_episodes()
        eps = _ctl(sock, "agent_episodes", {"agent": aid})
        assert eps["ok"] and any(r[1] == "sess_scout" for r in eps["result"]), eps
        summ = _ctl(sock, "agent_summary", {"agent": aid})
        assert summ["ok"] and summ["result"]["observations"] == 5, summ
        other = _ctl(sock, "agent_episodes", {"agent": "agent_nobody"})
        assert other["ok"] and other["result"] == []
    finally:
        d.stop()
