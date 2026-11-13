"""Temperature units: the app stores Celsius and shows Celsius or Fahrenheit."""

from __future__ import annotations

from .models import Layer

TEMPERATURE_METRICS: frozenset[str] = frozenset({"cpu_temp", "gpu_temp"})


def is_temperature(metric: str) -> bool:
    return metric in TEMPERATURE_METRICS


def normalize_unit(value: str | None) -> str:
    return "f" if (value or "c").strip().lower().startswith("f") else "c"


def to_display(value: float, unit: str) -> float:
    if normalize_unit(unit) == "f":
        return value * 9 / 5 + 32
    return value


def suffix(unit: str) -> str:
    return "°F" if normalize_unit(unit) == "f" else "°C"


def display_unit(layer: Layer, unit: str) -> str:
    """What follows the number: a fixed °C/°F for temperatures, else the
    layer's own text so units like MB/s stay editable."""
    if is_temperature(layer.metric):
        return suffix(unit)
    return layer.unit
