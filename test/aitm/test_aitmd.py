"""A1: aitmd must not load human flow defaults. Runtime proof."""
import asyncio
import os
import tempfile

from mitmproxy import options
from mitmproxy.tools.aitmd import AitmMaster, aitm_addons

BANNED = {"View", "Dumper", "EventStore", "Save", "SaveHar"}

def _names():
    async def main():
        m = AitmMaster(options.Options())
        try:
            return sorted(type(a).__name__ for a in m.addons.chain)
        finally:
            m.daemon.store.close()
    os.environ["AITM_DIR"] = tempfile.mkdtemp()
    return asyncio.run(main())

def test_no_banned_addons_in_factory():
    assert not (BANNED & {type(a).__name__ for a in aitm_addons()})

def test_no_banned_addons_at_runtime():
    names = _names()
    assert not (BANNED & set(names)), names
    assert "AITMObserve" in names
