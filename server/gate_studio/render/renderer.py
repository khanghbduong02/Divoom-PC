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


def render_panel_frames(
    panel: Panel,
    values: dict[str, float | None] | None = None,
    media_dir: Path | None = None,
    now: datetime | None = None,
    *,
    history: History | None = None,
    temperature_unit: str = "c",
    static_only: bool = False,
    max_frames: int = 40,
) -> list[tuple[Image.Image, int]]:
    """Render one panel, preserving an animated GIF background.

    A still background produces one ``(image, delay_ms)`` pair.  An animated
    GIF is fitted frame-by-frame and keeps its delays; native text is still
    drawn by the device on top of the hosted GIF.
    """
    values = values or {}
    now = now or datetime.now()
    history = history or {}
    background = panel.background
    base_color = parse_color(background.color)

    sources: list[tuple[Image.Image | None, int]] = [(None, 100)]
    if background.kind == "image":
        sources = backgrounds.load_animation(
            media_dir, background.image, max_frames=max_frames
        ) or sources

    rendered: list[tuple[Image.Image, int]] = []
    for source, delay in sources:
        if source is None:
            canvas = Image.new("RGB", (PANEL_SIZE, PANEL_SIZE), base_color)
        else:
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
                # These become native text items on the device.  Leaving them
                # out keeps the background free of stale duplicate values.
                continue
            _draw_layer(draw, layer, values, now, history, temperature_unit)
        rendered.append((canvas, delay))
    return rendered


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
    """Render the first frame, used by the live editor preview."""
    return render_panel_frames(
        panel,
        values,
        media_dir,
        now,
        history=history,
        temperature_unit=temperature_unit,
        static_only=static_only,
        max_frames=1,
    )[0][0]


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


def render_all_frames(
    theme: Theme,
    values: dict[str, float | None] | None = None,
    media_dir: Path | None = None,
    now: datetime | None = None,
    *,
    history: History | None = None,
    temperature_unit: str = "c",
    static_only: bool = False,
    max_frames: int = 40,
) -> list[list[tuple[Image.Image, int]]]:
    """Render every panel while preserving animated backgrounds."""
    now = now or datetime.now()
    return [
        render_panel_frames(
            panel,
            values,
            media_dir,
            now,
            history=history,
            temperature_unit=temperature_unit,
            static_only=static_only,
            max_frames=max_frames,
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
