"""Startup checks that keep a second launch from using the wrong token."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from gate_studio.__main__ import existing_agent, wait_for_agent


class _HealthHandler(BaseHTTPRequestHandler):
    status = 401
    payload: object = {"detail": "Unauthorized"}

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        body = json.dumps(self.payload).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


def _serve(status: int, payload: object) -> tuple[ThreadingHTTPServer, Thread]:
    handler = type("Handler", (_HealthHandler,), {"status": status, "payload": payload})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_existing_agent_recognizes_our_health_reply() -> None:
    server, thread = _serve(200, {"ok": True, "version": "0.2.1"})
    try:
        assert existing_agent(server.server_port, "right-token") == ("ours", "0.2.1")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_existing_agent_reports_a_wrong_token_as_other() -> None:
    server, thread = _serve(401, {"detail": "Unauthorized"})
    try:
        assert existing_agent(server.server_port, "wrong-token") == ("other", None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_wait_for_agent_waits_for_an_older_version(monkeypatch) -> None:
    replies = iter([("ours", "0.0.1"), ("free", None)])
    monkeypatch.setattr("gate_studio.__main__.existing_agent", lambda *args: next(replies))
    monkeypatch.setattr("gate_studio.__main__.time.sleep", lambda _seconds: None)
    assert wait_for_agent(8765, "token") == ("free", None)