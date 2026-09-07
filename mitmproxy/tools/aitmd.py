"""aitmd: headless agent-first runtime. No human flow defaults."""
from __future__ import annotations
from mitmproxy import addons
from mitmproxy import master
from mitmproxy import options
from mitmproxy.addons import errorcheck
from mitmproxy.addons import save
from mitmproxy.addons import savehar
from mitmproxy.aitm.adapter import observe
from mitmproxy.aitm.daemon import Daemon

BANNED = (save.Save, savehar.SaveHar)

def aitm_addons():
    return [a for a in addons.default_addons() if not isinstance(a, BANNED)]

class AitmMaster(master.Master):
    def __init__(self, options: options.Options, loop=None) -> None:
        super().__init__(options, event_loop=loop, with_termlog=True)
        self.daemon = Daemon()
        observe.bind_sink(self.daemon.submit)
        self.addons.add(*aitm_addons())
        self.addons.add(
            observe.AITMObserve(),
            errorcheck.ErrorCheck(),
        )
    async def running(self):
        self.daemon.start()
        await super().running()

    async def done(self):
        try:
            self.daemon.stop()
        finally:
            await super().done()

def aitmd(args=None) -> int | None:  # pragma: no cover
    from mitmproxy.tools import cmdline
    from mitmproxy.tools import main
    main.run(AitmMaster, cmdline.mitmdump, args)
    return None
