"""API tests driven through the ASGI app, with a throwaway data folder."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gate_studio.api import create_app
from gate_studio.config import ConfigStore
from gate_studio.device.external import ExternalSnapshot
from gate_studio.library import SavedLibrary
from gate_studio.models import Layer


@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(tmp_path / "data")


@pytest.fixture()
def client(store: ConfigStore):
    app = create_app(store, static_dir=tmp_path_missing())
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": f"Bearer {store.token()}"})
        yield test_client


def tmp_path_missing() -> Path:
    return Path(__file__).parent / "no-such-static-dir"


def test_health_requires_token(client: TestClient, store: ConfigStore) -> None:
    anonymous = TestClient(client.app)
    assert anonymous.get("/api/health").status_code == 401
    assert anonymous.get(f"/api/health?token={store.token()}").status_code == 200


def test_health_reports_version_and_device(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["device"]["configured"] is False


def test_theme_round_trip(client: TestClient) -> None:
    theme = client.get("/api/theme").json()["theme"]
    assert len(theme["panels"]) == 5

    theme["panels"][1]["layers"].append(
        Layer.metric_layer("gpu_temp", y=10, scale=3).model_dump(mode="json")
    )
    theme["panels"][1]["background"]["color"] = "#123456"
    response = client.put("/api/theme", json=theme)
    assert response.status_code == 200

    stored = client.get("/api/theme").json()["theme"]
    assert stored["panels"][1]["background"]["color"] == "#123456"
    assert stored["panels"][1]["layers"][0]["metric"] == "gpu_temp"


def test_theme_rejects_unknown_metric(client: TestClient) -> None:
    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][0]["layers"] = [{"kind": "metric", "metric": "moon_phase"}]
    assert client.put("/api/theme", json=theme).status_code == 422


def test_presets_list_and_apply(client: TestClient) -> None:
    presets = client.get("/api/presets").json()["presets"]
    ids = {preset["id"] for preset in presets}
    assert {"nvidia-hud", "minimal-mono", "retro-terminal"} <= ids

    applied = client.post("/api/presets/nvidia-hud/apply")
    assert applied.status_code == 200
    theme = applied.json()["theme"]
    assert theme["name"] == "NVIDIA HUD"
    assert len(theme["panels"][0]["layers"]) >= 2
    assert client.post("/api/presets/nope/apply").status_code == 404


def test_send_without_device_explains_the_problem(client: TestClient) -> None:
    response = client.post("/api/send")
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["kind"] == "not_configured"
    assert "wizard" in (error["hint"] or "").lower()


def test_editing_the_draft_does_not_change_the_applied_design(client: TestClient) -> None:
    state = client.app.state.gate
    original = state.applied_theme.panels[0].background.color

    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][0]["background"]["color"] = "#123456"
    assert client.put("/api/theme", json=theme).status_code == 200

    assert state.config.theme.panels[0].background.color == "#123456"
    assert state.applied_theme.panels[0].background.color == original


def test_send_applies_only_the_requested_panel(client: TestClient, monkeypatch) -> None:
    state = client.app.state.gate
    before_other = state.applied_theme.panels[0].background.color

    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][0]["background"]["color"] = "#AAAAAA"
    theme["panels"][1]["background"]["color"] = "#BBBBBB"
    assert client.put("/api/theme", json=theme).status_code == 200

    monkeypatch.setattr("gate_studio.api._push", lambda *args, **kwargs: [])
    response = client.post("/api/send", json={"panels": [1]})
    assert response.status_code == 200

    assert state.applied_theme.panels[0].background.color == before_other
    assert state.applied_theme.panels[1].background.color == "#BBBBBB"


def test_send_all_applies_every_panel(client: TestClient, monkeypatch) -> None:
    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][2]["background"]["color"] = "#CCCCCC"
    assert client.put("/api/theme", json=theme).status_code == 200

    monkeypatch.setattr("gate_studio.api._push", lambda *args, **kwargs: [])
    assert client.post("/api/send").status_code == 200

    state = client.app.state.gate
    assert state.applied_theme.panels[2].background.color == "#CCCCCC"
    assert state.config.applied_theme is not None
    assert state.config.applied_theme.panels[2].background.color == "#CCCCCC"


def test_paused_panel_round_trip_and_preview_state(client: TestClient, store: ConfigStore) -> None:
    paused = client.post("/api/panels/1/pause", json={"paused": True})
    assert paused.status_code == 200
    body = paused.json()["paused_panels"]
    assert body[0]["panel"] == 1
    assert body[0]["source"] == "manual"
    assert json.loads(store.config_path.read_text(encoding="utf-8"))["paused_panels"][0][
        "panel"
    ] == 1

    with client.websocket_connect(f"/ws?token={store.token()}") as websocket:
        tick = websocket.receive_json()
    assert [item["panel"] for item in tick["paused"]] == [1]

    resumed = client.post("/api/panels/1/pause", json={"paused": False})
    assert resumed.json()["paused_panels"] == []


def test_send_resumes_a_paused_panel(client: TestClient, monkeypatch) -> None:
    assert client.post("/api/panels/1/pause", json={"paused": True}).status_code == 200
    monkeypatch.setattr("gate_studio.api._push", lambda *args, **kwargs: [])
    assert client.post("/api/send", json={"panels": [1]}).status_code == 200
    assert client.app.state.gate.paused_snapshot() == []


def test_external_change_pauses_only_that_panel(client: TestClient) -> None:
    state = client.app.state.gate
    first = ExternalSnapshot(
        channel_type=1,
        clock_id=581,
        preset=973749,
        faces=tuple((0, 100 + index, "") for index in range(5)),
    )
    changed_faces = list(first.faces)
    changed_faces[2] = (0, 999, "")
    second = ExternalSnapshot(
        channel_type=1,
        clock_id=581,
        preset=973749,
        faces=tuple(changed_faces),
    )

    assert state.apply_external_snapshot(first) == []
    assert state.apply_external_snapshot(second) == [2]
    assert [item["panel"] for item in state.paused_snapshot()] == [2]
    assert state.paused_snapshot()[0]["source"] == "external"


def test_pause_validates_the_panel_index(client: TestClient) -> None:
    assert client.post("/api/panels/9/pause", json={"paused": True}).status_code == 422


def test_external_watch_settings_round_trip(client: TestClient) -> None:
    body = client.put(
        "/api/config/settings",
        json={"external_watch": False, "external_check_interval": 12},
    ).json()
    assert body["settings"]["external_watch"] is False
    assert body["settings"]["external_check_interval"] == 12
    stored = client.get("/api/config").json()["settings"]
    assert stored["external_watch"] is False
    assert stored["external_check_interval"] == 12


def test_saved_theme_round_trip(client: TestClient, store: ConfigStore) -> None:
    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][0]["background"]["color"] = "#ABCDEF"
    assert client.put("/api/theme", json=theme).status_code == 200

    saved = client.post("/api/library/themes", json={"name": "My desk"})
    assert saved.status_code == 200
    item = saved.json()["item"]
    assert item["name"] == "My desk"
    assert saved.json()["library"]["themes"][0]["id"] == item["id"]
    assert SavedLibrary(store.data_dir).list()["themes"][0]["name"] == "My desk"

    changed = client.get("/api/theme").json()["theme"]
    changed["panels"][0]["background"]["color"] = "#000000"
    assert client.put("/api/theme", json=changed).status_code == 200

    applied = client.post(f"/api/library/themes/{item['id']}/apply")
    assert applied.status_code == 200
    assert applied.json()["theme"]["panels"][0]["background"]["color"] == "#ABCDEF"
    assert applied.json()["theme"]["name"] == "My desk"
    assert store.config_path.exists()


def test_saved_panel_replaces_only_that_panel(client: TestClient) -> None:
    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][1]["background"]["color"] = "#123456"
    theme["panels"][0]["background"]["color"] = "#654321"
    assert client.put("/api/theme", json=theme).status_code == 200

    saved = client.post(
        "/api/library/panels", json={"panel": 1, "name": "My sensor tile"}
    )
    assert saved.status_code == 200
    item = saved.json()["item"]

    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][1]["background"]["color"] = "#FFFFFF"
    assert client.put("/api/theme", json=theme).status_code == 200

    applied = client.post(
        f"/api/library/panels/{item['id']}/apply", json={"panel": 1}
    )
    assert applied.status_code == 200
    stored = applied.json()["theme"]
    assert stored["panels"][1]["background"]["color"] == "#123456"
    assert stored["panels"][0]["background"]["color"] == "#654321"


def test_saved_names_update_in_place(client: TestClient) -> None:
    client.post("/api/library/themes", json={"name": "Desk"})
    client.post("/api/library/themes", json={"name": "Desk"})
    library = client.get("/api/library").json()
    assert [item["name"] for item in library["themes"]].count("Desk") == 1


def test_saved_library_validates_names_and_ids(client: TestClient) -> None:
    assert client.post("/api/library/themes", json={"name": "  "}).status_code == 422
    assert client.post("/api/library/themes/nope/apply").status_code == 404
    assert client.post("/api/library/panels/nope/apply", json={"panel": 0}).status_code == 404


def test_media_upload_then_serve(client: TestClient) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buffer, format="PNG")
    upload = client.post(
        "/api/media",
        files={"file": ("bg.png", buffer.getvalue(), "image/png")},
    )
    assert upload.status_code == 200
    name = upload.json()["name"]
    served = client.get(f"/media/{name}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"


def test_media_rejects_other_types(client: TestClient) -> None:
    response = client.post("/api/media", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_settings_update(client: TestClient) -> None:
    body = client.put("/api/config/settings", json={"refresh_interval": 2.5}).json()
    assert body["settings"]["refresh_interval"] == 2.5
    assert body["restart_required"] is False


def test_preview_websocket_streams_panels(client: TestClient, store: ConfigStore) -> None:
    with client.websocket_connect(f"/ws?token={store.token()}") as websocket:
        tick = websocket.receive_json()
    assert tick["type"] == "tick"
    assert len(tick["panels"]) == 5
    assert tick["panels"][0]["png"].startswith("iVBOR")  # base64 PNG magic


def test_preview_websocket_rejects_bad_token(client: TestClient) -> None:
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=wrong") as websocket:
            websocket.receive_json()


def test_diagnostics_shape(client: TestClient) -> None:
    body = client.get("/api/diagnostics").json()
    assert set(body) >= {"device", "last_replies", "last_error", "sensors"}
    assert "cpu_percent" in body["sensors"]


def test_theme_drops_missing_background_media(client: TestClient) -> None:
    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][0]["background"] = {
        "kind": "image",
        "image": "gone.png",
        "color": "#000000",
    }
    stored = client.put("/api/theme", json=theme).json()["theme"]
    assert stored["panels"][0]["background"]["kind"] == "color"
    assert stored["panels"][0]["background"]["image"] is None


def test_config_file_is_written(client: TestClient, store: ConfigStore) -> None:
    client.put("/api/config/settings", json={"refresh_interval": 1.2})
    payload = json.loads(store.config_path.read_text(encoding="utf-8"))
    assert payload["settings"]["refresh_interval"] == 1.2


def test_preset_can_apply_to_a_single_panel(client: TestClient) -> None:
    before = client.get("/api/theme").json()["theme"]
    response = client.post("/api/presets/retro-terminal/apply", json={"panel": 2})
    assert response.status_code == 200
    after = response.json()["theme"]

    assert after["panels"][2]["background"]["color"] == "#0A0800"
    assert after["panels"][0] == before["panels"][0]
    assert after["panels"][4] == before["panels"][4]
    # the theme is no longer the preset it borrowed from
    assert not after["id"].startswith("preset-")


def test_single_panel_preset_validates_index(client: TestClient) -> None:
    assert client.post("/api/presets/minimal-mono/apply", json={"panel": 9}).status_code == 422


def test_auto_scale_survives_a_theme_round_trip(client: TestClient) -> None:
    theme = client.get("/api/theme").json()["theme"]
    layer = Layer.metric_layer("ram_percent", auto_scale=True, scale=8).model_dump(mode="json")
    theme["panels"][0]["layers"] = [layer]
    stored = client.put("/api/theme", json=theme).json()["theme"]
    assert stored["panels"][0]["layers"][0]["auto_scale"] is True


def test_system_reports_always_on_state(client: TestClient) -> None:
    body = client.get("/api/system").json()
    assert body["version"]
    assert body["auto_push"] is True
    assert "autostart" in body
    assert "last_push_at" in body


def test_push_settings_round_trip(client: TestClient) -> None:
    body = client.put(
        "/api/config/settings", json={"push_interval": 5, "auto_push": False}
    ).json()
    assert body["settings"]["push_interval"] == 5
    assert body["settings"]["auto_push"] is False
    stored = client.get("/api/config").json()["settings"]
    assert stored["push_interval"] == 5
    assert stored["auto_push"] is False


def test_autostart_endpoint_is_safe_without_registry(client: TestClient) -> None:
    response = client.post("/api/system/autostart", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["supported"] in (True, False)


def test_temperature_unit_round_trip(client: TestClient) -> None:
    body = client.put("/api/config/settings", json={"temperature_unit": "f"}).json()
    assert body["settings"]["temperature_unit"] == "f"
    assert client.get("/api/config").json()["settings"]["temperature_unit"] == "f"
    assert client.get("/api/diagnostics").json()["temperature_unit"] == "f"


def test_diagnostics_reports_temp_source(client: TestClient) -> None:
    hardware = client.get("/api/diagnostics").json()["hardware"]
    assert "cpu_temp_source" in hardware
    assert "cpu_temp_hint" in hardware


def test_line_layer_round_trips_through_the_theme_api(client: TestClient) -> None:
    theme = client.get("/api/theme").json()["theme"]
    theme["panels"][0]["layers"] = [
        {
            "id": "line1", "kind": "metric", "metric": "cpu_percent", "widget": "line",
            "history_minutes": 45, "x": 0, "y": 100, "w": 128, "h": 28,
            "color": "#FFFFFF", "track_color": "#222222", "visible": True,
        }
    ]
    saved = client.put("/api/theme", json=theme).json()["theme"]
    layer = saved["panels"][0]["layers"][0]
    assert layer["widget"] == "line"
    assert layer["history_minutes"] == 45
