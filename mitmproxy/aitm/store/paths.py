"""Store paths. Local-only, capped, no cloud."""
from __future__ import annotations

import os


def base_dir() -> str:
    d = os.environ.get("AITM_DIR", os.path.join(os.path.expanduser("~"), ".aitm"))
    os.makedirs(d, exist_ok=True)
    return d

def db_path() -> str:
    return os.path.join(base_dir(), "aitm.db")

def socket_path() -> str:
    return os.path.join(base_dir(), "aitmd.sock")

def evidence_dir() -> str:
    d = os.path.join(base_dir(), "blobs")
    os.makedirs(d, exist_ok=True)
    return d
