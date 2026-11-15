"""Best-effort CPU/GPU readings that need more than psutil.

* NVIDIA GPUs: NVML (no elevation needed).
* CPU/AMD/Intel temperatures and loads: LibreHardwareMonitor's local web server
  (0.9.5+) or, for older installs, the WMI namespace it used to expose. Windows
  itself has no unprivileged CPU-temperature API, so a helper has to be running.

Every source is optional. When one is missing the value stays ``None`` so the
panel shows ``--`` instead of a wrong number, and nothing here ever raises into
the sampling loop.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass

RETRY_SECONDS = 30.0
LHM_REFRESH_SECONDS = 2.0
LHM_DATA_URL = "http://127.0.0.1:8085/data.json"
LHM_HTTP_TIMEOUT = 1.5

SENSOR_NAMESPACES: tuple[tuple[str, str], ...] = (
    ("root/LibreHardwareMonitor", "LibreHardwareMonitor (WMI)"),
    ("root/OpenHardwareMonitor", "OpenHardwareMonitor (WMI)"),
)

CPU_TEMP_HINT = (
    "Windows has no unprivileged CPU-temperature API. The app can install "
    "LibreHardwareMonitor and switch on its local sensor server (Troubleshooting → "
    "Enable CPU temperature); the reading appears within 30 seconds. NVIDIA GPU "
    "readings work without it; AMD and Intel GPU readings need it."
)

NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def _number(raw: object) -> float | None:
    """Pull the numeric part out of LHM's values, e.g. ``"65.0 °C"``."""
    if isinstance(raw, (int, float)):
        return float(raw)
    match = NUMBER.search(str(raw or ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


@dataclass
class _GpuReadings:
    """One physical GPU's sensors, collected before choosing a primary GPU."""

    key: str
    vendor: str
    temp_core: float | None = None
    temp_any: float | None = None
    load_core: float | None = None
    load_3d: float | None = None
    memory_used: float | None = None
    memory_total: float | None = None
    dedicated_used: float | None = None
    dedicated_total: float | None = None
    shared_used: float | None = None
    shared_total: float | None = None
    fan_control: float | None = None

    @property
    def score(self) -> int:
        """Prefer the GPU with the most usable readings, then a dGPU over an iGPU."""
        score = 0
        score += 4 if self.temp_core is not None or self.temp_any is not None else 0
        score += 4 if self.load_core is not None else 0
        score += 1 if self.load_3d is not None else 0
        score += 4 if self.memory_pair is not None else 0
        score += 2 if self.fan_control is not None else 0
        score += 3 if self.vendor in ("amd", "nvidia") else 0
        return score

    @property
    def memory_pair(self) -> tuple[float, float] | None:
        for used, total in (
            (self.memory_used, self.memory_total),
            (self.dedicated_used, self.dedicated_total),
            (self.shared_used, self.shared_total),
        ):
            if used is not None and total is not None and total > 0:
                return used, total
        return None


def _percent(used: float | None, total: float | None) -> float | None:
    if used is None or total is None or total <= 0:
        return None
    return round(max(0.0, min(100.0, used / total * 100.0)), 1)


def _gpu_group(identifier: str) -> tuple[str, str] | None:
    """Return ``(/gpu-amd/0, amd)``-style group and vendor for a GPU sensor id."""
    if not identifier.startswith("/gpu"):
        return None
    parts = identifier.split("/")
    if len(parts) < 4:
        return None
    vendor = parts[1].removeprefix("gpu-")
    return "/".join(parts[:3]), vendor


def _add_gpu_sensor(
    gpu: _GpuReadings,
    kind: str,
    name: str,
    value: float,
) -> None:
    """Map LibreHardwareMonitor's sensor names for NVIDIA, AMD and Intel GPUs."""
    if kind == "temperature":
        if "core" in name or name in ("gpu", "gpu temperature"):
            if gpu.temp_core is None:
                gpu.temp_core = value
        elif "hot spot" in name or "junction" in name or "gpu" in name:
            if gpu.temp_any is None:
                gpu.temp_any = value
    elif kind == "load":
        if "memory" in name:
            return
        if name in ("gpu core", "gpu") or ("core" in name and "soc" not in name):
            if gpu.load_core is None:
                gpu.load_core = value
        elif "3d" in name or "render" in name:
            if gpu.load_3d is None:
                gpu.load_3d = value
    elif kind in ("data", "smalldata"):
        if "gpu memory used" in name:
            gpu.memory_used = value
        elif "gpu memory total" in name:
            gpu.memory_total = value
        elif "d3d dedicated memory used" in name:
            gpu.dedicated_used = value
        elif "d3d dedicated memory total" in name:
            gpu.dedicated_total = value
        elif "d3d shared memory used" in name:
            gpu.shared_used = value
        elif "d3d shared memory total" in name:
            gpu.shared_total = value
    elif kind == "control" and "fan" in name:
        if gpu.fan_control is None:
            gpu.fan_control = value


def parse_lhm_payload(payload: object) -> dict[str, float | None]:
    """Read CPU/GPU values out of LibreHardwareMonitor's ``data.json`` tree."""
    cpu_package = cpu_tctl = cpu_max = cpu_average = cpu_any = None
    gpus: dict[str, _GpuReadings] = {}

    stack = [payload]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        stack.extend(node.get("Children") or [])
        identifier = str(node.get("SensorId") or "").lower()
        kind = str(node.get("Type") or "").lower()
        name = str(node.get("Text") or "").strip().lower()
        if not identifier or not kind:
            continue
        value = _number(node.get("Value"))
        if value is None:
            continue
        is_cpu = identifier.startswith(("/intelcpu", "/amdcpu", "/cpu"))
        if kind == "temperature" and is_cpu:
            if "package" in name and cpu_package is None:
                cpu_package = value
            elif "tctl" in name and cpu_tctl is None:
                cpu_tctl = value
            elif "core max" in name and cpu_max is None:
                cpu_max = value
            elif "core average" in name and cpu_average is None:
                cpu_average = value
            elif "distance" not in name and cpu_any is None:
                cpu_any = value
            continue
        group = _gpu_group(identifier)
        if group is None:
            continue
        key, vendor = group
        gpu = gpus.setdefault(key, _GpuReadings(key=key, vendor=vendor))
        _add_gpu_sensor(gpu, kind, name, value)

    cpu_temp = cpu_package
    for candidate in (cpu_tctl, cpu_max, cpu_average, cpu_any):
        if cpu_temp is None:
            cpu_temp = candidate
    gpu = max(gpus.values(), key=lambda item: (item.score, item.key)) if gpus else None
    return {
        "cpu_temp": cpu_temp,
        "gpu_temp": (gpu.temp_core if gpu and gpu.temp_core is not None else gpu.temp_any if gpu else None),
        "gpu_percent": (gpu.load_core if gpu and gpu.load_core is not None else gpu.load_3d if gpu else None),
        "vram_percent": (_percent(*gpu.memory_pair) if gpu and gpu.memory_pair else None),
        # A fan's RPM is not a percentage. Only expose the Control sensor,
        # which LHM reports in percent; otherwise leave it as "--".
        "fan_percent": (
            round(max(0.0, min(100.0, gpu.fan_control)), 1)
            if gpu and gpu.fan_control is not None
            else None
        ),
    }


class HardwareReader:
    def __init__(self) -> None:
        self._nvml: tuple[object, object] | None = None
        self._nvml_failed_at: float | None = None
        self._lhm_conn: object | None = None
        self._lhm_failed_at: float | None = None
        self._lhm_http_failed_at: float | None = None
        self._lhm_last_read = 0.0
        self._lhm_values: dict[str, float | None] = {}
        self._sensor_source: str | None = None
        self._cpu_temp_source: str | None = None

    # -- NVIDIA --------------------------------------------------------
    def _nvml_handle(self) -> tuple[object, object] | None:
        if self._nvml is not None:
            return self._nvml
        if self._nvml_failed_at and time.time() - self._nvml_failed_at < RETRY_SECONDS:
            return None
        try:
            import pynvml  # provided by nvidia-ml-py

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml = (pynvml, handle)
            return self._nvml
        except Exception:  # noqa: BLE001 - any driver/library problem means "no GPU data"
            self._nvml_failed_at = time.time()
            return None

    def nvidia(self) -> dict[str, float | None]:
        values: dict[str, float | None] = {}
        handle_pair = self._nvml_handle()
        if handle_pair is None:
            return values
        pynvml, handle = handle_pair
        try:
            values["gpu_percent"] = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
        except Exception:  # noqa: BLE001
            pass
        try:
            values["gpu_temp"] = float(
                pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            if memory.total:
                values["vram_percent"] = round(memory.used / memory.total * 100, 1)
        except Exception:  # noqa: BLE001
            pass
        try:
            fan = pynvml.nvmlDeviceGetFanSpeed(handle)
            if fan is not None:
                values["fan_percent"] = float(fan)
        except Exception:  # noqa: BLE001
            pass
        return values

    # -- LibreHardwareMonitor -----------------------------------------
    def _lhm_http(self) -> dict[str, float | None] | None:
        """LibreHardwareMonitor 0.9.5+ publishes sensors only over HTTP."""
        if sys.platform != "win32":
            return None
        if self._lhm_http_failed_at and time.time() - self._lhm_http_failed_at < RETRY_SECONDS:
            return None
        try:
            with urllib.request.urlopen(LHM_DATA_URL, timeout=LHM_HTTP_TIMEOUT) as response:
                if response.status != 200:
                    raise OSError(f"HTTP {response.status}")
                payload = json.load(response)
        except Exception:  # noqa: BLE001 - server off, wrong version or port
            self._lhm_http_failed_at = time.time()
            return None
        self._lhm_http_failed_at = None
        self._sensor_source = "LibreHardwareMonitor (web)"
        return parse_lhm_payload(payload)

    def _lhm_wmi(self) -> object | None:
        if sys.platform != "win32":
            return None
        if self._lhm_conn is not None:
            return self._lhm_conn
        if self._lhm_failed_at and time.time() - self._lhm_failed_at < RETRY_SECONDS:
            return None
        try:
            import wmi
        except Exception:  # noqa: BLE001 - wmi/pywin32 missing means no helper data
            self._lhm_failed_at = time.time()
            return None
        for namespace, label in SENSOR_NAMESPACES:
            try:
                conn = wmi.WMI(namespace=namespace)
                if not conn.Sensor():
                    continue
                self._lhm_conn = conn
                self._sensor_source = label
                return conn
            except Exception:  # noqa: BLE001 - namespace absent or not permitted
                continue
        self._lhm_failed_at = time.time()
        return None

    def _lhm_from_wmi(self, conn: object) -> dict[str, float | None]:
        try:
            sensors = conn.Sensor()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - the helper may have been closed
            self._lhm_conn = None
            self._lhm_failed_at = time.time()
            return {}

        cpu_temp: float | None = None
        cpu_package: float | None = None
        gpus: dict[str, _GpuReadings] = {}

        for sensor in sensors:
            identifier = (getattr(sensor, "Identifier", "") or "").lower()
            name = (getattr(sensor, "Name", "") or "").lower()
            kind = (getattr(sensor, "SensorType", "") or "").lower()
            try:
                value = float(getattr(sensor, "Value", "nan"))
            except (TypeError, ValueError):
                continue
            if value != value:  # NaN
                continue
            is_cpu = "cpu" in identifier
            if kind == "temperature" and is_cpu:
                if "package" in name or "core average" in name or name == "cpu":
                    cpu_package = value if cpu_package is None else cpu_package
                elif cpu_temp is None:
                    cpu_temp = value
                continue
            group = _gpu_group(identifier)
            if group is None:
                continue
            key, vendor = group
            gpu = gpus.setdefault(key, _GpuReadings(key=key, vendor=vendor))
            _add_gpu_sensor(gpu, kind, name, value)

        gpu = max(gpus.values(), key=lambda item: (item.score, item.key)) if gpus else None

        return {
            "cpu_temp": cpu_package if cpu_package is not None else cpu_temp,
            "gpu_temp": (gpu.temp_core if gpu and gpu.temp_core is not None else gpu.temp_any if gpu else None),
            "gpu_percent": (gpu.load_core if gpu and gpu.load_core is not None else gpu.load_3d if gpu else None),
            "vram_percent": (_percent(*gpu.memory_pair) if gpu and gpu.memory_pair else None),
            "fan_percent": (
                round(max(0.0, min(100.0, gpu.fan_control)), 1)
                if gpu and gpu.fan_control is not None
                else None
            ),
        }

    def libre_hardware_monitor(self) -> dict[str, float | None]:
        if time.time() - self._lhm_last_read < LHM_REFRESH_SECONDS:
            return dict(self._lhm_values)

        values = self._lhm_http()
        if values is None:
            conn = self._lhm_wmi()
            values = self._lhm_from_wmi(conn) if conn is not None else {}
        if not values:
            return {}

        if values.get("cpu_temp") is not None:
            self._cpu_temp_source = self._sensor_source
        self._lhm_values = values
        self._lhm_last_read = time.time()
        return dict(values)

    # -- diagnostics ---------------------------------------------------
    def describe(self) -> dict[str, object]:
        """What the sensors can see right now, for the Troubleshooting panel."""
        return {
            "nvidia": self._nvml is not None,
            "cpu_temp_source": self._cpu_temp_source,
            "cpu_temp_hint": None if self._cpu_temp_source else CPU_TEMP_HINT,
        }

    # -- combined ------------------------------------------------------
    def sample(self) -> dict[str, float | None]:
        values: dict[str, float | None] = {}
        for source in (self.nvidia, self.libre_hardware_monitor):
            try:
                for key, value in source().items():
                    if value is not None and values.get(key) is None:
                        values[key] = value
            except Exception:  # noqa: BLE001 - a broken source must not stop sampling
                continue
        return values
