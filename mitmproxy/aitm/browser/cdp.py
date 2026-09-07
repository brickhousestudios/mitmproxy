"""CDP watcher. Per-tab network attribution via attach+flat sessions.
Research: CDP Target docs (attachToTarget flatten, sessionId events).
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.request
import uuid

import websockets

from .events import parse_request
from .events import parse_response


def list_tabs(cdp_http: str = "http://127.0.0.1:9222") -> list[dict]:
    try:
        with urllib.request.urlopen(cdp_http + "/json/list", timeout=5) as r:
            items = json.loads(r.read().decode())
    except Exception:
        return []
    return [{"id": t.get("id", ""), "title": t.get("title", "")[:120],
             "url": t.get("url", "")[:512], "type": t.get("type", "")}
            for t in items if t.get("type") == "page"]

def browser_ws(cdp_http: str = "http://127.0.0.1:9222") -> str:
    with urllib.request.urlopen(cdp_http + "/json/version", timeout=5) as r:
        return json.loads(r.read().decode())["webSocketDebuggerUrl"]

class CdpWatcher:
    def __init__(self, sink, cdp_http: str = "http://127.0.0.1:9222"):
        self.sink = sink
        self.cdp_http = cdp_http
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.cmd_q: asyncio.Queue | None = None
        self._cmd_id = 0
        self._pending_resp: dict[int, asyncio.Future] = {}
        self.sessions: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.ready: asyncio.Event | None = None
        self.error: str = ""
    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False

    def _thread_main(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.cmd_q = asyncio.Queue()
        self.ready = asyncio.Event()
        try:
            self.loop.run_until_complete(self._run())
        except Exception as e:
            self.error = str(e)[:300]

    def _next_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    async def _send(self, ws, method: str, params: dict | None = None,
                    session: str | None = None) -> dict:
        cid = self._next_id()
        msg: dict = {"id": cid, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        fut: asyncio.Future = self.loop.create_future()  # type: ignore[union-attr]
        self._pending_resp[cid] = fut
        await ws.send(json.dumps(msg))
        return await asyncio.wait_for(fut, timeout=10)

    async def aim_tab(self, target_id: str, title: str = "", url: str = "") -> dict:
        for sess, tab in self.sessions.items():
            if tab["targetId"] == target_id:
                return {"attached": True, "sessionId": sess, "tab": tab}
        res = await self._send(self._ws, "Target.attachToTarget",  # type: ignore[attr-defined]
                               {"targetId": target_id, "flatten": True})
        sess = res.get("result", {}).get("sessionId", "")
        if not sess:
            return {"attached": False, "error": str(res.get("error", "no session"))}
        await self._send(self._ws, "Network.enable", {}, session=sess)  # type: ignore[attr-defined]
        self.sessions[sess] = {"targetId": target_id, "title": title, "url": url}
        return {"attached": True, "sessionId": sess}
    def aim_tab_sync(self, target_id: str, title: str = "", url: str = "",
                       timeout: float = 15) -> dict:
        if not self.loop:
            return {"attached": False, "error": "watcher not started"}
        if self.ready is None:
            return {"attached": False, "error": "watcher not ready"}
        async def _wait_ready():
            try:
                await asyncio.wait_for(self.ready.wait(), timeout=timeout)
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_wait_ready(), self.loop).result(timeout=timeout)
        if self.error:
            return {"attached": False, "error": self.error}
        if not getattr(self, "_ws", None):
            return {"attached": False, "error": "cdp not connected"}
        fut = asyncio.run_coroutine_threadsafe(self.aim_tab(target_id, title, url), self.loop)
        try:
            return fut.result(timeout=timeout)
        except Exception as e:
            return {"attached": False, "error": str(e)[:200]}

    async def _run(self) -> None:
        async with websockets.connect(browser_ws(self.cdp_http), max_size=8 * 1024 * 1024) as ws:
            self._ws = ws
            if self.ready is not None:
                self.ready.set()
            await self._send(ws, "Target.setDiscoverTargets", {"discover": True})
            while self.running:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if "id" in msg and "method" not in msg:
                    fut = self._pending_resp.pop(msg["id"], None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif "method" in msg:
                    self._on_event(msg)

    def _on_event(self, msg: dict) -> None:
        method = msg.get("method", "")
        sess = msg.get("sessionId", "")
        tab = self.sessions.get(sess)
        if method == "Target.attachedToTarget":
            return
        if tab is None:
            return
        params = msg.get("params", {}) if isinstance(msg.get("params"), dict) else {}
        if method == "Network.requestWillBeSent":
            pr = parse_request(params)
            if pr is None:
                return
            if len(self.requests) > 2048:
                self.requests.pop(next(iter(self.requests)))
            self.requests[pr["requestId"] + sess] = {"tab": tab, "req": pr, "at": time.time()}
        elif method in ("Network.responseReceived", "Network.loadingFailed"):
            key = str(params.get("requestId", "")) + sess
            pend = self.requests.pop(key, None)
            if pend is None:
                return
            status = 0
            if method == "Network.responseReceived":
                rs = parse_response(params)
                if rs is None:
                    return
                status = rs["status"]
            req, tab = pend["req"], pend["tab"]
            obs = {"id": "obs_" + uuid.uuid4().hex[:12], "source": "cdp",
                "timestamp": int(time.time() * 1000),
                "sessionId": "tab_" + tab["targetId"][:8],
                "priority": "interesting" if req["rtype"] == "Document" else "normal",
                "metadata": {"method": req["method"], "host": req["host"],
                    "path": req["path"], "status": status,
                    "tab": tab["targetId"], "tabTitle": tab.get("title", "")[:120]}}
            try:
                self.sink(obs)
            except Exception:
                pass
