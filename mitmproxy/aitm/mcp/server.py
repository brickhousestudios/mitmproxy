"""AITM MCP server. Agent memory as tools, stdio transport."""
from __future__ import annotations
import asyncio
import json
import time
import uuid

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ..daemon import Daemon

_daemon: Daemon | None = None

def get_daemon() -> Daemon:
    global _daemon
    if _daemon is None:
        _daemon = Daemon()
        _daemon.start()
    return _daemon

TOOLS = [
    ("register_agent", "Register an agent identity", {"name": {"type": "string"}}),
    ("start_task", "Start a task for an agent", {"agent": {"type": "string"}, "goal": {"type": "string"}}),
    ("submit_observation", "Submit one observation", {
        "session": {"type": "string"}, "source": {"type": "string"},
        "priority": {"type": "string"}, "metadata": {"type": "object"},
        "agent": {"type": "string"}, "task": {"type": "string"}}),
    ("agent_summary", "Memory summary for an agent", {"agent": {"type": "string"}}),
    ("agent_episodes", "Episodes for an agent", {"agent": {"type": "string"}}),
    ("episode_deltas", "Recent deltas for a session", {"session": {"type": "string"}}),
    ("posture", "Daemon posture: stats, queue", {}),
    ("set_aim", "Aim capture at target hosts/paths", {"hosts": {"type": "array"}, "paths": {"type": "array"}}),
    ("clear_aim", "Remove aim, capture everything in scope", {}),
    ("aim", "Show current aim and miss count", {}),
    ("tabs", "List open browser tabs", {}),
    ("aim_tab", "Aim capture at one browser tab", {"target": {"type": "string"}}),
]
async def _on_list_tools(ctx, params) -> types.ListToolsResult:
    out = []
    for name, desc, props in TOOLS:
        req = [k for k in ("name", "agent", "session") if k in props]
        out.append(types.Tool(name=name, description=desc,
            inputSchema={"type": "object", "properties": props, "required": req}))
    return types.ListToolsResult(tools=out)

async def _on_call_tool(ctx, params) -> types.CallToolResult:
    d = get_daemon()
    name, args = params.name, params.arguments or {}
    if name == "register_agent":
        res = {"ok": True, "result": d.agents.register(str(args.get("name", "unnamed")))}
    elif name == "start_task":
        res = {"ok": True, "result": d.agents.start_task(
            str(args.get("agent", "")), str(args.get("goal", "")))}
    elif name == "submit_observation":
        obs = {"id": "obs_" + uuid.uuid4().hex[:12], "source": str(args.get("source", "mcp")),
            "timestamp": int(time.time() * 1000), "sessionId": str(args.get("session", "")),
            "agentId": str(args.get("agent", "") or "agent_unknown"),
            "taskId": args.get("task"), "priority": str(args.get("priority", "routine")),
            "metadata": args.get("metadata") if isinstance(args.get("metadata"), dict) else {}}
        oc = d.pipeline.ingest(obs)
        res = {"ok": True, "result": {"outcome": oc.outcome, "observationId": oc.observationId,
            "deltaId": oc.deltaId, "reason": oc.reason, "capturePosture": oc.capturePosture}}
    elif name in ("agent_summary", "agent_episodes", "episode_deltas", "posture", "set_aim", "clear_aim", "aim", "tabs", "aim_tab"):
        d.pipeline.flush_episodes()
        res = {"ok": True, "result": d.handle_control(
            {"op": name, "args": args})["result"]}
    else:
        res = {"ok": False, "error": f"unknown tool: {name}"}
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(res))])

server = Server("aitm", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)

async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

def main() -> None:
    asyncio.run(_main())
