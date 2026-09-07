"""CDP event shaping. Network events to observation metadata. No deps."""
from __future__ import annotations
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
