"""Sensor collector tests — no privileged hardware access required."""

from __future__ import annotations

import time

from gate_studio.sensors import METRIC_KEYS, HardwareReader, SensorCollector
from gate_studio.sensors.hardware import parse_lhm_payload


def test_snapshot_has_every_metric_key() -> None:
    collector = SensorCollector()
    snapshot = collector.snapshot()
    assert set(snapshot) == set(METRIC_KEYS)
    assert all(value is None for value in snapshot.values())


def test_collector_fills_psutil_metrics_and_history() -> None:
    collector = SensorCollector(interval=0.2)
    collector.start()
    try:
        collector.wait_for_first_sample(timeout=3.0)
        snapshot = collector.snapshot()
        history = collector.history()
    finally:
        collector.stop()

    assert snapshot["cpu_percent"] is not None
    assert snapshot["ram_percent"] is not None
    assert 0 <= float(snapshot["ram_percent"]) <= 100
    assert len(history["cpu_percent"]) >= 1
    assert set(history) == set(METRIC_KEYS)


def test_hardware_reader_never_raises_and_reports_only_known_keys() -> None:
    reader = HardwareReader()
    values = reader.sample()
    assert isinstance(values, dict)
    for key, value in values.items():
        assert key in METRIC_KEYS
        assert value is None or isinstance(value, float)


def test_lhm_web_payload_prefers_cpu_package_and_reads_gpu() -> None:
    payload = {
        "Text": "Sensor",
        "Children": [
            {
                "Text": "PC",
                "Children": [
                    {
                        "Text": "Intel Core i9",
                        "Children": [
                            {
                                "Text": "Temperatures",
                                "Children": [
                                    {"Text": "Core Max", "Type": "Temperature", "SensorId": "/intelcpu/0/temperature/0", "Value": "72.0 °C"},
                                    {"Text": "CPU Package", "Type": "Temperature", "SensorId": "/intelcpu/0/temperature/26", "Value": "65.0 °C"},
                                ],
                            }
                        ],
                    },
                    {
                        "Text": "NVIDIA",
                        "Children": [
                            {"Text": "GPU Core", "Type": "Temperature", "SensorId": "/gpu-nvidia/0/temperature/0", "Value": "41.8 °C"},
                            {"Text": "GPU Core", "Type": "Load", "SensorId": "/gpu-nvidia/0/load/0", "Value": "12.0 %"},
                        ],
                    },
                ],
            }
        ],
    }
    values = parse_lhm_payload(payload)
    assert values["cpu_temp"] == 65.0
    assert values["gpu_temp"] == 41.8
    assert values["gpu_percent"] == 12.0


def test_lhm_web_payload_uses_core_max_when_package_is_absent() -> None:
    payload = {
        "Children": [
            {
                "Text": "AMD Ryzen",
                "Children": [
                    {"Text": "Core Max", "Type": "Temperature", "SensorId": "/amdcpu/0/temperature/0", "Value": "55.5 °C"}
                ],
            }
        ]
    }
    assert parse_lhm_payload(payload)["cpu_temp"] == 55.5


def test_lhm_reads_amd_gpu_load_vram_and_fan_control() -> None:
    payload = {
        "Children": [
            {
                "Text": "AMD Radeon RX 7800 XT",
                "Children": [
                    {"Text": "GPU Core", "Type": "Temperature", "SensorId": "/gpu-amd/0/temperature/0", "Value": "47.0 °C"},
                    {"Text": "GPU Core", "Type": "Load", "SensorId": "/gpu-amd/0/load/0", "Value": "0.0 %"},
                    {"Text": "GPU Memory Used", "Type": "Data", "SensorId": "/gpu-amd/0/data/0", "Value": "3000.0 MB"},
                    {"Text": "GPU Memory Total", "Type": "Data", "SensorId": "/gpu-amd/0/data/2", "Value": "12000.0 MB"},
                    {"Text": "GPU Fan", "Type": "Control", "SensorId": "/gpu-amd/0/control/0", "Value": "35.0 %"},
                    {"Text": "GPU Fan", "Type": "Fan", "SensorId": "/gpu-amd/0/fan/0", "Value": "1200 RPM"},
                ],
            }
        ]
    }
    values = parse_lhm_payload(payload)
    assert values["gpu_temp"] == 47.0
    assert values["gpu_percent"] == 0.0
    assert values["vram_percent"] == 25.0
    assert values["fan_percent"] == 35.0


def test_lhm_reads_intel_integrated_gpu_shared_memory() -> None:
    payload = {
        "Children": [
            {
                "Text": "Intel UHD Graphics",
                "Children": [
                    {"Text": "GPU Core", "Type": "Temperature", "SensorId": "/gpu-intel-integrated/0/temperature/0", "Value": "45.0 °C"},
                    {"Text": "D3D 3D", "Type": "Load", "SensorId": "/gpu-intel-integrated/0/load/3", "Value": "12.0 %"},
                    {"Text": "D3D Dedicated Memory Used", "Type": "Data", "SensorId": "/gpu-intel-integrated/0/data/0", "Value": "512.0 MB"},
                    {"Text": "D3D Shared Memory Used", "Type": "Data", "SensorId": "/gpu-intel-integrated/0/data/1", "Value": "2048.0 MB"},
                    {"Text": "D3D Shared Memory Total", "Type": "Data", "SensorId": "/gpu-intel-integrated/0/data/2", "Value": "8192.0 MB"},
                ],
            }
        ]
    }
    values = parse_lhm_payload(payload)
    assert values["gpu_temp"] == 45.0
    assert values["gpu_percent"] == 12.0
    assert values["vram_percent"] == 25.0


def test_lhm_does_not_report_fan_rpm_as_a_percentage() -> None:
    payload = {
        "Children": [
            {
                "Text": "AMD Radeon",
                "Children": [
                    {"Text": "GPU Core", "Type": "Temperature", "SensorId": "/gpu-amd/0/temperature/0", "Value": "40.0 °C"},
                    {"Text": "GPU Fan", "Type": "Fan", "SensorId": "/gpu-amd/0/fan/0", "Value": "1200 RPM"},
                ],
            }
        ]
    }
    assert parse_lhm_payload(payload)["fan_percent"] is None


def test_collector_survives_a_failing_hardware_reader(monkeypatch) -> None:
    collector = SensorCollector()

    def boom() -> dict[str, float | None]:
        raise RuntimeError("WMI exploded")

    monkeypatch.setattr(collector._hardware, "sample", boom)
    collector._sample()
    assert collector.snapshot()["cpu_percent"] is not None


def test_net_rates_are_non_negative() -> None:
    collector = SensorCollector()
    collector._sample()
    time.sleep(0.05)
    collector._sample()
    snapshot = collector.snapshot()
    for key in ("net_up", "net_down"):
        assert snapshot[key] is None or snapshot[key] >= 0


def test_history_window_keeps_timestamps_and_filters_old_samples() -> None:
    collector = SensorCollector(interval=0.2)
    collector._sample()
    time.sleep(0.05)
    collector._sample()
    window = collector.history_window(60)
    stamps = [stamp for stamp, _ in window["cpu_percent"]]
    assert len(stamps) >= 2
    assert stamps == sorted(stamps)
    future = collector.history_window(60, now=time.time() + 3600)
    assert future["cpu_percent"] == []


def test_history_bounds_are_configurable() -> None:
    collector = SensorCollector(interval=0.5, history_seconds=3600)
    assert collector._history["cpu_percent"].maxlen >= 7200
    assert collector.history()["cpu_percent"] == []
