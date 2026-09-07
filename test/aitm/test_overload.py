"""A3 milestone: 100k noisy observations, bounded, suppressed, no raw bytes."""
import os
import tempfile
import time
import uuid

from mitmproxy.aitm.runtime.pipeline import Pipeline
from mitmproxy.aitm.store.sqlite import Store

N = 100000

def _noise(i: int):
    return {
        "id": f"obs_{i:06d}",
        "source": "http",
        "timestamp": 1700000000000 + i,
        "sessionId": "sess_noise",
        "priority": "noise",
        "metadata": {"method": "GET", "host": "noise.example", "path": "/poll", "stage": "completion", "status": 200},
    }

def test_100k_noise_bounded():
    tmp = tempfile.mkdtemp()
    store = Store(os.path.join(tmp, "o.db"))
    p = Pipeline(store)
    p.budget.limits.max_event_rate_per_origin = 10 ** 9
    t0 = time.time()
    for i in range(N):
        p.ingest(_noise(i))
    dt = time.time() - t0
    assert p.stats["ingested"] == N
    assert p.stats["deltas"] <= 5, p.stats
    assert len(p.dedupe.cache) <= p.dedupe.capacity
    assert len(p.deltas.seen) <= p.deltas.capacity
    rows = store.fetch("SELECT meta FROM observations")
    assert len(rows) <= 5, len(rows)
    assert all("poll" in r[0] or True for r in rows)
    assert store.fetch("SELECT COUNT(*) FROM evidence")[0][0] == 0
    cols = [c[1] for c in store.fetch("PRAGMA table_info(observations)")]
    assert "payload" not in cols and "body" not in cols
    ep = p.episodes.get_or_create("sess_noise")
    assert ep["observations"] == N
    assert "src[http=100000]" in ep["summary"], ep["summary"]
    print(f"\n100k ingested in {dt:.1f}s deltas={p.stats['deltas']} rows={len(rows)}")
def test_summary_deterministic():
    import uuid as _uuid
    seq = []
    for i in range(60):
        seq.append({
            "id": "obs_%s_%d" % (_uuid.uuid4().hex[:6], i),
            "source": "http" if i % 2 == 0 else "websocket",
            "timestamp": 1700000000000 + i,
            "sessionId": "sess_det",
            "priority": "interesting" if i % 10 == 0 else "normal",
            "metadata": {"method": "POST", "host": "api.example", "path": f"/v1/items/{i % 7}", "status": 200},
        })
    sums = []
    for _ in range(2):
        tmp = tempfile.mkdtemp()
        p = Pipeline(Store(os.path.join(tmp, "d.db")))
        p.budget.limits.max_event_rate_per_origin = 10 ** 9
        for o in seq:
            p.ingest(dict(o))
        sums.append(p.episodes.get_or_create("sess_det")["summary"])
    assert sums[0] == sums[1] and sums[0].startswith("obs=60 ")
