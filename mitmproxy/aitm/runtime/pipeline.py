"""Pipeline: admit→redact→budget→fp/dedupe→delta/counter→store→episode."""
from __future__ import annotations
import queue
import threading
from ..budget.manager import BudgetManager
from ..outcome import IngestOutcome
from ..policy.admission import admit
from ..policy.redact import redact_obj, redact_url
from ..reducer.counters import Counters
from ..reducer.delta import DeltaBuilder
from ..reducer.dedupe import Dedupe
from ..reducer.episode import EpisodeStore
from ..reducer.fingerprint import fingerprint

class Pipeline:
    def __init__(self, store, scope_allow=None, qsize: int = 2048):
        self.store = store
        self.scope_allow = scope_allow
        self.budget = BudgetManager()
        self.budget.limits.ingress_queue_capacity = qsize
        self.dedupe = Dedupe()
        self.deltas = DeltaBuilder()
        self.counters = Counters()
        self.episodes = EpisodeStore(max_episodes=self.budget.limits.max_retained_episodes)
        self.q: queue.Queue = queue.Queue(maxsize=qsize)
        self.stats: dict = {"ingested": 0, "deltas": 0, "suppressed_queue": 0}
        self.drops: dict[str, int] = {}
    def _drop(self, reason: str) -> None:
        self.drops[reason] = self.drops.get(reason, 0) + 1

    def submit(self, obs: dict) -> bool:
        try:
            self.q.put_nowait(obs)
            return True
        except queue.Full:
            self.stats["suppressed_queue"] += 1
            self._drop("queue_full")
            return False

    def start(self) -> None:
        self.running = True
        self.worker = threading.Thread(target=self._drain, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.running = False
        if self.worker is not None:
            self.worker.join(timeout=10)
        self.flush_episodes()

    def _drain(self) -> None:
        while self.running or not self.q.empty():
            try:
                obs = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.ingest(obs)
            except Exception:
                self._drop("ingest_error")
    def ingest(self, obs: dict) -> IngestOutcome:
        session = str(obs.get("sessionId", "sess_default"))
        ok, reason, pri = admit(obs, self.scope_allow)
        if not ok:
            self._drop(reason)
            return IngestOutcome(outcome="dropped", reason=reason)
        md = obs.get("metadata", {})
        md = redact_obj(dict(md) if isinstance(md, dict) else {})
        if isinstance(md.get("path"), str):
            md["path"] = redact_url(md["path"])
        obs = {**obs, "priority": pri, "metadata": md}
        origin = str(md.get("host", "") or obs.get("source", ""))
        if not self.budget.allow_origin(origin):
            self._drop("rate_limited")
            return IngestOutcome(outcome="dropped", reason="rate_limited")
        posture = self.budget.posture_for(pri)
        if posture == "suppressed":
            self._drop("suppressed")
            return IngestOutcome(outcome="dropped", reason="suppressed")
        self.budget.live_obs += 1
        self.stats["ingested"] += 1
        fp = fingerprint(obs)
        dup, n = self.dedupe.check(session + "|" + fp)
        ep = self.episodes.get_or_create(session, obs.get("taskId"))
        ep.setdefault("agentId", str(obs.get("agentId", "") or "agent_unknown"))
        if dup or posture == "counter":
            self.counters.add(session, fp, "dup" if dup else posture)
            self.store.add_counter(session, fp, "dup" if dup else posture, 1)
            self.episodes.note(ep, obs, None)
            return IngestOutcome(outcome="counted", observationId=obs.get("id"), capturePosture=posture, bucket="dup")
        delta = self.deltas.build(obs, fp)
        if delta is None:
            self.counters.add(session, fp, "reduced")
            self.store.add_counter(session, fp, "reduced", 1)
            self.episodes.note(ep, obs, None)
            return IngestOutcome(outcome="reduced", observationId=obs.get("id"), capturePosture=posture)
        if posture in ("full", "preview", "structure"):
            self.store.save_observation(obs, fp, posture)
        self.store.save_delta(delta)
        self.stats["deltas"] += 1
        self.episodes.note(ep, obs, delta)
        if ep["observations"] % 50 == 0:
            self.store.upsert_episode(ep)
        return IngestOutcome(outcome="evidenced", observationId=obs.get("id"), deltaId=delta["id"], capturePosture=posture)

    def flush_episodes(self) -> None:
        for ep in self.episodes.episodes.values():
            try:
                self.store.upsert_episode(ep)
            except Exception:
                self._drop("flush_error")
