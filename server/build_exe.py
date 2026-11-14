"""Build GateThemeStudio.exe — one file, no Python needed on the user's PC.

    pip install pyinstaller
    python build_exe.py

The executable lands in ``server/dist/GateThemeStudio.exe``. It starts the local
agent, opens the editor, adds itself to the Windows startup list and lives in the
system tray.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "gate_studio"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
TOOLS = ROOT.parent / "tools"
SENSOR_HELPER = TOOLS / "LibreHardwareMonitor"
SENSOR_SETUP = TOOLS / "setup-sensors.ps1"


def make_icon(path: Path) -> Path | None:
    """Render the tray logo to an .ico so the exe has a real icon."""
    try:
        from gate_studio.desktop import tray_image
    except Exception:  # noqa: BLE001 - icon is cosmetic
        return None
    try:
        image = tray_image(256)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return path
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    if not (PACKAGE / "static" / "index.html").exists():
        print("The editor bundle is missing. Run `npm install && npm run build` in ui/ first.")
        return 1
    if not (SENSOR_HELPER / "LibreHardwareMonitor.exe").exists() or not SENSOR_SETUP.exists():
        print(
            "The CPU sensor helper is missing. Put LibreHardwareMonitor 0.9.6 in "
            f"{SENSOR_HELPER} (download it from the LHM GitHub releases) and keep "
            f"{SENSOR_SETUP.name} there."
        )
        return 1

    icon = make_icon(BUILD / "app.ico")
    separator = ";" if os.name == "nt" else ":"

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "GateThemeStudio",
        "--add-data",
        f"{PACKAGE / 'presets'}{separator}gate_studio/presets",
        "--add-data",
        f"{PACKAGE / 'static'}{separator}gate_studio/static",
        "--add-data",
        f"{SENSOR_HELPER}{separator}tools/LibreHardwareMonitor",
        "--add-data",
        f"{SENSOR_SETUP}{separator}tools",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.loops.asyncio",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "pystray._win32",
    ]
    if icon is not None:
        args += ["--icon", str(icon)]
    args.append(str(ROOT / "run_agent.py"))

    print("Building GateThemeStudio.exe …")
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    produced = DIST / ("GateThemeStudio.exe" if os.name == "nt" else "GateThemeStudio")
    if produced.exists():
        size_mb = produced.stat().st_size / (1024 * 1024)
        print(f"Done: {produced} ({size_mb:.1f} MB)")
    spec = ROOT / "GateThemeStudio.spec"
    if spec.exists():
        spec.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
