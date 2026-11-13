"""Widget painters: big number and horizontal bar, plus text/clock/date."""

from __future__ import annotations

from datetime import datetime

from PIL import ImageDraw

from ..models import Layer
from . import font

MISSING = "--"


def format_value(value: float | None, layer: Layer) -> str:
    """Render a metric value, or a visible placeholder when it is unavailable."""
    if value is None:
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MISSING
    decimals = max(0, min(3, int(layer.decimals)))
    return f"{number:.{decimals}f}{layer.unit}"


def text_for(layer: Layer, value: float | None, now: datetime) -> str:
    if layer.kind == "text":
        if layer.source == "clock":
            return now.strftime("%H:%M")
        if layer.source == "date":
            return now.strftime("%a %d.%m")
        return layer.text
    return format_value(value, layer)


def _aligned_x(layer: Layer, text: str, scale: int) -> int:
    width = font.text_width(text, scale)
    if layer.align == "center":
        return layer.x + (layer.w - width) // 2
    if layer.align == "right":
        return layer.x + layer.w - width
    return layer.x


def draw_number(
    draw: ImageDraw.ImageDraw,
    layer: Layer,
    value: float | None,
    now: datetime,
) -> None:
    text = text_for(layer, value, now)
    if not text:
        return
    scale = font.fit_scale(text, layer.w, layer.scale, layer.h)
    x = _aligned_x(layer, text, scale)
    y = layer.y + max(0, (layer.h - font.text_height(scale)) // 2)
    font.draw_text(draw, (x, y), text, scale, layer.color)


def draw_bar(draw: ImageDraw.ImageDraw, layer: Layer, value: float | None) -> None:
    """Horizontal gauge: a track with a proportional fill."""
    if layer.w <= 0 or layer.h <= 0:
        return
    box = (layer.x, layer.y, layer.x + layer.w - 1, layer.y + layer.h - 1)
    draw.rectangle(box, fill=layer.track_color)
    if value is None:
        return
    span = float(layer.max_value) - float(layer.min_value)
    ratio = 0.0 if span == 0 else (float(value) - float(layer.min_value)) / span
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(layer.w * ratio))
    if filled <= 0:
        return
    draw.rectangle(
        (box[0], box[1], box[0] + filled - 1, box[3]),
        fill=layer.color,
    )
