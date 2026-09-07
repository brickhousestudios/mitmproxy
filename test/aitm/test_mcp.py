"""MCP adapter test: real client over stdio against real server."""
import asyncio
import json
import os
import sys
import tempfile

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def _session(tmp):
    env = dict(os.environ, AITM_DIR=tmp, PATH=os.environ.get("PATH", ""))
    params = StdioServerParameters(
        command=sys.executable, args=["-c", "from mitmproxy.aitm.mcp.server import main; main()"],
        env=env, cwd=REPO)
    cm = stdio_client(params)
    read, write = await cm.__aenter__()
    sess = ClientSession(read, write)
    await sess.__aenter__()
    await sess.initialize()
    return cm, sess

def _text(res):
    assert len(res.content) == 1
    return json.loads(res.content[0].text)

def test_mcp_query_surface():
    async def run():
        tmp = tempfile.mkdtemp()
        cm, sess = await _session(tmp)
        try:
            tools = await sess.list_tools()
            names = {t.name for t in tools.tools}
            assert {"submit_observation", "episodes", "deltas", "stats", "posture"} <= names
            assert not any("agent" in n for n in names), names
            s = _text(await sess.call_tool("submit_observation", {
                "session": "sess_mcp", "source": "http", "priority": "interesting",
                "task": "task_login_map",
                "metadata": {"method": "GET", "host": "app.example",
                "path": "/login", "status": 200}}))
            assert s["ok"] and s["result"]["outcome"] in ("evidenced", "counted"), s
            eps = _text(await sess.call_tool("episodes", {}))
            assert eps["ok"] and any(r[1] == "sess_mcp" for r in eps["result"]), eps
            dl = _text(await sess.call_tool("deltas", {"session": "sess_mcp"}))
            assert dl["ok"] and len(dl["result"]) >= 1, dl
            post = _text(await sess.call_tool("posture", {}))
            assert post["ok"] and post["result"]["stats"]["ingested"] == 1, post
        finally:
            await sess.__aexit__(None, None, None)
            await cm.__aexit__(None, None, None)
    asyncio.run(run())
