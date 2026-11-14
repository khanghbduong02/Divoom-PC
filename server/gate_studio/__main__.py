"""Start the local agent: ``python -m gate_studio`` or the packaged executable."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn

from . import desktop
from .api import SENSOR_SETUP_SCRIPT, create_app
from .config import ConfigStore
from .device import discover_cloud
from .device.errors import DeviceError

log = logging.getLogger("gate_studio")


def lan_address() -> str | None:
    """Best-effort LAN IP of this machine (no packets are actually sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def offer_sensor_setup(store: ConfigStore) -> None:
    """Ask once, on the first packaged run, to install the CPU sensor helper.

    The helper needs one administrator approval. Keeping the prompt here means the
    downloaded exe asks for it itself, while normal logins stay non-elevated (no UAC
    on every boot). Declining leaves the Troubleshooting button available.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    if not SENSOR_SETUP_SCRIPT.exists():
        return
    marker = store.data_dir / "sensor-setup-offered"
    if marker.exists():
        return
    installed = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "GateThemeStudio"
        / "LibreHardwareMonitor"
        / "LibreHardwareMonitor.exe"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    if installed.exists():
        try:
            marker.write_text("installed\n", encoding="utf-8")
        except OSError:
            pass
        return
    message = (
        "Gate Theme Studio can show CPU temperature after installing a small\n"
        "sensor helper (LibreHardwareMonitor) and its signed PawnIO driver.\n\n"
        "Windows will ask for administrator permission once. After that the helper\n"
        "starts automatically with Windows, and this app keeps running normally.\n\n"
        "Install it now?"
    )
    answer = ctypes.windll.user32.MessageBoxW(
        None, message, "Gate Theme Studio", 0x4 | 0x20  # MB_YESNO | MB_ICONQUESTION
    )
    try:
        marker.write_text("yes\n" if answer == 6 else "declined\n", encoding="utf-8")
    except OSError:
        pass
    if answer != 6:  # IDYES
        return
    params = f'-NoProfile -ExecutionPolicy Bypass -File "{SENSOR_SETUP_SCRIPT}"'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, None, 1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gate-studio", description="Divoom Times Gate theme editor")
    parser.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=None, help="override the app data folder")
    parser.add_argument("--lan", action="store_true", help="also allow other devices on the LAN")
    parser.add_argument("--silent", action="store_true", help="do not open a browser (autostart)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-tray", action="store_true")
    parser.add_argument("--no-discovery", action="store_true", help="skip the startup LAN discovery")
    parser.add_argument(
        "--no-autostart", action="store_true", help="do not register at login (used by smoke tests)"
    )
    return parser.parse_args(argv)


def setup_logging(store: ConfigStore) -> None:
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(store.data_dir / "agent.log", encoding="utf-8"))
    except OSError:
        pass
    if not getattr(sys, "frozen", False):
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers or None,
    )


def already_running(port: int, token: str) -> bool:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=1.0) as reply:
            payload = json.loads(reply.read())
    except Exception:  # noqa: BLE001 - anything here means "not our agent"
        return False
    return bool(payload.get("ok")) and "version" in payload


class LocalApi:
    """Tiny client the tray menu uses to talk to its own agent."""

    def __init__(self, port: int, token: str) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None) -> dict | None:
        request = urllib.request.Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as reply:
                return json.loads(reply.read() or b"{}")
        except Exception as exc:  # noqa: BLE001 - tray actions must never crash
            log.warning("local api %s %s failed: %s", method, path, exc)
            return None


def run_tray_session(server: uvicorn.Server, api: LocalApi, url: str, settings: dict) -> None:
    updates = {"enabled": bool(settings.get("auto_push", True))}

    def open_editor() -> None:
        webbrowser.open(url)

    def send_now() -> None:
        api.call("POST", "/api/send")

    def toggle_updates() -> None:
        updates["enabled"] = not updates["enabled"]
        api.call("PUT", "/api/config/settings", {"auto_push": updates["enabled"]})

    def open_settings() -> None:
        webbrowser.open(url + "&settings=1")

    def quit_app() -> None:
        server.should_exit = True

    icon = desktop.run_tray(
        open_editor=open_editor,
        send_now=send_now,
        toggle_updates=toggle_updates,
        open_settings=open_settings,
        quit_app=quit_app,
        updates_enabled=lambda: updates["enabled"],
    )
    if icon is None:
        return
    # the tray loop ended, so the user asked to quit (or the session closed)
    server.should_exit = True


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    store = ConfigStore(Path(args.data_dir) if args.data_dir else None)
    config = store.load()
    setup_logging(store)
    token = store.token()

    bind_lan = args.lan or config.settings.allow_lan
    host = args.host or ("0.0.0.0" if bind_lan else "127.0.0.1")
    url = f"http://localhost:{args.port}/?token={quote(token)}"

    if already_running(args.port, token):
        print("Gate Theme Studio is already running — opening the editor.")
        if not (args.no_browser or args.silent):
            webbrowser.open(url)
        return

    # A packaged build keeps itself registered at login; source checkouts do not
    # touch the registry unless the user flips the switch in Settings.
    if getattr(sys, "frozen", False) and config.settings.autostart and not args.no_autostart:
        desktop.set_autostart(True)

    app = create_app(store)
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=args.port, log_level="warning", log_config=None)
    )
    thread = threading.Thread(target=server.run, name="agent-http", daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)

    print("Gate Theme Studio")
    print(f"  editor : {url}")
    print(f"  data   : {store.data_dir}")
    if bind_lan:
        address = lan_address() or "<this-pc-ip>"
        print(f"  phone  : http://{address}:{args.port}/?token={quote(token)}")
        print("  warning: the editor is reachable from your whole network while this runs.")
    if config.device.configured:
        print(f"  device : {config.device.host}:{config.device.port} ({config.device.protocol})")
        print(
            "  updates: "
            + (
                f"on, every {config.settings.push_interval:g}s"
                if config.settings.auto_push
                else "paused"
            )
        )
    else:
        print("  device : not configured — use the connection wizard in the editor")

    if not args.no_discovery and not config.device.configured:
        def _announce() -> None:
            try:
                found = discover_cloud(timeout=4.0)
            except DeviceError:
                return
            for device in found:
                print(f"  found  : {device.get('name') or 'Times Gate'} at {device.get('ip')}")

        threading.Thread(target=_announce, name="startup-discovery", daemon=True).start()

    if not (args.silent or args.no_browser or args.no_tray):
        offer_sensor_setup(store)

    if not (args.no_browser or args.silent):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    if not args.no_tray:
        try:
            run_tray_session(
                server,
                LocalApi(args.port, token),
                url,
                {
                    "auto_push": config.settings.auto_push,
                },
            )
        except KeyboardInterrupt:
            pass
        server.should_exit = True
    else:
        # headless: the HTTP thread owns the lifetime
        try:
            while thread.is_alive():
                thread.join(timeout=0.5)
        except KeyboardInterrupt:
            server.should_exit = True

    thread.join(timeout=5)
    log.info("agent stopped")


if __name__ == "__main__":
    main()
