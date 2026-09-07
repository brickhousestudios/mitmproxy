import json
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from threading import Thread

from mitmproxy.aitm.browser.managed import restore_tabs
from mitmproxy.aitm.browser.managed import snapshot_tabs

PAGES = [{"id": "A1", "type": "page", "url": "https://a.example/", "title": "A"},
         {"id": "B2", "type": "page", "url": "https://b.example/", "title": "B"},
         {"id": "D9", "type": "devtools", "url": "devtools://x", "title": "D"}]
OPENED = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        body = json.dumps(PAGES).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        OPENED.append(json.loads(self.rfile.read(n).decode())["url"])
        self.send_response(200)
        self.end_headers()

def _srv():
    s = HTTPServer(("127.0.0.1", 0), H)
    Thread(target=s.serve_forever, daemon=True).start()
    return s

def test_snapshot_filters_pages():
    s = _srv()
    try:
        tabs = snapshot_tabs(f"http://127.0.0.1:{s.server_port}")
        assert [(t["id"], t["url"]) for t in tabs] == [("A1", "https://a.example/"), ("B2", "https://b.example/")]
    finally:
        s.shutdown()

def test_restore_opens_missing_only():
    s = _srv()
    OPENED.clear()
    try:
        base = f"http://127.0.0.1:{s.server_port}"
        n = restore_tabs(base, [{"url": "https://a.example/"}, {"url": "https://c.example/"}])
        assert n == 1 and OPENED == ["https://c.example/"]
    finally:
        s.shutdown()
