"""Native Times Gate text overlay support.

Continuously pushing JPEG frames makes the Times Gate flash its loading screen.
For a stable dashboard we upload the static part of a panel once as a hosted
GIF background and then update only text items with ``Draw/SendHttpItemList``.
The device can update those items without re-drawing the whole panel.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from .config import ConfigStore
from .models import Layer, Panel
from .render import widgets


@dataclass(frozen=True)
class NativePanel:
    """A panel whose background is hosted by the agent and whose values are items."""

    panel: int
    background_name: str


def dynamic_layers(panel: Panel) -> list[tuple[int, Layer]]:
    """Layers that can be represented by native item-list text updates."""
    result: list[tuple[int, Layer]] = []
    for index, layer in enumerate(panel.layers):
        if not layer.visible:
            continue
        if layer.kind == "metric" and layer.widget == "number":
            result.append((index, layer))
        elif layer.kind == "text" and layer.source in ("clock", "date"):
            result.append((index, layer))
    return result


_FONT_WIDTHS = {80: 5, 42: 7}
_FONT_HEIGHTS = {80: 7, 42: 9}


def _font_for(layer: Layer) -> int:
    # The editor's bitmap font is 5x7.  Font 80 is the matching 5x7 face.
    # Font 42 (7x9) has the '.' glyph that font 80 lacks, so use it for
    # decimal values and dates.
    if layer.kind == "metric" and layer.decimals > 0:
        return 42
    if layer.kind == "text" and layer.source == "date":
        return 42
    return 80


def _device_text(text: str) -> str:
    """Keep units inside the charsets of the small device fonts."""
    return text.replace("°C", "C").replace("°F", "F").replace("°", "")


def _align_for(layer: Layer) -> int:
    return {"left": 1, "center": 3, "right": 5}[layer.align]


def build_items(
    panel: Panel,
    values: dict[str, float | None],
    now: datetime,
    temperature_unit: str = "c",
) -> list[dict[str, object]]:
    """Build the dynamic ``ItemList`` for one panel.

    Labels and graphs stay in the background. Numbers, clock and date are
    native text items, so changing them does not load or clear the screen.
    """
    items: list[dict[str, object]] = []
    for index, layer in dynamic_layers(panel):
        text_id = index + 1
        if text_id > 39:
            # SendHttpItemList accepts IDs 1..39 on this firmware.
            continue
        text = widgets.text_for(
            layer,
            values.get(layer.metric) if layer.kind == "metric" else None,
            now,
            temperature_unit,
        )
        text = _device_text(text)
        if not text:
            continue
        font = _font_for(layer)
        font_width = _FONT_WIDTHS[font]
        font_height = _FONT_HEIGHTS[font]
        width = max(1, font_width * len(text) + 2)
        x = int(layer.x)
        if layer.align == "center":
            x += (int(layer.w) - width) // 2
        elif layer.align == "right":
            x += int(layer.w) - width
        y = int(layer.y) + max(0, (int(layer.h) - font_height) // 2)
        items.append(
            {
                "TextId": text_id,
                "type": 22,
                "x": x,
                "y": y,
                "dir": 0,
                "font": font,
                "TextWidth": width,
                "Textheight": font_height,
                "TextString": text,
                "speed": 0,
                "align": _align_for(layer),
                "color": layer.color,
            }
        )
    return items


def setup_items(
    panel: Panel,
    values: dict[str, float | None],
    now: datetime,
    temperature_unit: str = "c",
) -> list[dict[str, object]]:
    """Items for a ``NewFlag: 1`` setup call, with the required throwaway first item.

    The first type-22 item is dropped by the device when ``BackgroudGif`` is
    present.  A harmless leading item absorbs that firmware quirk.
    """
    items = build_items(panel, values, now, temperature_unit)
    if not items:
        return []
    used = {int(item["TextId"]) for item in items}
    dummy_id = next((value for value in range(1, 40) if value not in used), None)
    if dummy_id is None:
        return items
    dummy = {
        "TextId": dummy_id,
        "type": 22,
        "x": 0,
        "y": 0,
        "dir": 0,
        "font": 4,
        "TextWidth": 1,
        "Textheight": 16,
        # Non-empty so the firmware really counts it as the throwaway first
        # item; the colour makes it invisible if it is not dropped.
        "TextString": ".",
        "speed": 0,
        "align": 1,
        "color": panel.background.color,
    }
    return [dummy, *items]


def save_background(
    store: ConfigStore,
    theme_id: str,
    panel: int,
    image: Image.Image | list[Image.Image],
    durations: list[int] | None = None,
) -> str:
    """Save a panel background as a device-safe still or animated GIF.

    The Times Gate treats GIF palette index 0 as transparent, so index 0 is
    reserved for an unused sentinel and the rendered colours start at index 1.
    Animated backgrounds keep their frame delays and loop forever.
    """
    store.ensure_dirs()
    for old in store.media_dir.glob(f"native-{theme_id[:10]}-{panel}-*.gif"):
        with contextlib.suppress(OSError):
            old.unlink()
    name = f"native-{theme_id[:10]}-{panel}-{uuid.uuid4().hex[:6]}.gif"
    path: Path = store.media_path(name)
    images = image if isinstance(image, list) else [image]
    images = images[:40]
    if not images:
        raise ValueError("background has no frames")

    def frame(source: Image.Image) -> Image.Image:
        paletted = source.convert("RGB").quantize(colors=255)
        source_palette = (list(paletted.getpalette() or []) + [0] * 768)[:765]
        output = Image.new("P", paletted.size)
        output.putpalette([1, 2, 3, *source_palette])
        output.putdata([index + 1 for index in paletted.getdata()])
        return output

    frames = [frame(item) for item in images]
    delays = (durations or [100] * len(frames))[: len(frames)]
    if len(delays) < len(frames):
        delays += [delays[-1] if delays else 100] * (len(frames) - len(delays))
    frames[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[max(30, min(1000, int(delay))) for delay in delays],
        loop=0,
        optimize=False,
        disposal=2,
    )
    return name