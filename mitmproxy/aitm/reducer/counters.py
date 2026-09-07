"""Counter buckets. Floods become numbers, never retained events."""
from __future__ import annotations
from collections import defaultdict

class Counters:
    def __init__(self):
        self.buckets: dict[tuple[str, str, str], int] = defaultdict(int)
        self.total = 0

    def add(self, session: str, fp: str, bucket: str = "default", n: int = 1) -> int:
        key = (session, fp, bucket)
        self.buckets[key] += n
        self.total += n
        return self.buckets[key]

    def snapshot(self, session: str | None = None) -> dict:
        out: dict = {}
        for (sess, fp, bucket), n in self.buckets.items():
            if session is not None and sess != session:
                continue
            out.setdefault(sess, {}).setdefault(fp, {})[bucket] = n
        return out
