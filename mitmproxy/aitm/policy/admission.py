"""Admission: deterministic first-pass. Scope, allow/deny, source."""
from __future__ import annotations

ALLOWED_SOURCES = {"http", "websocket", "sse", "cdp", "tool", "filesystem", "model", "synthetic"}
DENY_HOSTS_SUFFIX = (".ico", ".png", ".jpg", ".woff", ".woff2", ".ttf", ".mp4")

def admit(obs: dict, scope_allow: list[str] | None = None) -> tuple[bool, str, str]:
    src = str(obs.get("source", ""))
    if src not in ALLOWED_SOURCES:
        return False, "deny_source", "noise"
    md = obs.get("metadata", {}) if isinstance(obs.get("metadata"), dict) else {}
    path = str(md.get("path", ""))
    host = str(md.get("host", ""))
    if path.endswith(DENY_HOSTS_SUFFIX) or path in ("/favicon.ico",):
        return False, "drop_static", "noise"
    if scope_allow:
        if host and not any(host.endswith(s) or host == s for s in scope_allow):
            return False, "out_of_scope", "noise"
    pri = str(obs.get("priority", "normal"))
    if pri not in ("noise", "normal", "interesting", "critical"):
        pri = "normal"
    return True, "admitted", pri
