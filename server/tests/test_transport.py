"""Transport tests against a fake Times Gate, so no hardware is required."""

from __future__ import annotations

import base64
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import httpx

from gate_studio.device import transport as transport_module
from gate_studio.device.errors import DeviceError, DeviceErrorKind
from gate_studio.device.transport import (
    HW400,
    HW402,
    DeviceTransport,
    FrameIds,
    lcd_index,
    lcd_mask,
    probe_endpoint,
)

TOKEN = 4242


class _Handler(BaseHTTPRequestHandler):
    received: list[dict] = []
    token = TOKEN

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if payload.get("LocalToken") != self.token:
            self._send(400, {"error_code": "DeviceToken is err"})
            return
        _Handler.received.append(payload)
        command = payload.get("Command")
        if command == "Channel/GetAllConf":
            self._send(200, {"error_code": 0, "DeviceName": "Fake Gate", "Hardware": 400})
        elif command == "Draw/SendHttpGif":
            self._send(200, {"error_code": 0, "PicID": payload.get("PicID")})
        else:
            self._send(200, {"error_code": 0})

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:  # keep test output clean
        pass


@pytest.fixture()
def fake_gate():
    _Handler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def test_get_all_conf_injects_local_token(fake_gate: int) -> None:
    with DeviceTransport("127.0.0.1", fake_gate, TOKEN, HW400) as gate:
        reply = gate.get_all_conf()
    assert reply["error_code"] == 0
    assert _Handler.received[-1]["LocalToken"] == TOKEN


def test_missing_token_is_reported_as_token_error(fake_gate: int) -> None:
    with DeviceTransport("127.0.0.1", fake_gate, None, HW400) as gate:
        with pytest.raises(DeviceError) as info:
            gate.get_all_conf()
    assert info.value.kind is DeviceErrorKind.TOKEN
    assert info.value.raw and "DeviceToken" in info.value.raw


def test_wrong_token_is_reported_as_token_error(fake_gate: int) -> None:
    with DeviceTransport("127.0.0.1", fake_gate, 1, HW400) as gate:
        with pytest.raises(DeviceError) as info:
            gate.get_all_conf()
    assert info.value.kind is DeviceErrorKind.TOKEN


class _FailingClient:
    """Stands in for httpx so error classification is deterministic."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def post(self, *args: object, **kwargs: object) -> object:
        raise self.exc

    def close(self) -> None:
        pass


def test_closed_port_is_reported_as_refused() -> None:
    gate = DeviceTransport(
        "127.0.0.1",
        80,
        TOKEN,
        HW400,
        client=_FailingClient(httpx.ConnectError("WinError 10061: connection refused")),
    )
    with pytest.raises(DeviceError) as info:
        gate.get_all_conf()
    assert info.value.kind is DeviceErrorKind.REFUSED
    assert "127.0.0.1:80" in info.value.message
    assert "port" in (info.value.hint or "").lower()


def test_unreachable_host_is_reported_as_network_error() -> None:
    gate = DeviceTransport(
        "10.0.0.1",
        80,
        TOKEN,
        HW400,
        client=_FailingClient(httpx.ConnectError("No route to host")),
    )
    with pytest.raises(DeviceError) as info:
        gate.get_all_conf()
    assert info.value.kind is DeviceErrorKind.NETWORK


def test_silent_socket_is_reported_as_timeout() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        with DeviceTransport("127.0.0.1", port, TOKEN, HW400, timeout=0.4) as gate:
            with pytest.raises(DeviceError) as info:
                gate.get_all_conf()
        assert info.value.kind is DeviceErrorKind.TIMEOUT
    finally:
        listener.close()


def test_send_frame_encodes_jpeg_and_panel_mask(fake_gate: int) -> None:
    with DeviceTransport("127.0.0.1", fake_gate, TOKEN, HW400) as gate:
        gate.send_frame(b"\xff\xd8fake-jpeg", panels=[2], pic_id=7)
    sent = _Handler.received[-1]
    assert sent["Command"] == "Draw/SendHttpGif"
    assert sent["PicWidth"] == 128
    assert sent["PicNum"] == 1
    assert sent["PicOffset"] == 0
    assert sent["PicID"] == 7
    assert sent["LcdArray"] == [0, 0, 1, 0, 0]
    assert base64.b64decode(sent["PicData"]) == b"\xff\xd8fake-jpeg"


def test_frame_ids_increase_monotonically() -> None:
    ids = FrameIds(start=5)
    allocated = [ids.next() for _ in range(3)]
    assert allocated == [5, 6, 7]
    assert ids.current == 8


def test_lcd_helpers() -> None:
    assert lcd_mask([0, 4]) == [1, 0, 0, 0, 1]
    assert lcd_index(3) == 3
    with pytest.raises(ValueError):
        lcd_index(5)


def test_probe_endpoint_reports_ok_and_name(fake_gate: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(transport_module.ENDPOINTS, HW400, (fake_gate, "/post"))
    outcome = probe_endpoint("127.0.0.1", HW400, TOKEN)
    assert outcome.ok is True
    assert outcome.device_name == "Fake Gate"
    assert outcome.port == fake_gate


def test_probe_endpoint_reports_token_without_failing(fake_gate: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(transport_module.ENDPOINTS, HW402, (fake_gate, "/divoom_api"))
    outcome = probe_endpoint("127.0.0.1", HW402, None)
    assert outcome.ok is False
    assert outcome.kind == DeviceErrorKind.TOKEN.value
