"""Draws a whole 128x128 panel headlessly, then encodes it for the device.

Rendering app-side (instead of the device's text commands) is what buys free
positioning, arbitrary fonts and gauges — the panel just receives one JPEG.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from ..models import Layer, Panel, Theme
from . import backgrounds, font, widgets

PANEL_SIZE = 128


def parse_color(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return (255, 255, 255)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return (255, 255, 255)


History = dict[str, list[tuple[float, float | None]]]


def _draw_layer(
    draw: ImageDraw.ImageDraw,
    layer: Layer,
    values: dict[str, float | None],
    now: datetime,
    history: History,
    temperature_unit: str,
) -> None:
    if not layer.visible:
        return
    value = values.get(layer.metric) if layer.kind == "metric" else None
    if layer.kind == "metric" and layer.widget == "bar":
        widgets.draw_bar(draw, layer, value)
    elif layer.kind == "metric" and layer.widget == "line":
        cutoff = now.timestamp() - max(1, layer.history_minutes) * 60
        samples = [
            (stamp, item) for stamp, item in history.get(layer.metric, []) if stamp >= cutoff
        ]
        widgets.draw_line(draw, layer, samples, temperature_unit)
    else:
        widgets.draw_number(draw, layer, value, now, temperature_unit)


def render_panel(
    panel: Panel,
    values: dict[str, float | None] | None = None,
    media_dir: Path | None = None,
    now: datetime | None = None,
    *,
    history: History | None = None,
    temperature_unit: str = "c",
    static_only: bool = False,
) -> Image.Image:
    values = values or {}
    now = now or datetime.now()
    history = history or {}
    background = panel.background
    base_color = parse_color(background.color)

    canvas = Image.new("RGB", (PANEL_SIZE, PANEL_SIZE), base_color)
    if background.kind == "image":
        source = backgrounds.load_media(media_dir, background.image)
        if source is not None:
            canvas = backgrounds.fit_image(
                source,
                (PANEL_SIZE, PANEL_SIZE),
                background.fit,
                background=base_color,
            )
            canvas = backgrounds.dim(canvas, background.dim)

    draw = ImageDraw.Draw(canvas)
    for layer in panel.layers:
        if static_only and (
            (layer.kind == "metric" and layer.widget == "number")
            or (layer.kind == "text" and layer.source in ("clock", "date"))
        ):
            # These become native text items on the device.  Leaving them out
            # keeps the uploaded background free of stale duplicate values.
            continue
        _draw_layer(draw, layer, values, now, history, temperature_unit)
    return canvas


def render_all(
    theme: Theme,
    values: dict[str, float | None] | None = None,
    media_dir: Path | None = None,
    now: datetime | None = None,
    *,
    history: History | None = None,
    temperature_unit: str = "c",
    static_only: bool = False,
) -> list[Image.Image]:
    now = now or datetime.now()
    return [
        render_panel(
            panel,
            values,
            media_dir,
            now,
            history=history,
            temperature_unit=temperature_unit,
            static_only=static_only,
        )
        for panel in theme.panels
    ]


def encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def encode_jpeg(image: Image.Image, quality: int = 88) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, subsampling=0)
    return buffer.getvalue()


def render_test_panel(index: int, color: str = "#00D1FF") -> Image.Image:
    """The M1 proof image: panel index on a coloured tile."""
    tile = Image.new("RGB", (PANEL_SIZE, PANEL_SIZE), "#0B0B0B")
    draw = ImageDraw.Draw(tile)
    tint = parse_color(color)
    draw.rectangle((0, 0, PANEL_SIZE - 1, PANEL_SIZE - 1), outline=tint, width=3)
    label = str(index + 1)
    scale = font.fit_scale(label, PANEL_SIZE - 24, 12, PANEL_SIZE - 24)
    width = font.text_width(label, scale)
    height = font.text_height(scale)
    font.draw_text(
        draw,
        ((PANEL_SIZE - width) // 2, (PANEL_SIZE - height) // 2),
        label,
        scale,
        color,
    )
    return tile
