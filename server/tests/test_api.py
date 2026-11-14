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
