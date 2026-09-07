"""Delta builder. First-seen + priority rules, deterministic text."""
from __future__ import annotations
import time
import uuid
from collections import OrderedDict

class DeltaBuilder:
    def __init__(self, capacity: int = 8192):
        self.seen: OrderedDict[tuple[str, str], float] = OrderedDict()
        self.capacity = capacity

    def _remember(self, session: str, fp: str) -> bool:
        key = (session, fp)
        first = key not in self.seen
        self.seen[key] = time.time()
        if len(self.seen) > self.capacity:
            self.seen.popitem(last=False)
        return first

    def build(self, obs: dict, fp: str) -> dict | None:
        session = str(obs.get("sessionId", "sess_default"))
        pri = str(obs.get("priority", "normal"))
        first = self._remember(session, fp)
        if pri == "noise" and not first:
            return None
        if pri == "normal" and not first:
            return None
        md = obs.get("metadata", {}) if isinstance(obs.get("metadata"), dict) else {}
        if pri in ("interesting", "critical"):
            kind = "notable"
        elif first:
            kind = "new"
        else:
            kind = "change"
        summary = "{m} {h}{p} [{s}]".format(
            m=md.get("method", md.get("stage", "event")),
            h=md.get("host", ""),
            p=md.get("path", ""),
            s=md.get("status", md.get("stage", "")),
        )[:512]
        return {
            "id": "delta_" + uuid.uuid4().hex[:12],
            "sessionId": session,
            "subject": fp,
            "kind": kind,
            "summary": summary,
            "confidence": 0.9 if first else 0.6,
            "evidenceIds": [],
        }
