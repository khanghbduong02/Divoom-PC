"""Desktop niceties: start-with-Windows and the tray icon.

Everything here is optional. On a machine where the registry or a system tray is
unavailable the agent still runs as a plain local web app.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

APP_NAME = "GateThemeStudio"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_supported() -> bool:
    return sys.platform == "win32"


def autostart_command() -> str:
    """The command Windows should run at login."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --silent'
    entry = Path(__file__).resolve().parent.parent / "run_agent.py"
    return f'"{sys.executable}" "{entry}" --silent'


def autostart_enabled() -> bool:
    if not autostart_supported():
        return False
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Add or remove the per-user Run entry. Returns the resulting state."""
    if not autostart_supported():
        return False
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        return autostart_enabled()
    return autostart_enabled()


def tray_image(size: int = 64):
    """Five ascending bars, drawn with Pillow so no icon file is needed."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = round(size * 0.12)
    gap = round(size * 0.06)
    bar = (size - 2 * margin - 3 * gap) / 4
    heights = (0.45, 0.65, 0.85, 1.0)
    for index, factor in enumerate(heights):
        left = margin + index * (bar + gap)
        top = size - margin - (size - 2 * margin) * factor
        draw.rounded_rectangle(
            (left, top, left + bar, size - margin),
            radius=max(1, round(bar / 4)),
            fill=(59, 110, 168, 255) if index % 2 else (36, 38, 42, 255),
        )
    return image


def run_tray(
    open_editor,
    send_now,
    toggle_updates,
    open_settings,
    quit_app,
    updates_enabled: Callable[[], bool],
):
    """Create and show a system-tray icon. Returns the icon, or None.

    The caller keeps a reference so the icon survives, and calls ``stop()`` on
    shutdown. Import failures (no pystray on this platform) are not fatal.
    """
    try:
        import pystray
    except Exception:  # noqa: BLE001 - tray support is optional
        return None

    def _call(action):
        def handler(icon, item):
            action()

        return handler

    def _quit(icon, item):
        quit_app()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open editor", _call(open_editor), default=True),
        pystray.MenuItem("Send to display now", _call(send_now)),
        pystray.MenuItem(
            "Keep panels updated",
            _call(toggle_updates),
            checked=lambda item: updates_enabled(),
        ),
        pystray.MenuItem("Settings…", _call(open_settings)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Gate Theme Studio", _quit),
    )
    icon = pystray.Icon(APP_NAME, tray_image(), "Gate Theme Studio", menu)
    try:
        icon.run()
    except Exception:  # noqa: BLE001 - e.g. no desktop session
        return None
    return icon
