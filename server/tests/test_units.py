"""Temperature display rules: °C in storage, °C or °F on the panel."""

from __future__ import annotations

from gate_studio.models import Layer
from gate_studio.render.widgets import format_value
from gate_studio.units import normalize_unit, suffix, to_display


def test_celsius_to_fahrenheit_conversion() -> None:
    assert to_display(0, "c") == 0
    assert to_display(100, "f") == 212
    assert to_display(36.5, "f") == 97.7
    assert round(to_display(-40, "f")) == -40


def test_unit_labels_and_normalisation() -> None:
    assert suffix("c") == "°C"
    assert suffix("F") == "°F"
    assert normalize_unit(None) == "c"
    assert normalize_unit("fahrenheit") == "f"
    assert normalize_unit("Celsius") == "c"


def test_temperature_value_uses_the_selected_unit() -> None:
    layer = Layer.metric_layer("cpu_temp")
    assert format_value(60, layer, "c") == "60°C"
    assert format_value(60, layer, "f") == "140°F"
    assert format_value(None, layer, "f") == "--"


def test_other_units_are_not_converted() -> None:
    layer = Layer.metric_layer("net_down")
    assert format_value(1.5, layer, "f") == "1.5MB/s"
    percent = Layer.metric_layer("ram_percent")
    percent.unit = "%"
    assert format_value(42, percent, "f") == "42%"
