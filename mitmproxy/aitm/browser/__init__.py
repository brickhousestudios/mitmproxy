"""AITM browser package. Tabs as first-class aim targets via CDP."""
from .events import parse_request, parse_response

__all__ = ["parse_request", "parse_response"]
