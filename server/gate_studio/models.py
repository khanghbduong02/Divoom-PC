"""Theme, layer and device configuration models.

The JSON shapes here are the contract between the browser editor, the renderer
and the on-disk config file, so they stay deliberately flat and versioned.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PANEL_COUNT = 5
PANEL_SIZE = 128
THEME_SCHEMA_VERSION = 1

#: Metrics the agent can supply. Anything missing renders as ``--``.
METRICS: tuple[str, ...] = (
    "cpu_percent",
    "cpu_temp",
    "gpu_percent",
    "gpu_temp",
    "vram_percent",
    "ram_percent",
    "disk_percent",
    "net_up",
    "net_down",
    "fan_percent",
)

#: Default unit + range per metric, used by the editor when a layer is created.
METRIC_DEFAULTS: dict[str, dict[str, object]] = {
    "cpu_percent": {"unit": "%", "min": 0, "max": 100, "decimals": 0},
    "cpu_temp": {"unit": "C", "min": 20, "max": 100, "decimals": 0},
    "gpu_percent": {"unit": "%", "min": 0, "max": 100, "decimals": 0},
    "gpu_temp": {"unit": "C", "min": 20, "max": 100, "decimals": 0},
    "vram_percent": {"unit": "%", "min": 0, "max": 100, "decimals": 0},
    "ram_percent": {"unit": "%", "min": 0, "max": 100, "decimals": 0},
    "disk_percent": {"unit": "%", "min": 0, "max": 100, "decimals": 0},
    "net_up": {"unit": "MB/s", "min": 0, "max": 10, "decimals": 1},
    "net_down": {"unit": "MB/s", "min": 0, "max": 10, "decimals": 1},
    "fan_percent": {"unit": "%", "min": 0, "max": 100, "decimals": 0},
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _check_color(value: str) -> str:
    if not _HEX_COLOR.match(value):
        raise ValueError("colour must look like #RRGGBB")
    return value.upper()


class Layer(BaseModel):
    """One drawable element on a panel, positioned in 128x128 device pixels."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    kind: Literal["metric", "text"] = "metric"

    # metric layers
    metric: str = "cpu_percent"
    widget: Literal["number", "bar"] = "number"

    # text layers
    text: str = ""
    source: Literal["static", "clock", "date"] = "static"

    x: int = 0
    y: int = 0
    w: int = PANEL_SIZE
    h: int = 40

    color: str = "#FFFFFF"
    track_color: str = "#2A2A2A"
    scale: int = 2
    #: when true the text grows/shrinks to fill the layer box, so dragging the
    #: box corner scales the content instead of needing a separate size value
    auto_scale: bool = False
    decimals: int = 0
    unit: str = ""
    min_value: float = 0
    max_value: float = 100
    align: Literal["left", "center", "right"] = "left"
    visible: bool = True

    @field_validator("color", "track_color")
    @classmethod
    def _validate_color(cls, value: str) -> str:
        return _check_color(value)

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, value: str) -> str:
        if value not in METRICS:
            raise ValueError(f"unknown metric {value!r}")
        return value

    @field_validator("x", "y")
    @classmethod
    def _validate_position(cls, value: int) -> int:
        return max(-PANEL_SIZE, min(PANEL_SIZE * 2, value))

    @field_validator("w", "h")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        return max(1, min(PANEL_SIZE * 2, value))

    @field_validator("scale")
    @classmethod
    def _validate_scale(cls, value: int) -> int:
        return max(1, min(8, value))

    @classmethod
    def metric_layer(cls, metric: str, **overrides: object) -> "Layer":
        defaults = METRIC_DEFAULTS.get(metric, {})
        payload: dict[str, object] = {
            "kind": "metric",
            "metric": metric,
            "widget": "number",
            "unit": defaults.get("unit", ""),
            "min_value": defaults.get("min", 0),
            "max_value": defaults.get("max", 100),
            "decimals": defaults.get("decimals", 0),
        }
        payload.update(overrides)
        return cls(**payload)  # type: ignore[arg-type]


class Background(BaseModel):
    kind: Literal["color", "image"] = "color"
    color: str = "#000000"
    image: str | None = None
    fit: Literal["fit", "crop", "stretch"] = "crop"
    dim: int = 0  # 0-100 black overlay, keeps text legible over photos

    @field_validator("color")
    @classmethod
    def _validate_color(cls, value: str) -> str:
        return _check_color(value)

    @field_validator("dim")
    @classmethod
    def _validate_dim(cls, value: int) -> int:
        return max(0, min(100, value))

    @field_validator("image")
    @classmethod
    def _validate_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.replace("\\", "/").split("/")[-1]


class Panel(BaseModel):
    background: Background = Field(default_factory=Background)
    accent: str = "#00D1FF"
    layers: list[Layer] = Field(default_factory=list)

    @field_validator("accent")
    @classmethod
    def _validate_accent(cls, value: str) -> str:
        return _check_color(value)


class Theme(BaseModel):
    schema_version: int = THEME_SCHEMA_VERSION
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "Untitled"
    panels: list[Panel] = Field(default_factory=lambda: [Panel() for _ in range(PANEL_COUNT)])

    @field_validator("panels")
    @classmethod
    def _exactly_five_panels(cls, value: list[Panel]) -> list[Panel]:
        panels = list(value[:PANEL_COUNT])
        while len(panels) < PANEL_COUNT:
            panels.append(Panel())
        return panels


class DeviceConfig(BaseModel):
    """What the wizard learned about the user's Times Gate."""

    host: str | None = None
    port: int = 80
    protocol: Literal["hw400", "hw402"] = "hw400"
    local_token: int | None = None
    name: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.host)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class AppSettings(BaseModel):
    refresh_interval: float = 1.5
    allow_lan: bool = False
    auto_push: bool = False

    @field_validator("refresh_interval")
    @classmethod
    def _validate_interval(cls, value: float) -> float:
        return max(0.5, min(10.0, value))


class AppConfig(BaseModel):
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    settings: AppSettings = Field(default_factory=AppSettings)
    theme: Theme = Field(default_factory=lambda: Theme(name="Untitled"))
