"""Redact before persistence. Headers, query, JSON secrets."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

REDACT_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}
REDACT_QUERY = {"token", "access_token", "api_key", "key", "signature", "sig"}
SECRET_KEY_RE = re.compile(r"(token|secret|passwd|password|api[_-]?key|auth|cookie|bearer|session)", re.I)
REDACTED = "[REDACTED]"

def redact_headers(headers: dict) -> dict:
    out = {}
    for k, v in (headers or {}).items():
        if str(k).lower() in REDACT_HEADERS:
            out[k] = REDACTED
        else:
            out[k] = v
    return out

def redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        q = parse_qsl(parts.query, keep_blank_values=True)
        nq = [(k, REDACTED if k.lower() in REDACT_QUERY else v) for k, v in q]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(nq), parts.fragment))
    except Exception:
        return REDACTED if "token" in url.lower() else url

def redact_obj(o, depth: int = 0):
    if depth > 6:
        return REDACTED
    if isinstance(o, dict):
        return {k: (REDACTED if SECRET_KEY_RE.search(str(k)) else redact_obj(v, depth + 1)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact_obj(v, depth + 1) for v in o[:200]]
    if isinstance(o, str) and len(o) > 4096:
        return o[:4096] + "...[TRUNC]"
    return o
