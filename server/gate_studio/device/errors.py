"""Device failures the user can act on.

The three cases the brief calls out must stay distinguishable, because they point
at completely different fixes: wrong port/revision, wrong address or sleeping
device, and a device that answers but wants the LocalToken.
"""

from __future__ import annotations

from enum import Enum


class DeviceErrorKind(str, Enum):
    REFUSED = "refused"
    TIMEOUT = "timeout"
    TOKEN = "token"
    DEVICE = "device"
    NETWORK = "network"
    NOT_CONFIGURED = "not_configured"


class DeviceError(Exception):
    def __init__(
        self,
        kind: DeviceErrorKind,
        message: str,
        raw: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.raw = raw
        self.hint = hint

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "message": self.message,
            "raw": self.raw,
            "hint": self.hint,
        }
