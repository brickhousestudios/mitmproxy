# aitm — Agent In The Middle

Local, passive-by-default instrumentation runtime built on the mitmproxy engine.
The engine is a sensor only; the SQLite store is the only state authority.

## Architecture

```
HTTP traffic (mitmproxy addon)  ─┐
                                ├─> Pipeline.ingest ─> Store (SQLite)
CDP tab capture (watcher)       ─┘       │
                                  admit -> redact -> dedupe -> delta -> episode
```

- `adapter/` — mitmproxy addon shaping proxied HTTP into observations
- `browser/` — CDP per-tab capture:
  - `cdp.py` `CdpWatcher`: attach+flatten sessions, request/response tracking, emits on `loadingFinished`/`loadingFailed`, backstop flush for stale pending, stop-flush, `body_failures` counter
  - `events.py`: event shaping, `parse_request` (rtype, skip lists), `extract_stream_text` (SSE/JSON body extraction, 6000-char cap)
  - `managed.py`: Chrome launcher
- `budget/` — per-origin rate limiting and capture posture (full/preview/structure/counter/suppressed)
- `policy/` — static admission, tab aim (`Aim.tabs`), bodyText redaction
- `reducer/` — fingerprint (normalized route + short body hash), dedupe (TTL), delta (first-seen per fingerprint), counters, episodes
- `runtime/pipeline.py` — ingest flow wiring
- `store/` — SQLite persistence (observations, deltas, counters, episodes)
- `control/`, `mcp/` — control socket and MCP server

## Semantics

- **Tab scoping.** When `Aim.tabs` is set, only traffic from those tabs is admitted (drop at door); bodyText is kept for aimed tabs and stripped otherwise.
- **Body gating.** `BODY_TYPES = {XHR, Fetch, EventSource}` — only these resource types get `getResponseBody`. Document/Script/Stylesheet are metadata-only. Payload cap 1 MiB.
- **Fingerprints.** sha256 over (source, method, host, templated route, operation, status, content-type, short body hash). Body contributes 8 hex chars — distinct bodies on one route stay distinct; identical repeats collapse.
- **Dedupe.** Identical fingerprint within TTL → counter bucket, not stored again.
- **bodyTruncated.** Set from the real stream-cap flag returned by body extraction, not a length guess.
- **Redaction.** bodyText passes `policy/redact.py` scrubbing before storage; fingerprints hash the post-redaction text.

## Tests

Fast lane (this subsystem):

    uv run pytest test/aitm -q

The full repo suite is slow; use `uv run pytest` / `uv run tox` sparingly. Never run pytest with the system python3 (3.9) — runtime union types break collection; use uv/venv.
