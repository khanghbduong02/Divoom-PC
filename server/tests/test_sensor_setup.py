"""Tests for starting/installing the optional Windows sensor helper."""

from __future__ import annotations

from pathlib import Path

from gate_studio import sensor_setup


def test_helper_exe_points_at_the_installed_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    exe = tmp_path / "GateThemeStudio" / "LibreHardwareMonitor" / "LibreHardwareMonitor.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"helper")

    assert sensor_setup.helper_exe() == exe
    assert sensor_setup.helper_installed() is True


def test_installed_helper_is_started_without_another_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sensor_setup.sys, "platform", "win32")
    monkeypatch.setattr(sensor_setup, "helper_installed", lambda: True)
    monkeypatch.setattr(sensor_setup, "helper_running", lambda timeout=1.0: False)
    monkeypatch.setattr(sensor_setup, "start_helper", lambda: True)
    setup = tmp_path / "setup-sensors.ps1"
    setup.write_text("", encoding="utf-8")

    assert sensor_setup.ensure_sensor_helper(tmp_path, setup) == "started"


def test_first_run_offers_the_bundled_installer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sensor_setup.sys, "platform", "win32")
    monkeypatch.setattr(sensor_setup, "helper_installed", lambda: False)
    monkeypatch.setattr(sensor_setup, "_ask_to_install", lambda: 6)
    installed: list[Path] = []
    monkeypatch.setattr(
        sensor_setup, "open_installer", lambda script: installed.append(script) or True
    )
    setup = tmp_path / "setup-sensors.ps1"
    setup.write_text("", encoding="utf-8")

    assert sensor_setup.ensure_sensor_helper(tmp_path, setup) == "installing"
    assert installed == [setup]
    assert (tmp_path / "sensor-setup-offered").read_text(encoding="utf-8").strip() == "yes"


def test_declining_does_not_prompt_again(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sensor_setup.sys, "platform", "win32")
    monkeypatch.setattr(sensor_setup, "helper_installed", lambda: False)
    monkeypatch.setattr(sensor_setup, "_ask_to_install", lambda: 7)
    monkeypatch.setattr(sensor_setup, "open_installer", lambda script: True)
    setup = tmp_path / "setup-sensors.ps1"
    setup.write_text("", encoding="utf-8")

    assert sensor_setup.ensure_sensor_helper(tmp_path, setup) == "declined"
    assert sensor_setup.ensure_sensor_helper(tmp_path, setup) == "already-offered"


def test_silent_startup_does_not_show_a_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sensor_setup.sys, "platform", "win32")
    monkeypatch.setattr(sensor_setup, "helper_installed", lambda: False)
    setup = tmp_path / "setup-sensors.ps1"
    setup.write_text("", encoding="utf-8")

    assert (
        sensor_setup.ensure_sensor_helper(tmp_path, setup, allow_prompt=False)
        == "not-installed"
    )
