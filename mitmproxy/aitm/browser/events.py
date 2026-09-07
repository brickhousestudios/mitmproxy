"""CDP event shaping. Network events to observation metadata. No deps."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

SKIP_TYPES = {"Image", "Font", "Media", "Other"}
SKIP_SUFFIX = (".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".mp4", ".css")

def parse_request(params: dict) -> dict | None:
    req = params.get("request", {}) if isinstance(params.get("request"), dict) else {}
    url = str(req.get("url", ""))
    if not url.startswith(("http://", "https://")):
        return None
    parts = urlsplit(url)
    if parts.path.endswith(SKIP_SUFFIX) or parts.path in ("/favicon.ico",):
        return None
    if str(params.get("type", "")) in SKIP_TYPES:
        return None
    return {"method": str(req.get("method", "GET")), "host": parts.hostname or "",
        "path": parts.path or "/", "scheme": parts.scheme,
        "requestId": str(params.get("requestId", "")),
        "rtype": str(params.get("type", ""))}

def parse_response(params: dict) -> dict | None:
    resp = params.get("response", {}) if isinstance(params.get("response"), dict) else {}
    if "status" not in resp:
        return None
    try:
        status = int(resp.get("status", 0))
    except (TypeError, ValueError):
        return None
    return {"requestId": str(params.get("requestId", "")), "status": status}

def extract_stream_text(payload: str, cap: int = 6000) -> tuple[str, bool]:
    """Best-effort readable text from an SSE response body.
    Handles OpenAI choices[].delta.content and ChatGPT webapp
    JSON-patch append ops. Returns (text, truncated)."""
    chunks: list[str] = []
    size = 0
    truncated = False
    for line in payload.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            msg = json.loads(data)
        except Exception:
            continue
        texts = _texts_from_msg(msg)
        for t in texts:
            if size + len(t) > cap:
                need = cap - size
                if need > 0:
                    chunks.append(t[:need])
                    size = cap
                truncated = True
                break
            chunks.append(t)
            size += len(t)
        if truncated:
            break
    if not chunks:
        flat = " ".join(payload.split())
        if len(flat) > cap:
            return flat[:cap], True
        return flat, len(payload) > cap
    return "".join(chunks), truncated


def _texts_from_msg(msg) -> list[str]:
    out: list[str] = []
    if isinstance(msg, dict):
        choices = msg.get("choices")
        if isinstance(choices, list):
            for ch in choices:
                if not isinstance(ch, dict):
                    continue
                delta = ch.get("delta", {}) or {}
                c = delta.get("content") if isinstance(delta, dict) else None
                if isinstance(c, str) and c:
                    out.append(c)
        ops = msg.get("v")
        if isinstance(ops, list):
            for op in ops:
                if isinstance(op, dict) and op.get("o") == "append":
                    v = op.get("v")
                    if isinstance(v, str) and v:
                        out.append(v)
    return out
