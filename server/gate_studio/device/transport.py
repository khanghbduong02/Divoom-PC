"""HTTP transport for the Times Gate local API.

Two hardware revisions expose the same JSON commands on different endpoints:

* HW 400 -> ``POST http://<ip>/post``
* HW 402 -> ``POST http://<ip>:9000/divoom_api``

Newer firmware also rejects local calls that omit an integer ``LocalToken``
(the number shown in the Divoom phone app), so the token is injected into every
request body here.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from threading import Lock

import httpx

from .errors import DeviceError, DeviceErrorKind

HW400 = "hw400"
HW402 = "hw402"

#: protocol -> (default port, path)
ENDPOINTS: dict[str, tuple[int, str]] = {
    HW400: (80, "/post"),
    HW402: (9000, "/divoom_api"),
}

PANEL_COUNT = 5


def lcd_mask(panels: list[int] | tuple[int, ...]) -> list[int]:
    """Length-5 mask selecting which panels a frame applies to."""
    wanted = {int(p) for p in panels}
    return [1 if index in wanted else 0 for index in range(PANEL_COUNT)]


def lcd_index(panel: int) -> int:
    """Single-panel addressing used by several device commands."""
    if not 0 <= int(panel) < PANEL_COUNT:
        raise ValueError(f"panel must be 0..{PANEL_COUNT - 1}")
    return int(panel)


class FrameIds:
    """Monotonic PicID sequence.

    The device leaves a panel stuck on "loading" if an ID is reused, so IDs are
    allocated once per process and the device's counter is reset at startup.
    """

    def __init__(self, start: int = 1) -> None:
        self._value = int(start)
        self._lock = Lock()

    @property
    def current(self) -> int:
        with self._lock:
            return self._value

    def next(self) -> int:
        with self._lock:
            value = self._value
            self._value += 1
            return value


@dataclass
class ProbeOutcome:
    host: str
    port: int
    protocol: str
    ok: bool
    kind: str
    message: str
    raw: str | None = None
    device_name: str | None = None
    extra: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "ok": self.ok,
            "kind": self.kind,
            "message": self.message,
            "raw": self.raw,
            "device_name": self.device_name,
        }


def _token_error(error_code: object, message: str) -> bool:
    text = f"{error_code} {message}".lower()
    return "token" in text


def _device_name(payload: dict[str, object]) -> str | None:
    for key in ("DeviceName", "device_name", "ShortName", "Name", "DeviceId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class DeviceTransport:
    """One configured connection to one device."""

    def __init__(
        self,
        host: str,
        port: int | None = None,
        local_token: int | None = None,
        protocol: str | None = None,
        timeout: float = 4.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.host = host.strip()
        if protocol is None:
            protocol = HW402 if (port or 0) >= 9000 else HW400
        if protocol not in ENDPOINTS:
            raise ValueError(f"unknown protocol {protocol!r}")
        self.protocol = protocol
        self.port = int(port or ENDPOINTS[protocol][0])
        self.local_token = int(local_token) if local_token not in (None, "") else None
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    # -- plumbing ------------------------------------------------------
    @property
    def path(self) -> str:
        return ENDPOINTS[self.protocol][1]

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{self.path}"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "DeviceTransport":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        body = dict(payload)
        if self.local_token is not None:
            body["LocalToken"] = self.local_token
        command = str(body.get("Command", ""))
        try:
            response = self._client.post(self.url, json=body, timeout=self.timeout)
        except httpx.ConnectTimeout as exc:
            raise DeviceError(
                DeviceErrorKind.TIMEOUT,
                f"No reply from {self.host} within {self.timeout:g}s while connecting to port {self.port}.",
                hint=(
                    "The device is off, asleep or on another network — or this port is closed "
                    "(wrong hardware revision: 80 for HW 400, 9000 for HW 402)."
                ),
            ) from exc
        except httpx.ReadTimeout as exc:
            raise DeviceError(
                DeviceErrorKind.TIMEOUT,
                f"{self.host}:{self.port} accepted the connection but did not answer in "
                f"{self.timeout:g}s.",
                hint="The device may be busy or asleep. Try again, then power-cycle it.",
            ) from exc
        except httpx.ConnectError as exc:
            detail = str(exc).lower()
            if "refused" in detail or "10061" in detail:
                raise DeviceError(
                    DeviceErrorKind.REFUSED,
                    f"Nothing is listening on {self.host}:{self.port}.",
                    hint=(
                        "The host is reachable but this port is closed. The Times Gate has two "
                        "hardware revisions: try the other port (80 for HW 400, 9000 for HW 402)."
                    ),
                ) from exc
            raise DeviceError(
                DeviceErrorKind.NETWORK,
                f"Could not reach {self.host}.",
                hint="Is the device powered on and on the same Wi-Fi network as this PC?",
            ) from exc
        except httpx.HTTPError as exc:
            raise DeviceError(
                DeviceErrorKind.NETWORK,
                f"Connection to {self.host} failed: {exc.__class__.__name__}.",
            ) from exc

        raw = response.text[:2000]
        try:
            data = response.json()
        except ValueError as exc:
            raise DeviceError(
                DeviceErrorKind.DEVICE,
                f"{self.host} answered HTTP {response.status_code} with something that is not JSON.",
                raw=raw,
                hint="That usually means the wrong port is serving a different service.",
            ) from exc
        if not isinstance(data, dict):
            raise DeviceError(
                DeviceErrorKind.DEVICE,
                f"Unexpected reply from {self.host}.",
                raw=raw,
            )

        error_code = data.get("error_code", data.get("ErrorCode", 0))
        message = str(data.get("error_message") or data.get("ErrorMessage") or "")
        if _token_error(error_code, message):
            raise DeviceError(
                DeviceErrorKind.TOKEN,
                "The device answered but rejected the request: LocalToken is missing or wrong.",
                raw=raw,
                hint=(
                    "Open the Divoom app, select the device, and copy the number shown under its "
                    "settings into the LocalToken field."
                ),
            )
        if error_code not in (0, "0", None, ""):
            raise DeviceError(
                DeviceErrorKind.DEVICE,
                f"Device rejected {command or 'the request'}: {message or error_code}",
                raw=raw,
            )
        return data

    # -- commands ------------------------------------------------------
    def get_all_conf(self) -> dict[str, object]:
        return self._post({"Command": "Channel/GetAllConf"})

    def reset_pic_id(self) -> dict[str, object]:
        return self._post({"Command": "Draw/ResetHttpGifId"})

    def send_frame(
        self,
        jpeg: bytes,
        panels: list[int],
        pic_id: int,
        speed_ms: int = 100,
        width: int = 128,
    ) -> dict[str, object]:
        """Push one 128x128 JPEG to the selected panels.

        ``PicNum`` is the total frame count of this transfer; a still image is 1.
        """
        if not jpeg:
            raise ValueError("frame payload is empty")
        return self._post(
            {
                "Command": "Draw/SendHttpGif",
                "PicNum": 1,
                "PicWidth": width,
                "PicOffset": 0,
                "PicID": int(pic_id),
                "PicSpeed": int(speed_ms),
                "LcdArray": lcd_mask(panels),
                "PicData": base64.b64encode(jpeg).decode("ascii"),
            }
        )


def probe_endpoint(
    host: str,
    protocol: str,
    local_token: int | None = None,
    timeout: float = 2.5,
) -> ProbeOutcome:
    """Ask one revision's endpoint whether a Times Gate answers there."""
    port = ENDPOINTS[protocol][0]
    outcome = ProbeOutcome(
        host=host,
        port=port,
        protocol=protocol,
        ok=False,
        kind="unknown",
        message="",
    )
    try:
        with DeviceTransport(host, port, local_token, protocol, timeout=timeout) as transport:
            reply = transport.get_all_conf()
            outcome.ok = True
            outcome.kind = "ok"
            outcome.device_name = _device_name(reply)
            outcome.raw = str(reply)[:2000]
            outcome.message = (
                f"Times Gate answered on port {port} ({protocol.upper()})."
                if outcome.device_name is None
                else f"{outcome.device_name} answered on port {port} ({protocol.upper()})."
            )
    except DeviceError as exc:
        outcome.kind = exc.kind.value
        outcome.message = exc.message
        outcome.raw = exc.raw
        outcome.extra["hint"] = exc.hint
    return outcome


def probe_host(
    host: str,
    local_token: int | None = None,
    timeout: float = 2.5,
) -> list[ProbeOutcome]:
    """Probe both hardware revisions so the wizard can keep whichever answered."""
    return [
        probe_endpoint(host, HW400, local_token, timeout),
        probe_endpoint(host, HW402, local_token, timeout),
    ]
