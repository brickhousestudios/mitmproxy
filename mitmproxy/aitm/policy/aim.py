"""Aim: agent-scoped capture targeting. Host suffix + path prefix."""
from __future__ import annotations

class Aim:
    def __init__(self, hosts: list[str] | None = None, paths: list[str] | None = None):
        self.hosts = [h.strip().lower().lstrip(".") for h in (hosts or []) if h]
        self.paths = [p for p in (paths or []) if p]
        self.tabs: list[str] = []

    @property
    def active(self) -> bool:
        return bool(self.hosts or self.paths or self.tabs)

    def matches(self, obs: dict) -> bool:
        if not self.active:
            return True
        md = obs.get("metadata", {}) if isinstance(obs.get("metadata"), dict) else {}
        if self.tabs:
            return str(md.get("tab", "")) in self.tabs
        host = str(md.get("host", "")).lower()
        path = str(md.get("path", ""))
        if self.hosts:
            if not any(host == h or host.endswith("." + h) or host.endswith(h) for h in self.hosts):
                return False
        if self.paths:
            if not any(path.startswith(p) for p in self.paths):
                return False
        return True

    def describe(self) -> dict:
        return {"active": self.active, "hosts": self.hosts, "paths": self.paths, "tabs": self.tabs}
