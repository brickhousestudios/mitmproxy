"""Tab-aim tests: CDP shaping, tab match, watcher flow, fail-soft."""
import asyncio
import os
import tempfile

from mitmproxy.aitm.browser.cdp import CdpWatcher
from mitmproxy.aitm.browser.events import extract_stream_text
from mitmproxy.aitm.browser.events import parse_request
from mitmproxy.aitm.browser.events import parse_response
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

WILL = {"requestId": "R1", "type": "XHR",
        "request": {"url": "https://target.example/app", "method": "POST"}}
RESP = {"requestId": "R1", "response": {"status": 200}}
FIN = {"requestId": "R1"}

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def test_watcher_flow_emits_on_finished_with_body():
    got: list = []
    w = CdpWatcher(got.append)
    w.sessions["S1"] = {"targetId": "TAB1", "title": "Target", "url": "https://target.example/app"}
    async def fake_body(sess, rid):
        assert sess == "S1" and rid == "R1"
        return "hello world"
    w._response_body = fake_body  # type: ignore[method-assign]
    _run(w._on_event({"method": "Network.requestWillBeSent", "sessionId": "S1", "params": WILL}))
    _run(w._on_event({"method": "Network.responseReceived", "sessionId": "S1", "params": RESP}))
    assert got == [], got
    _run(w._on_event({"method": "Network.loadingFinished", "sessionId": "S1", "params": FIN}))
    assert len(got) == 1, got
    obs = got[0]
    assert obs["source"] == "cdp" and obs["sessionId"] == "tab_TAB1"
    assert obs["metadata"]["status"] == 200 and obs["metadata"]["tab"] == "TAB1"
    assert obs["metadata"]["bodyText"] == "hello world"

def test_watcher_flow_failed_has_no_body():
    got: list = []
    w = CdpWatcher(got.append)
    w.sessions["S1"] = {"targetId": "TAB1", "title": "T", "url": "https://target.example/"}
    _run(w._on_event({"method": "Network.requestWillBeSent", "sessionId": "S1", "params": WILL}))
    _run(w._on_event({"method": "Network.loadingFailed", "sessionId": "S1",
                       "params": {"requestId": "R1"}}))
    assert len(got) == 1 and got[0]["metadata"]["status"] == 0
    assert "bodyText" not in got[0]["metadata"]

def test_extract_openai_choices():
    payload = ('data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
               'data: {"choices": [{"delta": {"content": " there"}}]}\n\n'
               'data: [DONE]\n')
    text, trunc = extract_stream_text(payload)
    assert text == "Hello there" and trunc is False

def test_extract_chatgpt_patch_ops():
    payload = ('data: {"v": [{"p": "/a", "o": "append", "v": "foo"}]}\n\n'
               'data: {"v": [{"p": "/a", "o": "append", "v": "bar"}]}\n\n')
    text, trunc = extract_stream_text(payload)
    assert text == "foobar" and trunc is False

def test_extract_garbage_falls_back():
    text, _ = extract_stream_text("not sse at all\njust text")
    assert text == "not sse at all just text"

def test_extract_caps_long_streams():
    payload = "data: {\"choices\": [{\"delta\": {\"content\": \"" + "x" * 7000 + "\"}}]}\n"
    text, trunc = extract_stream_text(payload, cap=100)
    assert len(text) == 100 and trunc is True


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
