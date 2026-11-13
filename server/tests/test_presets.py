"""Preset files must stay valid themes that render on all five panels."""

from __future__ import annotations

import json

import pytest

from gate_studio.presets import PRESET_DIR, list_presets, load_preset
from gate_studio.render import render_all


def test_presets_are_discoverable() -> None:
    presets = list_presets()
    assert presets
    assert all(preset["name"] for preset in presets)
    assert all(preset["description"] for preset in presets)


@pytest.mark.parametrize("meta", list_presets(), ids=lambda meta: meta["id"])
def test_each_preset_loads_and_renders(meta: dict) -> None:
    theme = load_preset(meta["id"])
    assert theme.id == f"preset-{meta['id']}"
    assert theme.name == meta["name"]
    assert len(theme.panels) == 5
    assert all(panel.layers for panel in theme.panels), "every panel should carry content"

    images = render_all(
        theme,
        {
            "cpu_percent": 41,
            "cpu_temp": 55,
            "gpu_percent": 76,
            "gpu_temp": 71,
            "ram_percent": 63,
            "disk_percent": 28,
        },
    )
    assert len(images) == 5
    assert all(image.size == (128, 128) for image in images)
    # a preset with actual content must not render five identical black panels
    assert len({image.tobytes() for image in images}) > 1


def test_preset_files_are_plain_json_themes() -> None:
    for path in PRESET_DIR.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "panels" in payload
        assert len(payload["panels"]) == 5


def test_unknown_preset_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_preset("does-not-exist")
