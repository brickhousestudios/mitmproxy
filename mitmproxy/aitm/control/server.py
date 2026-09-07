"""Unix-socket JSON-lines API. Agents query semantic state here."""
from __future__ import annotations
import json
import os
import socket
import threading

class ControlServer:
    def __init__(self, sock_path: str, daemon):
        self.sock_path = sock_path
        self.daemon = daemon
        self.thread: threading.Thread | None = None
        self.running = False

    def start(self) -> None:
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.sock_path)
        self._srv.listen(16)
        self._srv.settimeout(0.5)
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        srv = self._srv
        while self.running:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                try:
                    req = json.loads(conn.recv(65536).decode())
                    res = self.daemon.handle_control(req)
                except Exception as e:
                    res = {"ok": False, "error": str(e)[:512]}
                conn.sendall(json.dumps(res).encode())
        srv.close()

    def stop(self) -> None:
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=5)
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass
