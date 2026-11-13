"""Talking to a Times Gate over the local network."""

from .discovery import discover, discover_cloud, scan_subnet
from .errors import DeviceError, DeviceErrorKind
from .transport import (
    ENDPOINTS,
    HW400,
    HW402,
    DeviceTransport,
    FrameIds,
    ProbeOutcome,
    lcd_mask,
    probe_endpoint,
    probe_host,
)

__all__ = [
    "ENDPOINTS",
    "HW400",
    "HW402",
    "DeviceError",
    "DeviceErrorKind",
    "DeviceTransport",
    "FrameIds",
    "ProbeOutcome",
    "discover",
    "discover_cloud",
    "lcd_mask",
    "probe_endpoint",
    "probe_host",
    "scan_subnet",
]
