"""AITMObserve: thin mitmproxy addon. Emit only, retain nothing."""
from __future__ import annotations
import queue
from .mitmproxy import observation_from_flow_headers

_sink = None
_local: queue.Queue = queue.Queue(maxsize=2048)
suppressed: dict[str, int] = {}

def bind_sink(fn) -> None:
    global _sink
    _sink = fn

def try_emit(obs: dict) -> bool:
    if _sink is not None:
        try:
            if _sink(obs) is not False:
                return True
        except Exception:
            pass
    try:
        _local.put_nowait(obs)
        return True
    except queue.Full:
        k = str(obs.get("source", "http"))
        suppressed[k] = suppressed.get(k, 0) + 1
        return False
class AITMObserve:
    """No retention, no body copy, no db, no LLM, no print."""
    def requestheaders(self, flow):
        try_emit(observation_from_flow_headers(flow, "request_headers"))

    def responseheaders(self, flow):
        try_emit(observation_from_flow_headers(flow, "response_headers"))

    def response(self, flow):
        try_emit(observation_from_flow_headers(flow, "completion"))

    def error(self, flow):
        try_emit(observation_from_flow_headers(flow, "error"))

    def websocket_message(self, flow):
        try_emit(observation_from_flow_headers(flow, "websocket"))

addons = [AITMObserve()]
