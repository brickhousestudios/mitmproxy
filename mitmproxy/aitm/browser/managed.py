"""Managed browser lifecycle. AITM owns the debug relaunch: snapshot, ephemeral
CDP port, restore, guaranteed teardown. No lingering exposure."""
from __future__ import annotations
import json
import re
import subprocess
import time
import urllib.request

BRAVE_BIN = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
PROFILE = "Brave-Browser"

def app_support() -> str:
    import os
    return os.path.expanduser("~/Library/Application Support/BraveSoftware")

def quit_brave(timeout: float = 20) -> bool:
    subprocess.run(["osascript", "-e", 'tell application "Brave Browser" to quit'],
                   capture_output=True, timeout=30)
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(["pgrep", "-f", "Brave Browser.app"], capture_output=True)
        if r.returncode != 0:
            return True
        time.sleep(1)
    return False

def launch_debug(extra: list[str] | None = None, timeout: float = 40) -> str:
    cmd = [BRAVE_BIN, f"--user-data-dir={app_support()}/{PROFILE}",
           "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check"]
    cmd += extra or []
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    port = ""
    deadline = time.time() + timeout
    buf = ""
    while time.time() < deadline and not port:
        import select
        ready, _, _ = select.select([p.stderr], [], [], 2)
        if ready:
            buf += p.stderr.read(4096) or ""
            m = re.search(r"DevTools listening on ws://127\.0\.0\.1:(\d+)", buf)
            if m:
                port = m.group(1)
    if not port:
        raise RuntimeError("no CDP port in Brave stderr: " + buf[-300:])
    return f"http://127.0.0.1:{port}"
def snapshot_tabs(cdp_http: str) -> list[dict]:
    try:
        with urllib.request.urlopen(cdp_http + "/json/list", timeout=5) as r:
            items = json.loads(r.read().decode())
    except Exception:
        return []
    return [{"id": t.get("id", ""), "url": t.get("url", ""), "title": t.get("title", "")}
            for t in items if t.get("type") == "page"]

def restore_tabs(cdp_http: str, snapshot: list[dict]) -> int:
    current = {t["url"] for t in snapshot_tabs(cdp_http)}
    opened = 0
    for tab in snapshot:
        url = tab.get("url", "")
        if url and url not in ("about:blank", "chrome://newtab/") and url not in current:
            try:
                data = json.dumps({"url": url}).encode()
                req = urllib.request.Request(cdp_http + "/json/new", data=data,
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).read()
                opened += 1
            except Exception:
                pass
    return opened

def launch_normal() -> bool:
    p = subprocess.Popen([BRAVE_BIN, f"--user-data-dir={app_support()}/{PROFILE}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        r = subprocess.run(["pgrep", "-f", "Brave Browser.app"], capture_output=True)
        if r.returncode == 0:
            return True
        time.sleep(1)
    return False
class ManagedSession:
    """Owns a debug-flagged Brave lifetime. Teardown always restores normal."""
    def __init__(self, snapshot: list[dict] | None = None):
        self.snapshot = snapshot or []
        self.cdp_http = ""
        self.restored = 0

    def __enter__(self) -> "ManagedSession":
        if not quit_brave():
            raise RuntimeError(" Brave  refused to quit; aborting, nothing changed")
        self.cdp_http = launch_debug()
        self.restored = restore_tabs(self.cdp_http, self.snapshot)
        return self

    def __exit__(self, *exc) -> None:
        try:
            fresh = snapshot_tabs(self.cdp_http) if self.cdp_http else []
            for tab in fresh:
                if tab.get("url", "") not in {s.get("url", "") for s in self.snapshot}:
                    try:
                        urllib.request.urlopen(
                            self.cdp_http + "/json/close/" + tab["id"], timeout=5).read()
                    except Exception:
                        pass
        finally:
            quit_brave()
            launch_normal()
