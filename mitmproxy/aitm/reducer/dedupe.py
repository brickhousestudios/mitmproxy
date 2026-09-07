"""TTL-bounded dedupe. Collapse floods, keep counters."""
from __future__ import annotations

import time
from collections import OrderedDict


class Dedupe:
    def __init__(self, capacity: int = 4096, ttl_s: int = 60):
        self.cache: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self.capacity = capacity
        self.ttl = ttl_s
        self.hits = 0
        self.misses = 0

    def check(self, fp: str) -> tuple[bool, int]:
        now = time.time()
        if fp in self.cache:
            ts, n = self.cache.pop(fp)
            if now - ts < self.ttl:
                self.cache[fp] = (ts, n + 1)
                self.hits += 1
                return True, n + 1
        self.cache[fp] = (now, 1)
        self.misses += 1
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        return False, 1
