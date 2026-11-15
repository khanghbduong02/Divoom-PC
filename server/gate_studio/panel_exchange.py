"""Portable saved-panel files for sharing between Gate Theme Studio installs."""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import ConfigStore, MEDIA_SUFFIXES
from .library import SavedPanel
from .models import Panel

PANEL_FILE_FORMAT = "gate-theme-studio-panel"
PANEL_FILE_VERSION = 1
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PANEL_FILE_BYTES = 12 * 1024 * 1024

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


@dataclass(frozen=True)
class ImportedPanel:
    name: str
    panel: Panel


def export_filename(name: str) -> str:
    """Return a safe, readable download filename for a saved panel."""
    cleaned = re.sub(r"[^A-Za-z0-9 _.-]+", "", name).strip(" ._")
    return f"{cleaned or 'panel'}.json"


def build_panel_export(saved: SavedPanel, media_dir: Path) -> dict[str, object]:
    """Build a self-contained JSON document for one saved panel."""
    panel = saved.panel.model_copy(deep=True)
    background_image: dict[str, str] | None = None

    if panel.background.kind == "image" and panel.background.image:
        image_path = Path(media_dir) / Path(panel.background.image).name
        if image_path.is_file():
            data = image_path.read_bytes()
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("the background picture is too large to export")
            suffix = image_path.suffix.lower()
            background_image = {
                "filename": image_path.name,
                "mime": _IMAGE_MIME.get(suffix, "application/octet-stream"),
                "data": base64.b64encode(data).decode("ascii"),
            }
        else:
            # A stale media reference should not make the exported panel unusable.
            panel.background = panel.background.model_copy(
                update={"kind": "color", "image": None}
            )

    return {
        "format": PANEL_FILE_FORMAT,
        "version": PANEL_FILE_VERSION,
        "name": saved.name,
        "panel": panel.model_dump(mode="json"),
        "background_image": background_image,
    }


def parse_panel_import(data: bytes, store: ConfigStore) -> ImportedPanel:
    """Validate one portable panel file and store any embedded picture."""
    if len(data) > MAX_PANEL_FILE_BYTES:
        raise ValueError("the panel file is too large")

    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("the panel file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("the panel file must contain a JSON object")
    if payload.get("format") != PANEL_FILE_FORMAT:
        raise ValueError("this is not a Gate Theme Studio panel file")
    if payload.get("version") != PANEL_FILE_VERSION:
        raise ValueError("this panel file version is not supported")

    raw_panel = payload.get("panel")
    try:
        panel = Panel.model_validate(raw_panel)
    except ValueError as exc:
        raise ValueError("the panel contents are invalid") from exc

    raw_name = payload.get("name", "Imported panel")
    name = " ".join(str(raw_name).split()).strip()[:80] or "Imported panel"

    image = payload.get("background_image")
    if image is not None:
        if not isinstance(image, dict) or not isinstance(image.get("data"), str):
            raise ValueError("the embedded background picture is invalid")
        filename = Path(str(image.get("filename", "background.png"))).name
        suffix = Path(filename).suffix.lower()
        if suffix not in MEDIA_SUFFIXES:
            raise ValueError("the embedded background picture has an unsupported type")
        try:
            image_data = base64.b64decode(image["data"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("the embedded background picture is not valid base64") from exc
        if len(image_data) > MAX_IMAGE_BYTES:
            raise ValueError("the embedded background picture is too large")
        try:
            with Image.open(io.BytesIO(image_data)) as picture:
                picture.verify()
        except Exception as exc:  # noqa: BLE001 - any decoder failure means invalid input
            raise ValueError("the embedded background picture is not a valid image") from exc
        stored_name = store.save_media(filename, image_data)
        panel.background = panel.background.model_copy(
            update={"kind": "image", "image": stored_name}
        )
    elif panel.background.kind == "image":
        # The file did not carry its picture, so fall back to the solid colour.
        panel.background = panel.background.model_copy(
            update={"kind": "color", "image": None}
        )

    return ImportedPanel(name=name, panel=panel)


__all__ = [
    "ImportedPanel",
    "MAX_PANEL_FILE_BYTES",
    "PANEL_FILE_FORMAT",
    "PANEL_FILE_VERSION",
    "build_panel_export",
    "export_filename",
    "parse_panel_import",
]
