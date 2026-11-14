"""Read the Divoom app's screen layout from Divoom's cloud.

The Times Gate local API can draw to a screen but cannot read one back.  Its
``Channel/GetIndex`` reply is also empty on HW 402 firmware, so a local poll
cannot tell whether the phone app replaced a screen.  The app's own layout is
kept in Divoom's cloud, however, and ``Channel/Get5LcdInfoV2`` exposes it
without an account.  We use that only as a change signal: when a face changes,
the local agent pauses that screen instead of overwriting it two seconds later.

This is deliberately an external-state reader, not a source of truth for what
our own local pushes drew.  Divoom's cloud does not update for local API writes,
which is exactly what lets us distinguish the phone app from this editor.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

PANEL_COUNT = 5
CLOUD_STATE_URL = "https://app.divoom-gz.com/Channel/Get5LcdInfoV2"


class ExternalWatchError(Exception):
    """The Divoom cloud could not describe the app-side screen layout."""


@dataclass(frozen=True)
class ExternalSnapshot:
    """One reading of the active Divoom-app layout."""

    channel_type: int
    clock_id: int
    preset: int | None
    #: ``(channel, clock id, image id)`` for each of the five screens
    faces: tuple[tuple[int, int, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "channel_type": self.channel_type,
            "clock_id": self.clock_id,
            "preset": self.preset,
            "faces": [list(face) for face in self.faces],
        }


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_snapshot(payload: object) -> ExternalSnapshot:
    """Turn ``Channel/Get5LcdInfoV2`` JSON into a comparable snapshot."""
    if not isinstance(payload, dict):
        raise ExternalWatchError("Divoom's cloud returned an unexpected reply.")

    code = payload.get("ReturnCode", payload.get("error_code", 0))
    if code not in (0, "0", None, ""):
        message = str(payload.get("ReturnMessage") or payload.get("error_message") or code)
        raise ExternalWatchError(f"Divoom's cloud rejected the request: {message}")

    channel_type = _as_int(payload.get("ChannelType"), 0)
    clock_id = _as_int(payload.get("ClockId"), 0)
    raw_preset = payload.get("LcdIndependence")
    preset = _as_int(raw_preset) if raw_preset not in (None, "", 0, "0") else None

    presets = payload.get("LcdIndependenceList") or []
    active = None
    if isinstance(presets, list):
        for entry in presets:
            if not isinstance(entry, dict):
                continue
            if preset is not None and _as_int(entry.get("LcdIndependence")) == preset:
                active = entry
                break
        if active is None and channel_type == 1:
            # Some firmware omits the active preset id but still returns exactly
            # one preset.  Accept that instead of disabling the watch.
            candidates = [entry for entry in presets if isinstance(entry, dict)]
            if len(candidates) == 1:
                active = candidates[0]
                preset = _as_int(active.get("LcdIndependence"), 0) or None

    if channel_type == 1 and active is None:
        raise ExternalWatchError("Divoom's cloud did not report an active screen layout.")

    faces: list[tuple[int, int, str]] = []
    if active is not None:
        lcds = active.get("LcdList") or []
        if not isinstance(lcds, list):
            lcds = []
        for index in range(PANEL_COUNT):
            face = lcds[index] if index < len(lcds) and isinstance(lcds[index], dict) else {}
            faces.append(
                (
                    _as_int(face.get("LcdSelectIndex"), 0),
                    _as_int(face.get("LcdClockId"), 0),
                    str(face.get("ClockImagePixelId") or ""),
                )
            )
    else:
        # Whole-display face: one clock spans all five screens.
        faces = [(0, clock_id, "")] * PANEL_COUNT

    return ExternalSnapshot(
        channel_type=channel_type,
        clock_id=clock_id,
        preset=preset,
        faces=tuple(faces),
    )


def diff_snapshots(previous: ExternalSnapshot | None, current: ExternalSnapshot) -> list[int]:
    """Return the screens whose app-side face changed between two readings."""
    if previous is None:
        return []
    if previous.channel_type != current.channel_type:
        return list(range(PANEL_COUNT))
    if current.channel_type == 0:
        return list(range(PANEL_COUNT)) if previous.clock_id != current.clock_id else []
    if previous.preset != current.preset:
        return list(range(PANEL_COUNT))
    return [
        index
        for index in range(PANEL_COUNT)
        if previous.faces[index] != current.faces[index]
    ]


def fetch_snapshot(
    device_id: int,
    client: httpx.Client | None = None,
    timeout: float = 6.0,
) -> ExternalSnapshot:
    """Ask Divoom's cloud what the phone app last put on each screen."""
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        try:
            reply = http.post(
                CLOUD_STATE_URL,
                json={"DeviceId": int(device_id), "DeviceType": "LCD"},
                timeout=timeout,
            )
            payload = reply.json()
        except httpx.HTTPError as exc:
            raise ExternalWatchError(
                "Could not reach Divoom's cloud to check for phone-app changes."
            ) from exc
        except ValueError as exc:
            raise ExternalWatchError(
                "Divoom's cloud returned something that was not JSON."
            ) from exc
        return parse_snapshot(payload)
    finally:
        if owns_client:
            http.close()


__all__ = [
    "CLOUD_STATE_URL",
    "ExternalSnapshot",
    "ExternalWatchError",
    "diff_snapshots",
    "fetch_snapshot",
    "parse_snapshot",
]
