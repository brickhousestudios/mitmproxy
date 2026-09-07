"""AITM stable semantic types. No raw bodies here."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal
from typing import Optional

Source = Literal["http", "websocket", "sse", "cdp", "tool", "filesystem", "model", "synthetic"]
Priority = Literal["noise", "normal", "interesting", "critical"]

@dataclass
class Observation:
    id: str
    source: Source
    timestamp: int
    sessionId: str
    taskId: Optional[str] = None
    priority: Priority = "normal"
    payloadRef: Optional[str] = None
    metadata: dict = field(default_factory=dict)

@dataclass
class StateDelta:
    id: str
    sessionId: str
    subject: str = ""
    kind: str = "content"
    summary: str = ""
    confidence: float = 0.0
    evidenceIds: list = field(default_factory=list)

@dataclass
class EvidenceRef:
    id: str
    representation_hash: str = ""
    sensitivity: str = "private"
    retention: str = "session"
    access: str = "meta"
    location: str = ""
    expires_at: Optional[int] = None

@dataclass
class Episode:
    id: str
    sessionId: str
    taskId: Optional[str] = None
    goal: Optional[str] = None
    summary: str = ""
    state: str = "active"
    observations: list = field(default_factory=list)
    deltas: list = field(default_factory=list)
    decisions: list = field(default_factory=list)

@dataclass
class Relation:
    frm: str = ""
    to: str = ""
    kind: str = "correlated_with"
    confidence: float = 0.0
    evidence_ids: list = field(default_factory=list)
