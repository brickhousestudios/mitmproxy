"""MCP layer test: real client over stdio against real server."""
import asyncio
import json
import os
import sys
import tempfile

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO = "/Users/thebrickhousestudios/GITHUB/mitmproxy"

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

def test_mcp_agent_loop():
    async def run():
        tmp = tempfile.mkdtemp()
        cm, sess = await _session(tmp)
        try:
            tools = await sess.list_tools()
            names = {t.name for t in tools.tools}
            assert {"register_agent", "submit_observation", "agent_summary", "posture"} <= names
            a = _text(await sess.call_tool("register_agent", {"name": "mcp-scout"}))
            assert a["ok"] and a["result"]["id"].startswith("agent_")
            aid = a["result"]["id"]
            s = _text(await sess.call_tool("submit_observation", {
                "session": "sess_mcp", "source": "http", "priority": "interesting",
                "agent": aid, "metadata": {"method": "GET", "host": "app.example",
                "path": "/login", "status": 200}}))
            assert s["ok"] and s["result"]["outcome"] in ("evidenced", "counted"), s
            summ = _text(await sess.call_tool("agent_summary", {"agent": aid}))
            assert summ["ok"] and summ["result"]["observations"] == 1, summ
            post = _text(await sess.call_tool("posture", {}))
            assert post["ok"] and post["result"]["stats"]["ingested"] == 1, post
        finally:
            await sess.__aexit__(None, None, None)
            await cm.__aexit__(None, None, None)
    asyncio.run(run())
