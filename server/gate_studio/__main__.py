"""Start the local agent: ``python -m gate_studio``."""

from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn

from .api import create_app
from .config import ConfigStore
from .device import discover_cloud
from .device.errors import DeviceError


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
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-discovery", action="store_true", help="skip the startup LAN discovery")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    store = ConfigStore(Path(args.data_dir) if args.data_dir else None)
    config = store.load()
    app = create_app(store)
    token = store.token()

    bind_lan = args.lan or config.settings.allow_lan
    host = args.host or ("0.0.0.0" if bind_lan else "127.0.0.1")
    url = f"http://localhost:{args.port}/?token={quote(token)}"

    print("Gate Theme Studio")
    print(f"  editor : {url}")
    print(f"  data   : {store.data_dir}")
    if bind_lan:
        address = lan_address() or "<this-pc-ip>"
        print(f"  phone  : http://{address}:{args.port}/?token={quote(token)}")
        print("  warning: the editor is reachable from your whole network while this runs.")
    if config.device.configured:
        print(f"  device : {config.device.host}:{config.device.port} ({config.device.protocol})")
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

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
