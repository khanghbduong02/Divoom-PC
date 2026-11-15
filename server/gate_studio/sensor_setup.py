"""Bootstrap the optional Windows sensor helper.

The app works without this helper (CPU/RAM/disk/network and NVIDIA GPU values
still work).  CPU temperature needs LibreHardwareMonitor, which in turn needs
the signed PawnIO driver and an elevated one-time install.

The packaged exe carries LibreHardwareMonitor and the setup script.  Source
checkouts can use the same script; it downloads LibreHardwareMonitor if the
ignored tools/ folder is not present.  This module only handles the parts that
do not need administrator rights: finding the installed helper, starting its
scheduled task, and showing the installer prompt.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LHM_TASK = "LibreHardwareMonitor"
LHM_DATA_URL = "http://127.0.0.1:8085/data.json"


def helper_exe() -> Path | None:
    """Return the installed helper executable, if it exists."""
    appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    exe = appdata / "GateThemeStudio" / "LibreHardwareMonitor" / "LibreHardwareMonitor.exe"
    return exe if exe.is_file() else None


def helper_installed() -> bool:
    return helper_exe() is not None


def helper_running(timeout: float = 1.0) -> bool:
    if sys.platform != "win32":
        return False
    try:
        with urllib.request.urlopen(LHM_DATA_URL, timeout=timeout) as response:
            return response.status == 200
    except Exception:  # noqa: BLE001 - any failure means "not running"
        return False


def _task_exists() -> bool:
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", LHM_TASK],
            capture_output=True,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _run_task() -> bool:
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Run", "/TN", LHM_TASK],
            capture_output=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def start_helper(wait_seconds: float = 4.0) -> bool:
    """Start the installed helper without elevation, preferring its logon task."""
    if helper_running():
        return True
    exe = helper_exe()
    if exe is None:
        return False

    if _task_exists() and _run_task():
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if helper_running():
                return True
            time.sleep(0.25)
        return False

    # A task can be missing after an older/manual install.  Starting the exe
    # directly still gives the helper a chance to open its local web server.
    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return False
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if helper_running():
            return True
        time.sleep(0.25)
    return False


def open_installer(script: Path) -> bool:
    """Open the elevated setup script through the normal Windows UAC prompt."""
    if sys.platform != "win32" or not script.is_file():
        return False
    params = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", params, None, 1
        )
    except Exception:  # noqa: BLE001 - a blocked prompt is not a crash
        return False
    return result > 32  # ShellExecute returns >32 on success


def _offer_message() -> str:
    return (
        "Gate Theme Studio can install the optional CPU temperature helper\n"
        "(LibreHardwareMonitor) and its signed PawnIO driver.\n\n"
        "Windows will ask for administrator permission once. The helper then\n"
        "starts automatically with Windows. CPU, RAM, disk, network, and NVIDIA\n"
        "GPU readings work without it; CPU temperature needs it.\n\n"
        "Install the sensor helper now?"
    )


def _ask_to_install() -> int:
    try:
        return int(
            ctypes.windll.user32.MessageBoxW(
                None, _offer_message(), "Gate Theme Studio", 0x4 | 0x20  # yes/no + question
            )
        )
    except Exception:  # noqa: BLE001 - no desktop session
        return 0


def ensure_sensor_helper(
    data_dir: Path,
    setup_script: Path,
    *,
    allow_prompt: bool = True,
) -> str:
    """Start an installed helper or offer the one-time installer.

    Returns a short state used by diagnostics and tests.  This never raises:
    sensor support is optional and must not prevent the app from starting.
    """
    if sys.platform != "win32":
        return "unsupported"
    if helper_installed():
        if helper_running():
            return "running"
        return "started" if start_helper() else "not-running"
    if not setup_script.is_file():
        return "no-installer"
    if not allow_prompt:
        return "not-installed"

    marker = Path(data_dir) / "sensor-setup-offered"
    if marker.exists():
        return "already-offered"

    marker.parent.mkdir(parents=True, exist_ok=True)
    answer = _ask_to_install()
    if answer == 0:
        return "prompt-unavailable"
    try:
        marker.write_text("yes\n" if answer == 6 else "declined\n", encoding="utf-8")
    except OSError:
        pass
    if answer != 6:  # IDYES
        return "declined"
    return "installing" if open_installer(setup_script) else "installer-blocked"
