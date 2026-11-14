"""Talking to a Times Gate over the local network."""

from .discovery import discover, discover_cloud, scan_subnet
from .errors import DeviceError, DeviceErrorKind
from .external import ExternalSnapshot, ExternalWatchError, diff_snapshots, fetch_snapshot
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
    "ExternalSnapshot",
    "ExternalWatchError",
    "FrameIds",
    "ProbeOutcome",
    "diff_snapshots",
    "discover",
    "discover_cloud",
    "fetch_snapshot",
    "lcd_mask",
    "probe_endpoint",
    "probe_host",
    "scan_subnet",
]
