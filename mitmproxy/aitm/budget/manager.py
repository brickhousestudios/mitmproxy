"""BudgetManager: global RAM/disk/queue/capture authority."""
from __future__ import annotations
from dataclasses import dataclass, field
import time

POSTURES = ("full", "preview", "structure", "metadata", "counter", "suppressed")

@dataclass
class Limits:
    max_live_observations: int = 5000
    max_live_raw_bytes: int = 134217728
    max_session_raw_bytes: int = 536870912
    max_event_rate_per_origin: int = 100
    max_body_capture_bytes: int = 262144
    max_websocket_frame_capture: int = 16384
    max_retained_episodes: int = 200
    max_disk_evidence_bytes: int = 10737418240
    ingress_queue_capacity: int = 2048
    reducer_queue_capacity: int = 1024
    store_queue_capacity: int = 256

@dataclass
class BudgetManager:
    limits: Limits = field(default_factory=Limits)
    live_obs: int = 0
    live_bytes: int = 0
    disk_bytes: int = 0
    origin_hits: dict = field(default_factory=dict)
    drops: dict = field(default_factory=dict)

    def posture(self) -> str:
        if self.live_obs > self.limits.max_live_observations * 0.9:
            return "counter"
        if self.live_bytes > self.limits.max_live_raw_bytes * 0.8:
            return "metadata"
        if self.live_obs > self.limits.max_live_observations * 0.6:
            return "structure"
        return "full"

    def allow_origin(self, origin: str) -> bool:
        now = int(time.time())
        w, c = self.origin_hits.get(origin, (now, 0))
        if now != w:
            self.origin_hits[origin] = (now, 1)
            return True
        if c >= self.limits.max_event_rate_per_origin:
            self.drops[origin] = self.drops.get(origin, 0) + 1
            return False
        self.origin_hits[origin] = (w, c + 1)
        return True

    def posture_for(self, priority: str) -> str:
        base = self.posture()
        if priority == "critical":
            return "full" if base != "suppressed" else "preview"
        if priority == "noise" and base in ("full", "preview"):
            return "counter"
        mapping = {"full": "full", "preview": "preview", "structure": "structure"}
        return mapping.get(base, base)
