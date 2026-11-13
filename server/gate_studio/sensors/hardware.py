"""Best-effort CPU/GPU readings that need more than psutil.

* NVIDIA GPUs: NVML (no elevation needed).
* CPU/AMD/Intel temperatures and loads: the WMI namespace exposed by
  LibreHardwareMonitor (or the older OpenHardwareMonitor). Windows itself has no
  unprivileged CPU-temperature API, so one of those helpers has to be running.

Every source is optional. When one is missing the value stays ``None`` so the
panel shows ``--`` instead of a wrong number, and nothing here ever raises into
the sampling loop.
"""

from __future__ import annotations

import sys
import time

RETRY_SECONDS = 30.0
LHM_REFRESH_SECONDS = 2.0

SENSOR_NAMESPACES: tuple[tuple[str, str], ...] = (
    ("root/LibreHardwareMonitor", "LibreHardwareMonitor"),
    ("root/OpenHardwareMonitor", "OpenHardwareMonitor"),
)

CPU_TEMP_HINT = (
    "Windows has no unprivileged CPU-temperature API. Install LibreHardwareMonitor "
    "(or OpenHardwareMonitor), run it as administrator and leave it running; this "
    "reading appears within 30 seconds. GPU temperatures work without it."
)


class HardwareReader:
    def __init__(self) -> None:
        self._nvml: tuple[object, object] | None = None
        self._nvml_failed_at: float | None = None
        self._lhm_conn: object | None = None
        self._lhm_failed_at: float | None = None
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
            if fan:
                values["fan_percent"] = float(fan)
        except Exception:  # noqa: BLE001
            pass
        return values

    # -- LibreHardwareMonitor -----------------------------------------
    def _lhm(self) -> object | None:
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

    def libre_hardware_monitor(self) -> dict[str, float | None]:
        if time.time() - self._lhm_last_read < LHM_REFRESH_SECONDS:
            return dict(self._lhm_values)
        conn = self._lhm()
        if conn is None:
            return {}
        try:
            sensors = conn.Sensor()
        except Exception:  # noqa: BLE001 - the helper may have been closed
            self._lhm_conn = None
            self._lhm_failed_at = time.time()
            return {}

        cpu_temp: float | None = None
        cpu_package: float | None = None
        gpu_temp: float | None = None
        gpu_load: float | None = None
        fan: float | None = None

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
            is_gpu = "gpu" in identifier
            if kind == "temperature" and is_cpu:
                if "package" in name or "core average" in name or name == "cpu":
                    cpu_package = value if cpu_package is None else cpu_package
                elif cpu_temp is None:
                    cpu_temp = value
            elif kind == "temperature" and is_gpu:
                if "core" in name or "gpu" in name:
                    gpu_temp = value if gpu_temp is None else gpu_temp
            elif kind == "load" and is_gpu and "core" in name:
                gpu_load = value
            elif kind == "fan" and is_gpu and fan is None:
                fan = value  # RPM on most boards; only used when NVML has no percentage

        values = {
            "cpu_temp": cpu_package if cpu_package is not None else cpu_temp,
            "gpu_temp": gpu_temp,
            "gpu_percent": gpu_load,
            "fan_percent": fan,
        }
        if values["cpu_temp"] is not None:
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
