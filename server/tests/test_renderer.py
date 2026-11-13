"""Renderer tests: geometry, placeholders and encoders."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from gate_studio.models import Background, Layer, Panel, Theme
from gate_studio.render import font, render_all, render_panel
from gate_studio.render.renderer import encode_jpeg, encode_png, render_test_panel


def test_panel_is_128_square_rgb() -> None:
    image = render_panel(Panel(background=Background(color="#101010")))
    assert image.size == (128, 128)
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (16, 16, 16)


def test_number_layer_draws_inside_its_box() -> None:
    layer = Layer.metric_layer("cpu_temp", x=0, y=0, w=128, h=128, scale=6, color="#00FF00")
    panel = Panel(background=Background(color="#000000"), layers=[layer])
    image = render_panel(panel, {"cpu_temp": 64})
    palette = dict((color, count) for count, color in image.getcolors(maxcolors=1 << 20) or [])
    assert palette.get((0, 255, 0), 0) > 50
    # nothing was painted into the bottom rows for a single line
    assert image.getpixel((0, 127)) == (0, 0, 0)


def test_missing_metric_renders_placeholder_not_a_number() -> None:
    layer = Layer.metric_layer("gpu_temp", y=20, w=128, h=30, scale=2)
    panel = Panel(background=Background(color="#000000"), layers=[layer])
    with_value = render_panel(panel, {"gpu_temp": 55})
    missing = render_panel(panel, {"gpu_temp": None})
    absent = render_panel(panel, {})
    assert missing.tobytes() != with_value.tobytes()
    assert missing.tobytes() == absent.tobytes()


def test_bar_fills_proportionally() -> None:
    layer = Layer.metric_layer(
        "cpu_percent", widget="bar", x=0, y=64, w=128, h=8, color="#FFFFFF", track_color="#333333"
    )
    panel = Panel(background=Background(color="#000000"), layers=[layer])
    half = render_panel(panel, {"cpu_percent": 50})
    assert half.getpixel((10, 68)) == (255, 255, 255)
    assert half.getpixel((120, 68)) == (51, 51, 51)

    full = render_panel(panel, {"cpu_percent": 250})
    assert full.getpixel((120, 68)) == (255, 255, 255)


def test_clock_layer_uses_current_time() -> None:
    layer = Layer(kind="text", source="clock", x=4, y=4, w=120, h=30, scale=3, color="#FFAA00")
    panel = Panel(background=Background(color="#000000"), layers=[layer])
    image = render_panel(panel, now=datetime(2026, 11, 13, 9, 41))
    palette = dict((color, count) for count, color in image.getcolors(maxcolors=1 << 20) or [])
    assert palette.get((255, 170, 0), 0) > 20


def test_background_image_is_fitted(tmp_path: Path) -> None:
    source = Image.new("RGB", (256, 64), (200, 10, 10))
    (tmp_path / "wide.png").write_bytes(encode_png(source))
    panel = Panel(background=Background(kind="image", image="wide.png", fit="stretch"))
    image = render_panel(panel, media_dir=tmp_path)
    assert image.getpixel((64, 64))[0] > 150
    assert image.getpixel((64, 64))[1] < 60


def test_missing_background_file_falls_back_to_colour(tmp_path: Path) -> None:
    panel = Panel(background=Background(kind="image", image="nope.png", color="#123456"))
    assert render_panel(panel, media_dir=tmp_path).getpixel((0, 0)) == (0x12, 0x34, 0x56)


def test_theme_renders_five_panels() -> None:
    theme = Theme(name="x")
    theme.panels[2].layers.append(Layer.metric_layer("ram_percent", y=40, scale=2))
    images = render_all(theme, {"ram_percent": 42})
    assert len(images) == 5
    assert images[2].tobytes() != images[0].tobytes()


def test_fit_scale_shrinks_long_text() -> None:
    assert font.fit_scale("12", 128, 8) == 8
    assert font.fit_scale("123456789", 128, 8) < 8
    assert font.fit_scale("123456789012345678901234", 128, 8) == 1


def test_encoders() -> None:
    image = render_test_panel(0)
    assert encode_png(image).startswith(b"\x89PNG")
    assert encode_jpeg(image).startswith(b"\xff\xd8")
    assert len(encode_jpeg(image)) < 12_000
