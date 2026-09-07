"""AITM ingest outcomes. Every adapter/reducer must return one."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from typing import Optional

OutcomeKind = Literal["dropped", "counted", "sampled", "reduced", "evidenced", "incident"]

@dataclass
class IngestOutcome:
    outcome: OutcomeKind
    observationId: Optional[str] = None
    deltaId: Optional[str] = None
    evidenceId: Optional[str] = None
    incidentId: Optional[str] = None
    capturePosture: str = "metadata_only"
    reason: str = ""
    bucket: Optional[str] = None
