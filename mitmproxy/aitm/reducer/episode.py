"""Episodes: one per (session, task) pair, deterministic summary, bounded."""
from __future__ import annotations

import uuid
from collections import Counter
from collections import OrderedDict


class EpisodeStore:
    def __init__(self, max_episodes: int = 200):
        self.episodes: OrderedDict[str, dict] = OrderedDict()
        self.by_session: dict[tuple[str, str], str] = {}
        self.max_episodes = max_episodes

    def get_or_create(self, session: str, task: str | None = None) -> dict:
        key = (session, task or "")
        if key in self.by_session:
            return self.episodes[self.by_session[key]]
        ep: dict = {
            "id": "ep_" + uuid.uuid4().hex[:12],
            "sessionId": session,
            "taskId": task,
            "goal": None,
            "summary": "",
            "state": "active",
            "observations": 0,
            "deltas": [],
            "kinds": Counter(),
            "sources": Counter(),
        }
        self.episodes[ep["id"]] = ep
        self.by_session[key] = ep["id"]
        while len(self.episodes) > self.max_episodes:
            old_id, _ = self.episodes.popitem(last=False)
            for s, eid in list(self.by_session.items()):
                if eid == old_id:
                    del self.by_session[s]
        return ep

    def note(self, ep: dict, obs: dict, delta: dict | None) -> None:
        ep["observations"] += 1
        ep["sources"][str(obs.get("source", ""))] += 1
        if delta is not None:
            ep["deltas"].append(delta["id"])
            ep["kinds"][str(delta.get("kind", ""))] += 1
        src = ", ".join(f"{k}={v}" for k, v in sorted(ep["sources"].items()))
        knd = ", ".join(f"{k}={v}" for k, v in sorted(ep["kinds"].items()))
        ep["summary"] = f"obs={ep['observations']} src[{src}] delta[{knd}]"
