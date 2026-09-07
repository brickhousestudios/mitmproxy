"""Convert mitmproxy hooks/flows to Observations. Metadata only."""
from __future__ import annotations
import time
import uuid

def observation_from_flow_headers(flow, stage: str) -> dict:
    req = getattr(flow, "request", None)
    resp = getattr(flow, "response", None)
    md: dict = {"stage": stage}
    try:
        if req is not None:
            md["method"] = getattr(req, "method", "")
            md["host"] = getattr(req, "host", "")
            md["path"] = getattr(req, "path", "")[:512]
            md["scheme"] = getattr(req, "scheme", "")
        if resp is not None:
            md["status"] = getattr(resp, "status_code", 0)
    except Exception:
        md["extract"] = "minimal"
    return {
        "id": "obs_" + uuid.uuid4().hex[:12],
        "source": "websocket" if stage == "websocket" else "http",
        "timestamp": int(time.time() * 1000),
        "sessionId": "sess_default",
        "priority": "normal",
        "metadata": md,
    }
