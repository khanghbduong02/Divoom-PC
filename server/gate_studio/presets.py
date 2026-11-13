"""Preset themes shipped with the agent, stored as plain JSON so they can be shared."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Theme

PRESET_DIR = Path(__file__).parent / "presets"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def preset_files() -> list[Path]:
    if not PRESET_DIR.exists():
        return []
    return sorted(PRESET_DIR.glob("*.json"))


def list_presets() -> list[dict[str, str]]:
    presets: list[dict[str, str]] = []
    for path in preset_files():
        try:
            data = _read(path)
        except (OSError, ValueError):
            continue
        presets.append(
            {
                "id": path.stem,
                "name": str(data.get("name") or path.stem),
                "description": str(data.get("description") or ""),
            }
        )
    return presets


def load_preset(preset_id: str) -> Theme:
    """Load one preset; the id in the file is ignored so links stay stable."""
    path = PRESET_DIR / f"{Path(preset_id).stem}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown preset {preset_id!r}")
    data = _read(path)
    theme = Theme.model_validate(data)
    theme.id = f"preset-{path.stem}"
    theme.name = str(data.get("name") or theme.name)
    return theme
