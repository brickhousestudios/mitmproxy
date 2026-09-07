"""Stable normalized hashing. Bodies contribute only a short hash, never content."""
from __future__ import annotations

import hashlib
import re

ID_RE = re.compile(r"/[0-9a-fA-F-]{6,}|/\d+")

def route_template(path: str) -> str:
    p = (path or "/")[:512]
    return ID_RE.sub("/:id", p)

def fingerprint(obs: dict) -> str:
    md = obs.get("metadata", {}) if isinstance(obs.get("metadata"), dict) else {}
    parts = [
        str(obs.get("source", "")),
        str(md.get("method", "")),
        str(md.get("host", "")),
        route_template(str(md.get("path", ""))),
        str(md.get("operationName", "")),
        str(md.get("status", "")),
        str(md.get("contentType", "")),
    ]
    body = str(md.get("bodyText", "") or "")
    if body:
        parts.append("b:" + hashlib.sha256(body.encode()).hexdigest()[:8])
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return h
