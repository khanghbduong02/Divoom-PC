"""Start the local agent: ``python -m gate_studio`` or the packaged executable."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn

from . import __version__, desktop
from .api import SENSOR_SETUP_SCRIPT, create_app
from .config import ConfigStore
from .device import discover_cloud
from .device.errors import DeviceError
from .sensor_setup import ensure_sensor_helper
from .update import recover_from_failed_update

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


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def existing_agent(port: int, token: str) -> tuple[str, str | None]:
    """Return ``("ours", version)``, ``("other", None)`` or ``("free", None)``.

    ``other`` means something is listening but does not accept this data
    folder's token.  Reporting that separately keeps a second launch from
    opening a browser at a server owned by the first copy.
    """
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=1.0) as reply:
            payload = json.loads(reply.read())
    except urllib.error.HTTPError:
        return ("other", None) if _port_open(port) else ("free", None)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ("other", None) if _port_open(port) else ("free", None)
    if not isinstance(payload, dict) or not bool(payload.get("ok")):
        return ("other", None)
    return ("ours", str(payload.get("version") or ""))


def wait_for_agent(port: int, token: str, timeout: float = 15.0) -> tuple[str, str | None]:
    """Wait out an old process during a restart before binding the port.

    The updater starts this exe as soon as the old file is replaced.  The old
    HTTP server can still be shutting down for a moment; binding immediately
    produces a Windows port-conflict dialog and no working app.
    """
    deadline = time.time() + timeout
    while True:
        status, version = existing_agent(port, token)
        if status == "free":
            return status, version
        if status == "ours" and version == __version__:
            return status, version
        if time.time() >= deadline:
            return status, version
        time.sleep(0.4)


def already_running(port: int, token: str) -> bool:
    status, _version = existing_agent(port, token)
    return status == "ours"


def report_port_conflict(port: int, silent: bool) -> None:
    """Explain a port conflict instead of opening a page with the wrong token."""
    message = (
        f"Gate Theme Studio could not start because port {port} is already in use.\n\n"
        "If Gate Theme Studio is already running, open the editor from its tray "
        "icon (Open editor). Otherwise close the program using that port and try "
        "again."
    )
    log.error(message)
    if silent:
        return
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        ctypes.windll.user32.MessageBoxW(
            None, message, "Gate Theme Studio", 0x10  # MB_ICONERROR
        )
    else:
        print(message)


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
    if recover_from_failed_update():
        return
    args = parse_args(argv)
    store = ConfigStore(Path(args.data_dir) if args.data_dir else None)
    config = store.load()
    setup_logging(store)
    token = store.token()

    bind_lan = args.lan or config.settings.allow_lan
    host = args.host or ("0.0.0.0" if bind_lan else "127.0.0.1")
    url = f"http://localhost:{args.port}/?token={quote(token)}"

    status, _version = wait_for_agent(args.port, token)
    if status == "ours":
        print("Gate Theme Studio is already running — opening the editor.")
        if not (args.no_browser or args.silent):
            webbrowser.open(url)
        return
    if status == "other":
        report_port_conflict(args.port, silent=args.silent)
        return

    # A packaged build keeps itself registered at login; source checkouts do not
    # touch the registry unless the user flips the switch in Settings.
    if getattr(sys, "frozen", False) and config.settings.autostart and not args.no_autostart:
        desktop.set_autostart(True)

    # An installed helper is started even when the app itself was launched at
    # login.  Only a normal windowed launch may show the one-time UAC prompt.
    sensor_state = ensure_sensor_helper(
        store.data_dir,
        SENSOR_SETUP_SCRIPT,
        allow_prompt=not (args.silent or args.no_tray or args.no_browser),
    )
    log.info("sensor helper: %s", sensor_state)

    app = create_app(store, port=args.port)
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=args.port, log_level="warning", log_config=None)
    )
    thread = threading.Thread(target=server.run, name="agent-http", daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)

    if not server.started:
        server.should_exit = True
        thread.join(timeout=3)
        report_port_conflict(args.port, silent=args.silent)
        return

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
