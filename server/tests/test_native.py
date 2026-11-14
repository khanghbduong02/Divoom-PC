"""Native item-list rendering tests (no hardware required)."""

from __future__ import annotations

from datetime import datetime

from gate_studio.models import Layer, Panel
from gate_studio.native import build_items, dynamic_layers, setup_items


def _panel() -> Panel:
    return Panel(
        layers=[
            Layer(kind="text", text="Mimi PC", source="static", x=6, y=4, w=116, h=14),
            Layer.metric_layer(
                "cpu_percent",
                widget="number",
                x=32,
                y=32,
                w=26,
                h=11,
                align="center",
            ),
            Layer.metric_layer("cpu_percent", widget="line", x=6, y=44, w=54, h=32),
            Layer(kind="text", text="", source="clock", x=0, y=0, w=40, h=20),
        ]
    )


def test_native_items_are_only_dynamic_layers() -> None:
    panel = _panel()
    assert [index for index, _ in dynamic_layers(panel)] == [1, 3]

    items = build_items(panel, {"cpu_percent": 12.0}, datetime(2026, 1, 2, 3, 4))
    assert [item["TextId"] for item in items] == [2, 4]
    assert items[0]["TextString"] == "12%"
    assert items[1]["TextString"] == "03:04"
    assert all(item["type"] == 22 for item in items)
    assert all(item["font"] == 80 for item in items)
    assert all(item["Textheight"] == 7 for item in items)


def test_native_empty_capacity_returns_no_items() -> None:
    panel = Panel(
        layers=[Layer.metric_layer("cpu_percent", widget="line", w=40, h=30)]
    )
    assert build_items(panel, {"cpu_percent": 5.0}, datetime.now()) == []


def test_setup_items_adds_a_throwaway_first_item() -> None:
    """The device drops the first type-22 item when a background URL is present."""
    items = setup_items(_panel(), {"cpu_percent": 12.0}, datetime(2026, 1, 2, 3, 4))
    assert len(items) == 3
    assert items[0]["TextString"] == "."
    assert items[0]["TextId"] not in {item["TextId"] for item in items[1:]}
    assert items[1]["TextString"] == "12%"