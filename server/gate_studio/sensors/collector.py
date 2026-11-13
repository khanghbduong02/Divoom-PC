"""Background sampling of every metric a panel can show."""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from threading import Event, Lock, Thread

import psutil

from .hardware import HardwareReader

METRIC_KEYS: tuple[str, ...] = (
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

HISTORY_LENGTH = 60


def _disk_path() -> str:
    if sys.platform == "win32":
        return f"{os.environ.get('SystemDrive', 'C:')}\\"
    return "/"


class SensorCollector:
    """Samples on its own thread so a slow WMI query never stalls a request."""

    def __init__(self, interval: float = 1.0, history: int = HISTORY_LENGTH) -> None:
        self.interval = max(0.2, interval)
        self._values: dict[str, float | None] = {key: None for key in METRIC_KEYS}
        self._history: dict[str, deque[float | None]] = {
            key: deque(maxlen=history) for key in METRIC_KEYS
        }
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._hardware = HardwareReader()
        self._last_net: tuple[float, float] | None = None
        self._last_net_at: float | None = None
        self.psutil_ok = True

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        psutil.cpu_percent(interval=None)  # prime the counter
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="sensor-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._sample()
            except Exception:  # noqa: BLE001 - sampling must survive a bad tick
                self.psutil_ok = False
            self._stop.wait(self.interval)

    # -- sampling ------------------------------------------------------
    def _sample(self) -> None:
        values: dict[str, float | None] = {key: None for key in METRIC_KEYS}

        values["cpu_percent"] = round(psutil.cpu_percent(interval=None), 1)
        values["ram_percent"] = round(psutil.virtual_memory().percent, 1)
        try:
            values["disk_percent"] = round(psutil.disk_usage(_disk_path()).percent, 1)
        except OSError:
            values["disk_percent"] = None

        now = time.monotonic()
        counters = psutil.net_io_counters()
        if counters is not None:
            if self._last_net is not None and self._last_net_at is not None:
                elapsed = max(1e-3, now - self._last_net_at)
                sent = (counters.bytes_sent - self._last_net[0]) / elapsed / 1_000_000
                received = (counters.bytes_recv - self._last_net[1]) / elapsed / 1_000_000
                values["net_up"] = round(max(0.0, sent), 2)
                values["net_down"] = round(max(0.0, received), 2)
            self._last_net = (counters.bytes_sent, counters.bytes_recv)
            self._last_net_at = now

        try:
            hardware_values = self._hardware.sample()
        except Exception:  # noqa: BLE001 - a dead sensor source must not blank the rest
            hardware_values = {}
        for key, value in hardware_values.items():
            if key in values and value is not None:
                values[key] = round(float(value), 1)

        with self._lock:
            self._values = values
            for key, value in values.items():
                self._history[key].append(value)

    # -- readers -------------------------------------------------------
    def snapshot(self) -> dict[str, float | None]:
        with self._lock:
            return dict(self._values)

    def history(self) -> dict[str, list[float | None]]:
        with self._lock:
            return {key: list(samples) for key, samples in self._history.items()}

    def wait_for_first_sample(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if any(value is not None for value in self._values.values()):
                    return
            time.sleep(0.05)
