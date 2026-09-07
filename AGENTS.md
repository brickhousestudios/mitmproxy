- This project uses uv. Always use `uv run pytest` and don't run pytest directly.
- To run all tests: `uv run tox`.
- When adding new source files, additionally run: `uv run tox -e individual_coverage -- FILENAME`.

## aitm subsystem (`mitmproxy/aitm/`)

Agent-In-The-Middle: local passive-by-default instrumentation runtime. Engine = sensor only; the SQLite store is the state authority. See `mitmproxy/aitm/README.md`.

- Fast test lane: `uv run pytest test/aitm -q` (full suite is slow).
- Body capture only for aimed tabs (`policy/aim.py`) with rtype in `browser/cdp.py` `BODY_TYPES` (XHR/Fetch/EventSource); everything else metadata-only.
- bodyText is redacted (`policy/redact.py`) before storage; `reducer/fingerprint.py` keeps only a short body hash, never content.
- Dedupe: identical repeats within TTL collapse to counters; distinct bodies on the same route stay separate deltas.
- Watcher (`browser/cdp.py`) emits on finished/failed with backstop + stop flush; body-fetch failures counted in `CdpWatcher.body_failures`.
- Never run pytest with system python3 (3.9); use uv/venv only.
