"""Aim tests: agent-scoped capture targeting."""
import json
import os
import socket
import tempfile
import time
import uuid

from mitmproxy.aitm.daemon import Daemon
from mitmproxy.aitm.policy.aim import Aim

def _obs(host, path="/", i=0):
    return {"id": "obs_" + uuid.uuid4().hex[:12], "source": "http",
        "timestamp": 1700000000000 + i, "sessionId": "sess_aim",
        "priority": "interesting",
        "metadata": {"method": "GET", "host": host, "path": path, "status": 200}}

def test_aim_matches():
    assert Aim().matches(_obs("anything.example"))
    a = Aim(hosts=["app.example"])
    assert a.matches(_obs("app.example"))
    assert a.matches(_obs("login.app.example"))
    assert not a.matches(_obs("redirector.brave.com"))
    b = Aim(hosts=["app.example"], paths=["/login"])
    assert b.matches(_obs("app.example", "/login"))
    assert not b.matches(_obs("app.example", "/dashboard"))

def test_aim_kills_noise():
    tmp = tempfile.mkdtemp()
    d = Daemon(db=os.path.join(tmp, "aim.db"), sock=os.path.join(tmp, "aim.sock"))
    try:
        d.pipeline.aim.hosts = ["app.example"]
        assert d.pipeline.ingest(_obs("app.example", "/login")).outcome == "evidenced"
        assert d.pipeline.ingest(_obs("redirector.brave.com", "/x")).outcome == "dropped"
        assert d.pipeline.drops.get("aim_miss", 0) == 1
        assert d.pipeline.stats["ingested"] == 1
    finally:
        d.store.close()

def test_aim_runtime_control():
    tmp = tempfile.mkdtemp()
    sock = os.path.join(tmp, "aim2.sock")
    d = Daemon(db=os.path.join(tmp, "aim2.db"), sock=sock)
    d.start()
    def ctl(op, args=None):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(sock)
        s.sendall(json.dumps({"op": op, "args": args or {}}).encode())
        r = json.loads(s.recv(65536).decode())
        s.close()
        return r
    try:
        assert ctl("aim")["result"]["active"] is False
        r = ctl("set_aim", {"hosts": ["target.example"], "paths": ["/app"]})
        assert r["ok"] and r["result"]["active"] is True
        assert d.pipeline.ingest(_obs("target.example", "/app")).outcome == "evidenced"
        assert d.pipeline.ingest(_obs("target.example", "/other")).reason == "aim_miss"
        assert d.pipeline.ingest(_obs("noise.example", "/app")).reason == "aim_miss"
        assert ctl("aim")["result"]["missed"] == 2
        assert ctl("clear_aim")["result"]["active"] is False
        assert d.pipeline.ingest(_obs("noise.example", "/app")).outcome == "evidenced"
    finally:
        d.stop()
