"""Sensor collector tests — no privileged hardware access required."""

from __future__ import annotations

import time

from gate_studio.sensors import METRIC_KEYS, HardwareReader, SensorCollector


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
