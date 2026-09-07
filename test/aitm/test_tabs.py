"""Tab-aim tests: CDP shaping, tab match, watcher flow, fail-soft."""
import os
import tempfile

from mitmproxy.aitm.browser.cdp import CdpWatcher
from mitmproxy.aitm.browser.events import parse_request, parse_response
from mitmproxy.aitm.daemon import Daemon
from mitmproxy.aitm.policy.aim import Aim

WILL = {"requestId": "R1", "type": "Document",
        "request": {"url": "https://target.example/app", "method": "GET"}}
RESP = {"requestId": "R1", "response": {"status": 200, "url": "https://target.example/app"}}

def test_shape_request():
    pr = parse_request(WILL)
    assert pr and pr["host"] == "target.example" and pr["path"] == "/app"
    assert parse_request({"request": {"url": "chrome://newtab/"}}) is None
    assert parse_request({"request": {"url": "https://x.example/favicon.ico"}}) is None
    assert parse_response(RESP) == {"requestId": "R1", "status": 200}

def test_aim_tabs():
    a = Aim()
    a.tabs = ["TAB1"]
    assert a.active is True
    yes = {"metadata": {"host": "target.example", "tab": "TAB1"}}
    no = {"metadata": {"host": "target.example", "tab": "TAB2"}}
    proxy = {"metadata": {"host": "target.example"}}
    assert a.matches(yes) and not a.matches(no) and not a.matches(proxy)
def test_watcher_flow_no_network():
    got: list = []
    w = CdpWatcher(got.append)
    w.sessions["S1"] = {"targetId": "TAB1", "title": "Target", "url": "https://target.example/app"}
    w._on_event({"method": "Network.requestWillBeSent", "sessionId": "S1", "params": WILL})
    w._on_event({"method": "Network.responseReceived", "sessionId": "S1", "params": RESP})
    assert len(got) == 1, got
    obs = got[0]
    assert obs["source"] == "cdp" and obs["sessionId"] == "tab_TAB1"
    assert obs["metadata"]["status"] == 200 and obs["metadata"]["tab"] == "TAB1"

def test_daemon_tabs_fail_soft():
    tmp = tempfile.mkdtemp()
    os.environ["AITM_CDP"] = "http://127.0.0.1:9"
    d = Daemon(db=os.path.join(tmp, "t.db"), sock=os.path.join(tmp, "t.sock"))
    try:
        assert d.handle_control({"op": "tabs"}) == {"ok": True, "result": []}
        r = d.handle_control({"op": "aim_tab", "args": {"target": "whatever"}})
        assert r["ok"] is False
    finally:
        del os.environ["AITM_CDP"]
        d.store.close()
