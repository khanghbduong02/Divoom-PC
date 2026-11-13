"""Finding the device: Divoom's LAN discovery call, then a subnet fallback."""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor

import httpx

from .errors import DeviceError, DeviceErrorKind
from .transport import HW400, HW402, ProbeOutcome, probe_endpoint

CLOUD_URL = "https://app.divoom-gz.com/Device/ReturnSameLANDevice"


def discover_cloud(timeout: float = 6.0) -> list[dict[str, object]]:
    """Ask Divoom's service for devices on this LAN — the call the phone app makes."""
    try:
        response = httpx.post(
            CLOUD_URL,
            json={},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        data = response.json()
    except httpx.HTTPError as exc:
        raise DeviceError(
            DeviceErrorKind.NETWORK,
            "Could not reach Divoom's discovery service.",
            hint="Check this PC's internet connection, or enter the device IP manually.",
        ) from exc
    except ValueError as exc:
        raise DeviceError(
            DeviceErrorKind.NETWORK,
            "Divoom's discovery service returned an unexpected reply.",
        ) from exc

    devices = data.get("DeviceList") or data.get("device_list") or []
    found: list[dict[str, object]] = []
    for entry in devices:
        if not isinstance(entry, dict):
            continue
        ip = entry.get("IP") or entry.get("Ip") or entry.get("ip")
        if not ip:
            continue
        found.append(
            {
                "name": entry.get("DeviceName") or "",
                "ip": str(ip),
                "mac": entry.get("Mac") or entry.get("MAC") or "",
                "device_id": entry.get("DeviceId") or entry.get("DeviceID"),
                "hardware": entry.get("Hardware"),
            }
        )
    return found


def local_prefixes() -> list[str]:
    """``a.b.c`` prefixes of this machine's LAN interfaces."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a hard dependency
        return []

    prefixes: list[str] = []
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family != socket.AF_INET or not address.address:
                continue
            try:
                parsed = ipaddress.IPv4Address(address.address)
            except ValueError:
                continue
            if parsed.is_loopback or parsed.is_link_local:
                continue
            prefix = ".".join(address.address.split(".")[:3])
            if prefix not in prefixes:
                prefixes.append(prefix)
    return prefixes


def _probe_first_answering(
    host: str,
    local_token: int | None,
    timeout: float,
) -> ProbeOutcome | None:
    for protocol in (HW400, HW402):
        outcome = probe_endpoint(host, protocol, local_token, timeout=timeout)
        # A token rejection still proves a Times Gate is there.
        if outcome.ok or outcome.kind in ("token", "device"):
            return outcome
    return None


def scan_subnet(
    prefix: str,
    local_token: int | None = None,
    timeout: float = 0.7,
    workers: int = 64,
) -> list[ProbeOutcome]:
    """Probe ``prefix.1``-``prefix.254`` on both revisions.

    Only used when cloud discovery finds nothing (isolated LAN, cloud blocked);
    it is a few hundred short requests, so keep the timeout small.
    """
    base = prefix.strip().rstrip(".")
    hosts = [f"{base}.{last}" for last in range(1, 255)]
    results: list[ProbeOutcome] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for outcome in pool.map(lambda host: _probe_first_answering(host, local_token, timeout), hosts):
            if outcome is not None:
                results.append(outcome)
    return results


def discover(
    host: str | None = None,
    local_token: int | None = None,
) -> dict[str, object]:
    """Best-effort device discovery for the setup wizard."""
    payload: dict[str, object] = {"cloud": [], "scan": [], "errors": []}
    errors: list[str] = payload["errors"]  # type: ignore[assignment]

    if host:
        payload["scan"] = [
            probe_endpoint(host, protocol, local_token).as_dict() for protocol in (HW400, HW402)
        ]
        return payload

    try:
        payload["cloud"] = discover_cloud()
    except DeviceError as exc:
        errors.append(exc.message)

    if not payload["cloud"]:
        for prefix in local_prefixes()[:2]:
            findings = scan_subnet(prefix, local_token)
            payload["scan"] = [finding.as_dict() for finding in findings]  # type: ignore[list-item]
            if findings:
                break
    return payload
