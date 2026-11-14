"""The Divoom cloud screen watcher, tested without network access."""

from __future__ import annotations

import httpx
import pytest

from gate_studio.device.external import (
    CLOUD_STATE_URL,
    ExternalWatchError,
    diff_snapshots,
    fetch_snapshot,
    parse_snapshot,
)


def _payload(
    faces: list[tuple[int, int, str]] | None = None,
    *,
    channel_type: int = 1,
    preset: int = 973749,
    clock_id: int = 581,
) -> dict[str, object]:
    faces = faces or [
        (0, 182, "image-a"),
        (0, 108, "image-b"),
        (1, 57, ""),
        (0, 671, "image-d"),
        (0, 196, "image-e"),
    ]
    return {
        "ReturnCode": 0,
        "ChannelType": channel_type,
        "ClockId": clock_id,
        "LcdIndependence": preset,
        "LcdIndependenceList": [
            {
                "IndependenceName": "Control1",
                "LcdIndependence": preset,
                "LcdIndependPos": 0,
                "LcdList": [
                    {
                        "LcdSelectIndex": channel,
                        "LcdClockId": face_id,
                        "ClockImagePixelId": pixel_id,
                    }
                    for channel, face_id, pixel_id in faces
                ],
            }
        ],
    }


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def json(self) -> object:
        return self.payload


class _FakeClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, url: str, json: dict[str, object], timeout: float) -> _FakeResponse:
        self.calls.append((url, json))
        return _FakeResponse(self.payload)


def test_parse_snapshot_reads_the_active_preset() -> None:
    snapshot = parse_snapshot(_payload())
    assert snapshot.channel_type == 1
    assert snapshot.preset == 973749
    assert snapshot.faces[0] == (0, 182, "image-a")
    assert len(snapshot.faces) == 5


def test_whole_display_changes_count_as_all_screens() -> None:
    previous = parse_snapshot(_payload(channel_type=0, preset=0, clock_id=10))
    same = parse_snapshot(_payload(channel_type=0, preset=0, clock_id=10))
    changed = parse_snapshot(_payload(channel_type=0, preset=0, clock_id=11))
    assert diff_snapshots(previous, same) == []
    assert diff_snapshots(previous, changed) == [0, 1, 2, 3, 4]


def test_only_the_screen_with_a_new_face_is_changed() -> None:
    previous = parse_snapshot(_payload())
    changed_faces = list(previous.faces)
    changed_faces[1] = (0, 109, "image-b")
    current = parse_snapshot(_payload(changed_faces))
    assert diff_snapshots(previous, current) == [1]


def test_switching_presets_changes_every_screen() -> None:
    previous = parse_snapshot(_payload())
    current = parse_snapshot(_payload(preset=973759))
    assert diff_snapshots(previous, current) == [0, 1, 2, 3, 4]


def test_parse_rejects_cloud_errors() -> None:
    with pytest.raises(ExternalWatchError, match="rejected"):
        parse_snapshot({"ReturnCode": 1, "ReturnMessage": "device not found"})


def test_parse_rejects_a_missing_active_layout() -> None:
    payload = _payload()
    payload["LcdIndependenceList"] = []
    with pytest.raises(ExternalWatchError, match="active"):
        parse_snapshot(payload)


def test_fetch_snapshot_posts_the_device_id() -> None:
    client = _FakeClient(_payload())
    snapshot = fetch_snapshot(300450453, client=client)  # type: ignore[arg-type]
    assert snapshot.preset == 973749
    assert client.calls == [
        (CLOUD_STATE_URL, {"DeviceId": 300450453, "DeviceType": "LCD"})
    ]


def test_fetch_snapshot_reports_network_failures() -> None:
    class FailingClient:
        def post(self, *args: object, **kwargs: object) -> object:
            raise httpx.ConnectError("offline")

    with pytest.raises(ExternalWatchError, match="cloud"):
        fetch_snapshot(1, client=FailingClient())  # type: ignore[arg-type]
