"""Pipeline unit tests: admit, redact, budget, dedupe, delta, store."""
import os
import tempfile
import time
import uuid

from mitmproxy.aitm.daemon import Daemon
from mitmproxy.aitm.runtime.pipeline import Pipeline
from mitmproxy.aitm.store.sqlite import Store


def _obs(**kw):
    d = {
        "id": "obs_" + uuid.uuid4().hex[:12],
        "source": "http",
        "timestamp": int(time.time() * 1000),
        "sessionId": "sess_test",
        "priority": "normal",
        "metadata": {"method": "GET", "host": "example.com", "path": "/a", "stage": "completion", "status": 200},
    }
    d.update(kw)
    return d

def _pipe():
    tmp = tempfile.mkdtemp()
    store = Store(os.path.join(tmp, "t.db"))
    return Pipeline(store), store

def test_static_denied():
    p, _ = _pipe()
    out = p.ingest(_obs(metadata={"path": "/favicon.ico", "host": "x.com"}))
    assert out.outcome == "dropped" and out.reason == "drop_static"
def test_redact_before_store():
    p, store = _pipe()
    md = {"method": "GET", "host": "example.com", "path": "/a?token=secret123", "api_key": "zzz"}
    p.ingest(_obs(metadata=md))
    rows = store.fetch("SELECT meta FROM observations")
    assert rows, "expected stored observation"
    assert "secret123" not in rows[0][0] and "zzz" not in rows[0][0]

def test_rate_limit_drops():
    p, _ = _pipe()
    p.budget.limits.max_event_rate_per_origin = 5
    outs = [p.ingest(_obs()) for _ in range(10)]
    assert any(o.outcome == "dropped" and o.reason == "rate_limited" for o in outs)

def test_dedupe_counts_flood():
    p, store = _pipe()
    for _ in range(20):
        p.ingest(_obs())
    assert p.stats["ingested"] == 20
    assert p.counters.total >= 19
    assert store.fetch("SELECT SUM(n) FROM counters")[0][0] >= 19
def test_control_roundtrip():
    import json
    import socket
    tmp = tempfile.mkdtemp()
    d = Daemon(db=os.path.join(tmp, "c.db"), sock=os.path.join(tmp, "c.sock"))
    d.start()
    try:
        d.submit(_obs())
        deadline = time.time() + 5
        while d.pipeline.stats["ingested"] == 0 and time.time() < deadline:
            time.sleep(0.05)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(os.path.join(tmp, "c.sock"))
        s.sendall(json.dumps({"op": "stats"}).encode())
        res = json.loads(s.recv(65536).decode())
        s.close()
        assert res["ok"] and res["result"]["stats"]["ingested"] >= 1
    finally:
        d.stop()
def _ctl(sock_path: str, op: str, args: dict | None = None) -> dict:
    import json
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    s.sendall(json.dumps({"op": op, "args": args or {}}).encode())
    res = json.loads(s.recv(65536).decode())
    s.close()
    return res

def test_control_episodes_deltas():
    tmp = tempfile.mkdtemp()
    sock = os.path.join(tmp, "e.sock")
    d = Daemon(db=os.path.join(tmp, "e.db"), sock=sock)
    d.start()
    try:
        d.submit(_obs())
        deadline = time.time() + 5
        while d.pipeline.stats["ingested"] == 0 and time.time() < deadline:
            time.sleep(0.05)
        d.pipeline.flush_episodes()
        eps = _ctl(sock, "episodes", {"limit": 10})
        assert eps["ok"] and any(r[1] == "sess_test" for r in eps["result"]), eps
        dlt = _ctl(sock, "deltas", {"session": "sess_test"})
        assert dlt["ok"] and len(dlt["result"]) >= 1, dlt
    finally:
        d.stop()


def test_redact_body_text_patterns():
    from mitmproxy.aitm.policy.redact import redact_body_text
    assert "topsecret" not in redact_body_text("Bearer topsecret123456 rest")
    assert redact_body_text('"api_key":"abcd12345678"').count("[REDACTED]") == 1
    assert redact_body_text("no secrets here: hello world") == "no secrets here: hello world"


def test_bodytext_scoped_and_scrubbed():
    p, store = _pipe()
    p.aim.tabs.append("TAB1")
    secret_body = '"access_token": "sk-abcdefgh123456", "note": "keep me"'
    out = p.ingest(_obs(metadata={"method": "POST", "host": "app.example", "path": "/api",
                                  "status": 200, "tab": "TAB1", "bodyText": secret_body}))
    assert out.outcome == "evidenced", out
    # Non-aimed tab never admits while tab scope is active (drop-at-door).
    out2 = p.ingest(_obs(metadata={"method": "POST", "host": "app.example", "path": "/api2",
                                   "status": 200, "tab": "TAB2", "bodyText": secret_body}))
    assert out2.outcome == "dropped" and out2.reason == "aim_miss", out2
    # No tab scope: bodyText is stripped from admitted traffic.
    p2, store2 = _pipe()
    p2.ingest(_obs(metadata={"method": "POST", "host": "app.example", "path": "/api3",
                             "status": 200, "bodyText": secret_body}))
    rows = store.fetch("SELECT meta FROM observations ORDER BY rowid")
    assert len(rows) == 1, rows
    kept = rows[0][0]
    assert "sk-abcdefgh123456" not in kept and "[REDACTED]" in kept and "keep me" in kept, kept
    rows2 = store2.fetch("SELECT meta FROM observations")
    assert len(rows2) == 1 and "bodyText" not in rows2[0][0], rows2
