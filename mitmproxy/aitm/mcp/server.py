"""AITM MCP adapter. Exposes the AITM control/query surface as stdio tools.
MCP is a client of AITM: no persistence, ownership, or memory semantics here."""
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
    ("submit_observation", "Submit one observation to the AITM pipeline", {
        "session": {"type": "string"}, "source": {"type": "string"},
        "priority": {"type": "string"}, "metadata": {"type": "object"},
        "task": {"type": "string"}}),
    ("episodes", "Episode summaries, most recent first", {}),
    ("deltas", "Recent deltas for a session", {"session": {"type": "string"}}),
    ("counters", "Suppression counters for a session", {"session": {"type": "string"}}),
    ("stats", "Pipeline stats, drops, posture, dedupe", {}),
    ("posture", "Current capture posture", {}),
    ("set_scope", "Set capture scope: target hosts/paths", {"hosts": {"type": "array"}, "paths": {"type": "array"}}),
    ("clear_scope", "Remove capture scope, observe everything admitted", {}),
    ("scope", "Show current capture scope and miss count", {}),
    ("tabs", "List open browser tabs (CDP sensor)", {}),
    ("scope_tab", "Scope capture to one browser tab", {"target": {"type": "string"}}),
]

async def _on_list_tools(ctx, params) -> types.ListToolsResult:
    out = []
    for name, desc, props in TOOLS:
        req = [k for k in ("session", "target") if k in props]
        out.append(types.Tool(name=name, description=desc,
            inputSchema={"type": "object", "properties": props, "required": req}))
    return types.ListToolsResult(tools=out)

async def _on_call_tool(ctx, params) -> types.CallToolResult:
    d = get_daemon()
    name, args = params.name, params.arguments or {}
    if name == "submit_observation":
        obs = {"id": "obs_" + uuid.uuid4().hex[:12], "source": str(args.get("source", "mcp")),
            "timestamp": int(time.time() * 1000), "sessionId": str(args.get("session", "")),
            "taskId": args.get("task"), "priority": str(args.get("priority", "routine")),
            "metadata": args.get("metadata") if isinstance(args.get("metadata"), dict) else {}}
        oc = d.pipeline.ingest(obs)
        res = {"ok": True, "result": {"outcome": oc.outcome, "observationId": oc.observationId,
            "deltaId": oc.deltaId, "reason": oc.reason, "capturePosture": oc.capturePosture}}
    elif name in ("episodes", "deltas", "counters", "stats", "posture",
                  "set_scope", "clear_scope", "scope", "tabs", "scope_tab"):
        d.pipeline.flush_episodes()
        op = {"set_scope": "set_aim", "clear_scope": "clear_aim",
              "scope": "aim", "scope_tab": "aim_tab"}.get(name, name)
        res = d.handle_control({"op": op, "args": args})
    else:
        res = {"ok": False, "error": f"unknown tool: {name}"}
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(res))])

server = Server("aitm", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)

async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

def main() -> None:
    asyncio.run(_main())
