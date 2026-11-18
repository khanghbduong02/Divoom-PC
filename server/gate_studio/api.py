"""The local agent: REST for editing/pushing, WebSocket for live preview."""

from __future__ import annotations

import ast
import asyncio
import base64
import contextlib
import json
import logging
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Literal
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .auth import TokenAuthMiddleware
from .config import ConfigStore
from .desktop import autostart_enabled, autostart_supported, set_autostart
from .device import (
    DeviceError,
    DeviceErrorKind,
    DeviceTransport,
    ExternalSnapshot,
    ExternalWatchError,
    FrameIds,
    diff_snapshots,
    discover,
    discover_cloud,
    fetch_snapshot,
    probe_endpoint,
    probe_host,
    scan_subnet,
)
from .device.discovery import local_prefixes
from .library import SavedLibrary
from .models import AppConfig, AppSettings, Background, DeviceConfig, Panel, PausedPanel, Theme
from .native import NativePanel, build_items, save_background, setup_items
from .panel_exchange import (
    MAX_PANEL_FILE_BYTES,
    build_panel_export,
    export_filename,
    parse_panel_import,
)
from .presets import list_presets, load_preset
from .render import encode_jpeg, encode_png, render_all, render_all_frames
from .render.renderer import render_test_panel
from .sensors import SensorCollector
from .update import (
    UpdateError,
    check_for_update,
    download_update,
    launch_updater,
    schedule_app_exit,
)

log = logging.getLogger(__name__)

#: How many frame uploads to allow before clearing the device's frame-ID
#: cache. The Times Gate starts showing "Loading" again after roughly 100
#: frames in one PicID sequence, so reset with a safety margin below that.
#: Resetting every 32 frames (the old behavior) made the loading flash too often.
PIC_RESET_EVERY = 80

STATIC_DIR = Path(__file__).parent / "static"


def _resource_root() -> Path:
    """Project root in a source checkout, bundle root inside the one-file exe."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


#: Windows sensor helper bundled with the exe or kept in tools/ in a checkout
SENSOR_SETUP_SCRIPT = _resource_root() / "tools" / "setup-sensors.ps1"


class AppState:
    """Everything the routes share, kept off module globals so tests can isolate."""

    def __init__(
        self,
        store: ConfigStore,
        collector: SensorCollector | None = None,
        port: int = 8765,
    ) -> None:
        self.store = store
        self.port = port
        self.library = SavedLibrary(store.data_dir)
        self.config: AppConfig = store.load()
        #: what the panels currently show; edits only replace it on Apply/Send
        self.applied_theme: Theme = (self.config.applied_theme or self.config.theme).model_copy(
            deep=True
        )
        if self.config.applied_theme is None:
            # Remember the first design as applied, so later drafts stay drafts
            # even if the app restarts before the user presses Apply/Send all.
            self.config.applied_theme = self.applied_theme.model_copy(deep=True)
            self.save()
        self.collector = collector or SensorCollector()
        self.ids = FrameIds()
        self.frames_since_reset = 0
        self._transport: DeviceTransport | None = None
        self._transport_key: tuple | None = None
        # Re-entrant: native setup may be entered from the push loop, which
        # already holds this lock, while /api/send enters it directly.
        self.frame_lock = RLock()
        self.last_replies: list[dict[str, object]] = []
        self.last_error: dict[str, object] | None = None
        #: native item-list layouts currently installed on the device
        self.native_layouts: dict[int, NativePanel] = {}

        # screens another app changed; persisted so a restart cannot overwrite them
        self._pause_lock = Lock()
        self.paused_panels: dict[int, PausedPanel] = {
            panel.panel: panel for panel in self.config.paused_panels
        }
        #: the last Divoom-app layout we saw (not what our own pushes drew)
        self.external_snapshot: ExternalSnapshot | None = None
        self.external_status: dict[str, object] = {
            "ok": False,
            "last_checked": None,
            "message": None,
        }

        # always-on pushing
        self.last_frames: dict[int, bytes] = {}
        self.last_push_at: float | None = None
        self.skipped_frames = 0
        self._push_thread: Thread | None = None
        self._stop_push = Event()
        self._next_push = 0.0
        self.device_online = False
        self._last_rediscovery = 0.0

        # Divoom-cloud watcher; separate from the push loop so a slow cloud
        # request can never hold up sensor updates.
        self._watch_thread: Thread | None = None
        self._stop_watch = Event()
        self._watch_stopping = False
        self._watch_next = 0.0
        self._watch_ready = Event()
        self._watch_restarts = 0
        self._takeover_version = 0
        self._skip_external_once = False

    def start_pusher(self) -> None:
        if self._push_thread and self._push_thread.is_alive():
            return
        self._stop_push.clear()
        self._push_thread = Thread(
            target=_push_loop, args=(self,), name="auto-push", daemon=True
        )
        self._push_thread.start()

    def stop_pusher(self) -> None:
        self._stop_push.set()
        if self._push_thread:
            self._push_thread.join(timeout=2.0)
            self._push_thread = None

    def start_watcher(self) -> None:
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._watch_stopping = False
        self._stop_watch.clear()
        self._watch_thread = Thread(
            target=_watch_loop, args=(self,), name="external-watch", daemon=True
        )
        self._watch_thread.start()
        log.info("external watch started")

    def ensure_watcher(self) -> None:
        """Restart the Divoom-app watcher if it died unexpectedly."""
        if self._stop_push.is_set() or self._watch_stopping:
            return
        settings = self.config.settings
        if not settings.external_watch or not self.config.device.configured:
            return
        thread = self._watch_thread
        if thread is not None and thread.is_alive():
            return
        log.warning("external watch stopped; restarting it")
        self._watch_restarts += 1
        try:
            self.start_watcher()
        except Exception:  # noqa: BLE001 - never let a watcher restart stop pushes
            log.exception("could not restart external watch")

    def stop_watcher(self) -> None:
        self._watch_stopping = True
        self._stop_watch.set()
        if self._watch_thread:
            self._watch_thread.join(timeout=2.0)
            self._watch_thread = None

    # -- config --------------------------------------------------------
    def save(self) -> None:
        self.store.save(self.config)

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.close_transport()
        # A different device has not seen these frames, and even the same device
        # may have forgotten them while the config was being changed.
        self.last_frames.clear()
        self.native_layouts.clear()
        self.external_snapshot = None
        self._watch_next = 0.0

    def close_transport(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._transport_key = None

    def transport(self) -> DeviceTransport:
        device = self.config.device
        if not device.configured:
            raise DeviceError(
                DeviceErrorKind.NOT_CONFIGURED,
                "No device is configured yet.",
                hint="Run the connection wizard and enter the Times Gate IP address.",
            )
        key = (device.host, device.port, device.protocol, device.local_token)
        if self._transport is None or self._transport_key != key:
            self.close_transport()
            self._transport = DeviceTransport(
                device.host or "",
                device.port,
                device.local_token,
                device.protocol,
            )
            self._transport_key = key
        return self._transport

    def note_device_offline(self) -> None:
        """Forget device-held state so the next connection rebuilds it.

        A Times Gate does not keep local custom item lists across every reboot.
        Keeping ``native_layouts`` around would make the next successful call
        send only text updates to a panel whose background is gone.
        """
        self.device_online = False
        self.native_layouts.clear()
        self.last_frames.clear()

    def maybe_rediscover(self) -> bool:
        """Follow a Gate whose DHCP address changed after a reboot.

        The saved IP is only a hint. Divoom's LAN discovery returns the
        current address; match it by the stable device id and probe both
        hardware revisions before updating the config.
        """
        device = self.config.device
        if not device.configured or device.device_id is None:
            return False
        now = time.monotonic()
        if now - self._last_rediscovery < 30.0:
            return False
        self._last_rediscovery = now
        try:
            found = discover_cloud(timeout=4.0)
        except DeviceError:
            return False
        candidates = [
            item
            for item in found
            if str(item.get("device_id")) == str(device.device_id)
            and item.get("ip")
        ]
        if not candidates:
            # Divoom's cloud discovery is often empty even when the Gate is on
            # the LAN.  Fall back to the same subnet scan the wizard uses and
            # match the stable DeviceId from the reply.
            for prefix in local_prefixes()[:2]:
                for outcome in scan_subnet(prefix, device.local_token, timeout=0.8):
                    if not outcome.ok or not outcome.raw:
                        continue
                    try:
                        raw = ast.literal_eval(outcome.raw)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(raw, dict) and str(raw.get("DeviceId")) == str(device.device_id):
                        candidates = [{"ip": outcome.host, "protocol": outcome.protocol}]
                        break
                if candidates:
                    break
        for candidate in candidates:
            host = str(candidate["ip"])
            known_protocol = candidate.get("protocol")
            preferred = (
                known_protocol
                if known_protocol in ("hw400", "hw402")
                else device.protocol
            )
            protocols = (preferred, "hw400" if preferred == "hw402" else "hw402")
            for protocol in dict.fromkeys(protocols):
                outcome = probe_endpoint(host, protocol, device.local_token, timeout=6.0)
                if not outcome.ok:
                    continue
                if host != device.host or outcome.protocol != device.protocol:
                    log.info(
                        "device moved to %s:%s (%s); updating saved connection",
                        host,
                        outcome.port,
                        outcome.protocol,
                    )
                    device.host = host
                    device.port = outcome.port
                    device.protocol = outcome.protocol
                    self.close_transport()
                    self.external_snapshot = None
                    self._watch_next = 0.0
                    self.save()
                self.device_online = True
                return True
        return False

    def device_summary(self) -> dict[str, object]:
        device = self.config.device
        return {
            "configured": device.configured,
            "host": device.host,
            "port": device.port,
            "protocol": device.protocol,
            "local_token_set": device.local_token is not None,
            "name": device.name,
            "device_id": device.device_id,
        }

    # -- external apps / paused screens --------------------------------
    def paused_snapshot(self) -> list[dict[str, object]]:
        with self._pause_lock:
            return [
                panel.model_dump(mode="json")
                for panel in self.paused_panels.values()
            ]

    def paused_indices(self) -> set[int]:
        with self._pause_lock:
            return set(self.paused_panels)

    def _save_pauses_locked(self) -> None:
        self.config.paused_panels = [
            self.paused_panels[index] for index in sorted(self.paused_panels)
        ]
        self.save()

    def pause_panels(
        self,
        panels: list[int],
        source: Literal["external", "manual"] = "manual",
        reason: str = "",
    ) -> list[dict[str, object]]:
        """Stop sending these screens until the user resumes them."""
        indices = [int(panel) for panel in dict.fromkeys(panels) if 0 <= int(panel) <= 4]
        if not indices:
            return self.paused_snapshot()
        with self.frame_lock:
            with self._pause_lock:
                for index in indices:
                    self.paused_panels[index] = PausedPanel(
                        panel=index, source=source, reason=reason
                    )
                    # force a fresh frame when the screen is resumed
                    self.last_frames.pop(index, None)
                self._save_pauses_locked()
        return self.paused_snapshot()

    def resume_panels(self, panels: list[int]) -> list[dict[str, object]]:
        indices = {int(panel) for panel in panels if 0 <= int(panel) <= 4}
        if not indices:
            return self.paused_snapshot()
        with self.frame_lock:
            with self._pause_lock:
                # An explicit resume/Apply owns these screens now.  A cloud
                # read that started before this moment must not pause them
                # again when it returns, and the next read becomes the new
                # baseline instead of reviving the old pause.
                self._takeover_version += 1
                self._skip_external_once = True
                changed = False
                for index in indices:
                    if self.paused_panels.pop(index, None) is not None:
                        self.last_frames.pop(index, None)
                        changed = True
                if changed:
                    self._save_pauses_locked()
        return self.paused_snapshot()

    def resume_external_pauses(self) -> list[int]:
        """Take back screens the Divoom app changed while our app was away.

        Manual pauses are deliberate and stay.  External pauses are cleared
        when restoring after an app/device restart.
        """
        with self._pause_lock:
            indices = [
                index
                for index, panel in self.paused_panels.items()
                if panel.source == "external"
            ]
        if indices:
            self.resume_panels(indices)
            log.info("restored %d screen(s) after restart", len(indices))
        return indices

    def clear_pauses(self) -> None:
        self.resume_panels(list(range(5)))

    def external_watch_state(self) -> dict[str, object]:
        return {
            "enabled": bool(self.config.settings.external_watch),
            "ok": bool(self.external_status.get("ok")),
            "last_checked": self.external_status.get("last_checked"),
            "message": self.external_status.get("message"),
        }

    def takeover_version(self) -> int:
        with self._pause_lock:
            return self._takeover_version

    def apply_external_snapshot(
        self, snapshot: ExternalSnapshot, takeover_version: int | None = None
    ) -> list[int]:
        """Pause screens the Divoom app changed since the previous cloud read."""
        changed = diff_snapshots(self.external_snapshot, snapshot)
        self.external_snapshot = snapshot
        if takeover_version is not None and takeover_version != self.takeover_version():
            # The user pressed Apply/Resume while this read was in flight.
            return []
        with self._pause_lock:
            if self._skip_external_once:
                # Apply/Resume wins; make this layout the new baseline.
                self._skip_external_once = False
                return []
        if changed:
            reason = (
                "The Divoom app changed the display layout. Updates are paused so it is not overwritten."
                if len(changed) == 5
                else "The Divoom app changed this screen. Updates are paused so it is not overwritten."
            )
            self.pause_panels(changed, source="external", reason=reason)
        return changed

    def ensure_device_id(self) -> int | None:
        """Fetch the Divoom device id once, using a separate short connection."""
        device = self.config.device
        if device.device_id is not None:
            return device.device_id
        if not device.configured:
            return None
        transport = DeviceTransport(
            device.host or "",
            device.port,
            device.local_token,
            device.protocol,
        )
        try:
            reply = transport.get_all_conf()
        finally:
            transport.close()
        raw = reply.get("DeviceId") or reply.get("device_id")
        try:
            device_id = int(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            device_id = None
        if device_id is not None:
            device.device_id = device_id
            self.save()
        return device_id


# -- request bodies ----------------------------------------------------
class ProbeRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    local_token: int | None = None


class ConnectRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = 80
    protocol: str = "hw400"
    local_token: int | None = None


class SendRequest(BaseModel):
    panels: list[int] | None = None
    #: the editor's current draft, so a click on Apply is not raced by the
    #: editor's debounced autosave
    theme: Theme | None = None


class TestFrameRequest(BaseModel):
    panel: int = 0


class ApplyPresetRequest(BaseModel):
    #: when set, only this panel is replaced instead of the whole theme
    panel: int | None = None


class SettingsPatch(BaseModel):
    refresh_interval: float | None = None
    push_interval: float | None = None
    allow_lan: bool | None = None
    auto_push: bool | None = None
    native_stats: bool | None = None
    restore_on_start: bool | None = None
    external_watch: bool | None = None
    external_check_interval: float | None = Field(default=None, ge=2, le=60)
    autostart: bool | None = None
    temperature_unit: Literal["c", "f"] | None = None


class PanelPauseRequest(BaseModel):
    paused: bool = True
    source: Literal["external", "manual"] = "manual"
    reason: str = Field(default="", max_length=300)


class SaveThemeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SavePanelRequest(BaseModel):
    panel: int = Field(ge=0, le=4)
    name: str = Field(min_length=1, max_length=80)


class ApplySavedPanelRequest(BaseModel):
    panel: int = Field(ge=0, le=4)


class AutostartRequest(BaseModel):
    enabled: bool


# -- helpers -----------------------------------------------------------
def _error_response(exc: DeviceError, status: int = 502) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": exc.as_dict()})


def _is_empty_panel(panel: Panel) -> bool:
    """A panel nobody has given layers or a background to yet.

    Its accent does not draw anything on its own, so changing only the accent
    still leaves the screen empty. A custom background is visible and counts
    as content, even when there are no layers on top of it.
    """
    return not panel.layers and panel.background == Background()


def _edited_panels(theme: Theme) -> list[int]:
    return [index for index, panel in enumerate(theme.panels) if not _is_empty_panel(panel)]


def _render_theme(state: AppState, theme: Theme, *, static_only: bool = False) -> list:
    """Render every panel, giving line layers only the history they ask for."""
    windows: dict[str, int] = {}
    for panel in theme.panels:
        for layer in panel.layers:
            if layer.kind == "metric" and layer.visible and layer.widget == "line":
                windows[layer.metric] = max(windows.get(layer.metric, 0), layer.history_minutes)
    history: dict[str, list[tuple[float, float | None]]] = {}
    if windows:
        full = state.collector.history_window(max(windows.values()) * 60)
        history = {metric: full[metric] for metric in windows if metric in full}
    return render_all(
        theme,
        state.collector.snapshot(),
        state.store.media_dir,
        history=history,
        temperature_unit=state.config.settings.temperature_unit,
        static_only=static_only,
    )


def _render_theme_frames(
    state: AppState, theme: Theme, *, static_only: bool = False
) -> list[list[tuple]]:
    """Render every panel without collapsing animated GIF backgrounds."""
    windows: dict[str, int] = {}
    for panel in theme.panels:
        for layer in panel.layers:
            if layer.kind == "metric" and layer.visible and layer.widget == "line":
                windows[layer.metric] = max(windows.get(layer.metric, 0), layer.history_minutes)
    history: dict[str, list[tuple[float, float | None]]] = {}
    if windows:
        full = state.collector.history_window(max(windows.values()) * 60)
        history = {metric: full[metric] for metric in windows if metric in full}
    return render_all_frames(
        theme,
        state.collector.snapshot(),
        state.store.media_dir,
        history=history,
        temperature_unit=state.config.settings.temperature_unit,
        static_only=static_only,
        max_frames=40,
    )


def _lan_ip() -> str | None:
    """Best-effort LAN address the Times Gate can use to fetch a background."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def _background_url(state: AppState, name: str) -> str | None:
    host = _lan_ip()
    if host is None:
        return None
    return (
        f"http://{host}:{state.port}/media/{name}"
        f"?token={quote(state.store.token())}"
    )


def _active_native_panels(state: AppState, theme: Theme, requested: list[int] | None = None) -> list[int]:
    paused = state.paused_indices()
    candidates = requested if requested is not None else _edited_panels(theme)
    return [
        index
        for index in candidates
        if 0 <= index < len(theme.panels)
        and index not in paused
        and not _is_empty_panel(theme.panels[index])
        and bool(build_items(theme.panels[index], {}, datetime.now()))
    ]


def _setup_native(state: AppState, theme: Theme, panels: list[int]) -> bool:
    """Install a stable background and native text for ``panels``.

    The device fetches the static artwork once via ``BackgroudGif`` and then
    only ``SendHttpItemList`` items change, avoiding repeated JPEG uploads.
    """
    if not state.config.settings.native_stats:
        return False
    if not state.config.settings.allow_lan:
        # Callers already fall back to JPEG updates when LAN access is off.
        # Do not leave a red "device error" behind for a supported fallback.
        return False
    targets = _active_native_panels(state, theme, panels)
    if not targets:
        return False
    values = state.collector.snapshot()
    now = datetime.now()
    rendered = _render_theme_frames(state, theme, static_only=True)
    transport = state.transport()
    layouts: dict[int, NativePanel] = {}
    with state.frame_lock:
        try:
            for index in targets:
                frames = rendered[index]
                name = save_background(
                    state.store,
                    theme.id,
                    index,
                    [image for image, _delay in frames],
                    [delay for _image, delay in frames],
                )
                url = _background_url(state, name)
                if url is None:
                    raise DeviceError(
                        DeviceErrorKind.NETWORK,
                        "Could not determine this PC's LAN address for the native background.",
                    )
                items = setup_items(
                    theme.panels[index],
                    values,
                    now,
                    state.config.settings.temperature_unit,
                )
                transport.send_item_list(
                    index,
                    items,
                    background_gif=url,
                    new_flag=True,
                )
                layouts[index] = NativePanel(panel=index, background_name=name)
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            state.native_layouts.clear()
            return False
        state.native_layouts = layouts
        state.last_push_at = time.time()
        state.last_error = None
        state.last_replies = [
            {
                "panel": index,
                "ok": True,
                "native": True,
                "background": layout.background_name,
            }
            for index, layout in layouts.items()
        ]
        return bool(layouts)


def _update_native(state: AppState) -> bool:
    """Send the current values as native text items without redrawing panels."""
    if not state.native_layouts:
        return False
    values = state.collector.snapshot()
    now = datetime.now()
    transport = state.transport()
    paused = state.paused_indices()
    try:
        for index in list(state.native_layouts):
            if index in paused:
                continue
            items = build_items(
                state.applied_theme.panels[index],
                values,
                now,
                state.config.settings.temperature_unit,
            )
            transport.send_item_list(index, items)
    except DeviceError as exc:
        state.last_error = exc.as_dict()
        # Keep the layout: the static artwork is already installed.  Retrying
        # the text update is cheap and does not flash the panel; re-uploading
        # the artwork every few seconds is what we are trying to avoid.
        return False
    state.last_error = None
    state.last_push_at = time.time()
    state.last_replies = [
        {"panel": index, "ok": True, "native": True}
        for index in state.native_layouts
    ]
    return True


def _reset_pic_ids(state: AppState, transport: DeviceTransport) -> None:
    transport.reset_pic_id()
    state.ids.reset()
    state.frames_since_reset = 0
    log.info("Reset device PicID after %d frames", PIC_RESET_EVERY)


def _reset_pic_ids_on_start(state: AppState) -> None:
    """Clear the device frame IDs without delaying the local HTTP server.

    A saved device can be asleep or slow.  Waiting for it here used to block
    uvicorn's lifespan startup for up to 12 seconds, which made the main
    process time out and report a port conflict even though no server had
    bound the port yet.  The reset is still serialized with frame sends, but
    it no longer prevents the editor from opening.
    """
    try:
        with state.frame_lock:
            transport = state.transport()
            transport.reset_pic_id()
            state.ids.reset()
            state.frames_since_reset = 0
    except DeviceError as exc:
        state.last_error = exc.as_dict()


def _push(state: AppState, panels: list[int] | None, images: list) -> list[dict[str, object]]:
    with state.frame_lock:
        transport = state.transport()
        targets = range(len(images)) if panels is None else panels
        frames = [
            (index, encode_jpeg(images[index]))
            for index in targets
            if 0 <= index < len(images)
        ]
        results: list[dict[str, object]] = []

        batch_sender = getattr(transport, "send_frames", None)
        if len(frames) > 1 and batch_sender is not None:
            # Updating five panels as five separate requests makes the device
            # show its loading state on one screen after another. A command
            # list applies the same batch in one request.
            if state.frames_since_reset + len(frames) > PIC_RESET_EVERY:
                _reset_pic_ids(state, transport)
            batch = [
                (payload, [index], state.ids.next()) for index, payload in frames
            ]
            try:
                reply = batch_sender(batch)
            except DeviceError as exc:
                if exc.kind is not DeviceErrorKind.DEVICE:
                    raise
                # Older firmware may reject Draw/CommandList.  Keep updating
                # the panels rather than leaving the display behind.
                log.warning("Draw/CommandList rejected; using single-panel sends")
                for index, payload in frames:
                    result = _send_panel(state, transport, payload, index)
                    state.last_frames[index] = payload
                    results.append(result)
            else:
                state.frames_since_reset += len(batch)
                for (index, payload), (_, _, pic_id) in zip(frames, batch):
                    state.last_frames[index] = payload
                    results.append(
                        {
                            "panel": index,
                            "ok": True,
                            "pic_id": pic_id,
                            "bytes": len(payload),
                            "reply": reply,
                        }
                    )
        else:
            for index, payload in frames:
                result = _send_panel(state, transport, payload, index)
                state.last_frames[index] = payload
                results.append(result)
        state.last_replies = results
        state.last_push_at = time.time()
        return results


def _send_panel(
    state: AppState,
    transport: DeviceTransport,
    payload: bytes,
    panel: int,
) -> dict[str, object]:
    """Upload one panel frame, resetting the PicID sequence when due.

    Caller must hold ``state.frame_lock``. The reset happens between frames so
    the next ID is valid for the device's fresh counter.
    """
    if state.frames_since_reset >= PIC_RESET_EVERY:
        _reset_pic_ids(state, transport)
    pic_id = state.ids.next()
    reply = transport.send_frame(payload, [panel], pic_id)
    state.frames_since_reset += 1
    return {
        "panel": panel,
        "ok": True,
        "pic_id": pic_id,
        "bytes": len(payload),
        "reply": reply,
    }


def _apply_draft(state: AppState, panels: list[int] | None) -> None:
    """Copy the editor draft into the design the display is allowed to show."""
    if panels is None:
        state.applied_theme = state.config.theme.model_copy(deep=True)
        state.last_frames.clear()
    else:
        applied = state.applied_theme.model_copy(deep=True)
        for index in panels:
            applied.panels[index] = state.config.theme.panels[index].model_copy(deep=True)
            state.last_frames.pop(index, None)
        state.applied_theme = applied
    state.config.applied_theme = state.applied_theme.model_copy(deep=True)
    state.save()


def _push_loop(state: AppState) -> None:
    """Keep the applied design live: re-render and send on an interval, skipping
    frames whose bytes did not change so an idle panel is not rewritten. Draft
    edits never reach this loop until Apply/Send copies them into applied_theme."""
    while not state._stop_push.wait(0.3):
        settings = state.config.settings
        if not settings.auto_push or not state.config.device.configured:
            continue
        if settings.restore_on_start and not state.device_online:
            # The Gate boots into its last Divoom face. Take the screens back
            # once it is reachable again, including after a DHCP change.
            state.resume_external_pauses()
        state.ensure_watcher()
        now = time.monotonic()
        if now < state._next_push:
            continue
        state._next_push = now + settings.push_interval
        try:
            with state.frame_lock:
                transport = state.transport()
                if settings.native_stats and settings.allow_lan:
                    if not state.native_layouts:
                        if _setup_native(
                            state,
                            state.applied_theme,
                            _edited_panels(state.applied_theme),
                        ):
                            state.device_online = True
                            state.last_push_at = time.time()
                            continue
                        if state.last_error is not None:
                            state.note_device_offline()
                            state.maybe_rediscover()
                    if state.native_layouts:
                        if _update_native(state):
                            state.device_online = True
                        else:
                            state.note_device_offline()
                            state.maybe_rediscover()
                    # Do not fall back to a JPEG upload here: that is what
                    # causes the device-wide loading flash.  If native setup
                    # failed, the last stable screen stays untouched.
                    state.last_push_at = time.time()
                    continue
                images = _render_theme(state, state.applied_theme)
                paused = state.paused_indices()
                empty = {
                    index
                    for index, panel in enumerate(state.applied_theme.panels)
                    if _is_empty_panel(panel)
                }
                for index, image in enumerate(images):
                    if index in paused or index in empty:
                        continue
                    payload = encode_jpeg(image)
                    if state.last_frames.get(index) == payload:
                        state.skipped_frames += 1
                        continue
                    result = _send_panel(state, transport, payload, index)
                    state.last_frames[index] = payload
                    state.last_replies = [result]
                state.device_online = True
                state.last_push_at = time.time()
                state.last_error = None
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            state.note_device_offline()
            state.maybe_rediscover()
            state._next_push = time.monotonic() + max(3.0, settings.push_interval)
        except Exception as exc:  # noqa: BLE001 - the loop must survive anything
            state.last_error = {
                "kind": "device",
                "message": f"Update failed: {exc}",
                "raw": None,
                "hint": None,
            }
            state.note_device_offline()


def _watch_loop(state: AppState) -> None:
    """Notice when the Divoom app changes a screen and hand that screen over."""
    try:
        while not state._stop_watch.wait(0.5):
            settings = state.config.settings
            if not settings.external_watch or not state.config.device.configured:
                continue
            now = time.monotonic()
            if now < state._watch_next:
                continue
            state._watch_next = now + settings.external_check_interval
            try:
                device_id = state.ensure_device_id()
                if device_id is None:
                    raise ExternalWatchError("The display's Divoom device id is not known yet.")
                takeover = state.takeover_version()
                snapshot = fetch_snapshot(device_id)
                state.apply_external_snapshot(snapshot, takeover_version=takeover)
                state.external_status = {
                    "ok": True,
                    "last_checked": time.time(),
                    "message": None,
                }
            except (ExternalWatchError, DeviceError) as exc:
                state.external_status = {
                    "ok": False,
                    "last_checked": time.time(),
                    "message": exc.message,
                }
            except Exception as exc:  # noqa: BLE001 - the watcher must survive anything
                state.external_status = {
                    "ok": False,
                    "last_checked": time.time(),
                    "message": f"Divoom app watch failed: {exc}",
                }
            finally:
                # The pusher waits for this before its first frame, so startup
                # does not overwrite settings the Divoom app changed.
                state._watch_ready.set()
    except BaseException:
        log.exception("external watch stopped unexpectedly; the pusher will restart it")
        raise


def _theme_with_media(theme: Theme, store: ConfigStore) -> Theme:
    for panel in theme.panels:
        image = panel.background.image
        if image and not store.media_path(image).exists():
            panel.background.image = None
            panel.background.kind = "color"
    return theme


def create_app(
    store: ConfigStore | None = None,
    static_dir: Path | None = None,
    port: int = 8765,
) -> FastAPI:
    store = store or ConfigStore()
    state = AppState(store, port=port)
    static_root = Path(static_dir) if static_dir else STATIC_DIR

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.collector.start()
        # The device and the PC usually restart together. Screens the Divoom
        # app owned while the PC was off must not keep blocking our design.
        # Manual pauses are left alone.
        if state.config.settings.restore_on_start:
            state.resume_external_pauses()
        state.native_layouts.clear()
        if state.config.device.configured:
            # PicIDs must start clean once per process or panels stay on
            # "loading", but a slow/asleep device must not hold up startup.
            Thread(
                target=_reset_pic_ids_on_start,
                args=(state,),
                name="device-reset",
                daemon=True,
            ).start()
        state.start_watcher()
        if state.config.settings.external_watch and state.config.device.configured:
            # Establish the Divoom-app baseline before the first automatic frame.
            # A timeout keeps a cloud outage from blocking the local display.
            state._watch_ready.wait(timeout=2.5)
        state.start_pusher()
        try:
            yield
        finally:
            state.stop_watcher()
            state.stop_pusher()
            state.collector.stop()
            state.close_transport()

    app = FastAPI(title="Gate Theme Studio", version=__version__, lifespan=lifespan)
    app.state.gate = state
    app.add_middleware(TokenAuthMiddleware, token=store.token())

    # -- basics --------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "version": __version__,
            "device": state.device_summary(),
            "sensors_ok": state.collector.psutil_ok,
        }

    @app.get("/api/config")
    def get_config() -> dict[str, object]:
        return {
            "device": state.device_summary(),
            "settings": state.config.settings.model_dump(),
            "media_dir": str(store.media_dir),
            "data_dir": str(store.data_dir),
        }

    @app.put("/api/config/settings")
    def put_settings(patch: SettingsPatch) -> dict[str, object]:
        settings = state.config.settings
        if patch.refresh_interval is not None:
            settings.refresh_interval = patch.refresh_interval
        if patch.push_interval is not None:
            settings.push_interval = patch.push_interval
        if patch.auto_push is not None:
            settings.auto_push = patch.auto_push
        if patch.native_stats is not None:
            settings.native_stats = patch.native_stats
            state.native_layouts.clear()
            state.last_error = None
        if patch.restore_on_start is not None:
            settings.restore_on_start = patch.restore_on_start
            state.native_layouts.clear()
            if patch.restore_on_start:
                state.resume_external_pauses()
        if patch.external_watch is not None:
            if settings.external_watch != patch.external_watch:
                state.external_snapshot = None
                state._watch_next = 0.0
            settings.external_watch = patch.external_watch
        if patch.external_check_interval is not None:
            settings.external_check_interval = patch.external_check_interval
            state._watch_next = 0.0
        restart_required = False
        if patch.allow_lan is not None and patch.allow_lan != settings.allow_lan:
            settings.allow_lan = patch.allow_lan
            state.native_layouts.clear()
            state.last_error = None
            restart_required = True
        if patch.temperature_unit is not None:
            settings.temperature_unit = patch.temperature_unit
        if patch.autostart is not None and patch.autostart != settings.autostart:
            settings.autostart = patch.autostart
            set_autostart(patch.autostart)
        state.save()
        return {
            "settings": AppSettings.model_validate(settings.model_dump()).model_dump(),
            "restart_required": restart_required,
            "autostart": autostart_enabled(),
        }

    @app.get("/api/system")
    def system() -> dict[str, object]:
        return {
            "version": __version__,
            "autostart": autostart_enabled(),
            "autostart_supported": autostart_supported(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "data_dir": str(store.data_dir),
            "auto_push": state.config.settings.auto_push,
            "push_interval": state.config.settings.push_interval,
            "last_push_at": state.last_push_at,
            "skipped_frames": state.skipped_frames,
            "paused_panels": state.paused_snapshot(),
            "external_watch": state.external_watch_state(),
        }

    @app.post("/api/system/sensors/install")
    def install_sensor_helper() -> dict[str, object]:
        """Ask Windows (with a normal UAC prompt) to install the CPU sensor helper."""
        if sys.platform != "win32":
            raise HTTPException(status_code=400, detail="CPU temperature sensors are Windows-only.")
        if not SENSOR_SETUP_SCRIPT.exists():
            raise HTTPException(
                status_code=404,
                detail="The sensor helper is not available in this build — see README → Metrics.",
            )
        command = (
            "Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList "
            f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{SENSOR_SETUP_SCRIPT}'"
        )
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"started": True}

    @app.post("/api/system/autostart")
    def set_autostart_state(body: AutostartRequest) -> dict[str, object]:
        state.config.settings.autostart = body.enabled
        state.save()
        return {
            "autostart": set_autostart(body.enabled),
            "supported": autostart_supported(),
        }

    # -- updates -------------------------------------------------------
    @app.get("/api/update/check")
    def update_check() -> dict[str, object]:
        try:
            return check_for_update().as_dict()
        except UpdateError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/update/install")
    def update_install() -> dict[str, object]:
        try:
            info = check_for_update()
        except UpdateError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not info.available:
            raise HTTPException(status_code=409, detail="Gate Theme Studio is already up to date.")
        if not info.can_install:
            raise HTTPException(
                status_code=409,
                detail="Updates can only be installed from the packaged Windows app.",
            )
        try:
            new_exe = download_update(info, store.data_dir / "updates")
        except UpdateError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        try:
            launch_updater(new_exe, data_dir=store.data_dir / "updates")
        except UpdateError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        schedule_app_exit()
        return {"started": True, "version": info.latest_version}

    # -- device --------------------------------------------------------
    @app.post("/api/device/probe")
    def probe(body: ProbeRequest) -> dict[str, object]:
        outcomes = probe_host(body.host.strip(), body.local_token)
        return {"outcomes": [outcome.as_dict() for outcome in outcomes]}

    @app.post("/api/device/discover")
    def discovery(body: dict | None = None) -> dict[str, object]:
        host = (body or {}).get("host") if isinstance(body, dict) else None
        token = (body or {}).get("local_token") if isinstance(body, dict) else None
        return discover(host=host, local_token=token)

    @app.post("/api/device/connect")
    def connect(body: ConnectRequest) -> dict[str, object]:
        host = body.host.strip()
        if body.protocol not in ("hw400", "hw402"):
            raise HTTPException(status_code=422, detail="protocol must be hw400 or hw402")
        transport = DeviceTransport(host, body.port, body.local_token, body.protocol)
        try:
            reply = transport.get_all_conf()
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            return _error_response(exc)
        finally:
            transport.close()

        name = None
        for key in ("DeviceName", "ShortName", "Name"):
            if isinstance(reply.get(key), str):
                name = str(reply[key])
                break
        raw_id = reply.get("DeviceId") or reply.get("device_id")
        try:
            device_id = int(raw_id) if raw_id not in (None, "") else None
        except (TypeError, ValueError):
            device_id = None
        state.apply_config(
            state.config.model_copy(
                update={
                    "device": DeviceConfig(
                        host=host,
                        port=body.port,
                        protocol=body.protocol,  # type: ignore[arg-type]
                        local_token=body.local_token,
                        name=name,
                        device_id=device_id,
                    )
                }
            )
        )
        state.clear_pauses()
        state.external_status = {"ok": False, "last_checked": None, "message": None}
        state.save()
        state.last_error = None
        return {"device": state.device_summary(), "reply": reply}

    @app.delete("/api/device")
    def forget_device() -> dict[str, object]:
        state.apply_config(state.config.model_copy(update={"device": DeviceConfig()}))
        state.clear_pauses()
        state.external_status = {"ok": False, "last_checked": None, "message": None}
        state.save()
        return {"device": state.device_summary()}

    @app.post("/api/device/test-frame")
    def test_frame(body: TestFrameRequest) -> dict[str, object]:
        """M1 proof: one coloured, numbered tile on a chosen panel."""
        if not 0 <= body.panel <= 4:
            raise HTTPException(status_code=422, detail="panel must be 0..4")
        images = [render_test_panel(i) if i == body.panel else None for i in range(5)]
        state.resume_panels([body.panel])
        try:
            results = _push(state, [body.panel], images)
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            return _error_response(exc)
        state.last_error = None
        return {"results": results}

    @app.post("/api/panels/{panel}/pause")
    def set_panel_pause(panel: int, body: PanelPauseRequest) -> dict[str, object]:
        """Signal from the editor or another local app to hand a screen over."""
        if not 0 <= panel <= 4:
            raise HTTPException(status_code=422, detail="panel must be 0..4")
        if body.paused:
            reason = body.reason or (
                "Another app changed this screen. Updates are paused so it is not overwritten."
                if body.source == "external"
                else "Updates for this screen are paused."
            )
            state.pause_panels([panel], source=body.source, reason=reason)
        else:
            state.resume_panels([panel])
        return {"paused_panels": state.paused_snapshot()}

    # -- theme ---------------------------------------------------------
    @app.get("/api/theme")
    def get_theme() -> dict[str, object]:
        return {"theme": state.config.theme.model_dump(mode="json")}

    @app.put("/api/theme")
    def put_theme(theme: Theme) -> dict[str, object]:
        state.config.theme = _theme_with_media(theme, store)
        state.save()
        return {"theme": state.config.theme.model_dump(mode="json")}

    @app.get("/api/presets")
    def presets() -> dict[str, object]:
        return {"presets": list_presets()}

    @app.post("/api/presets/{preset_id}/apply")
    def apply_preset(preset_id: str, body: ApplyPresetRequest | None = None) -> dict[str, object]:
        try:
            preset = load_preset(preset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if body is not None and body.panel is not None:
            if not 0 <= body.panel <= 4:
                raise HTTPException(status_code=422, detail="panel must be 0..4")
            panels = list(state.config.theme.panels)
            panels[body.panel] = preset.panels[body.panel]
            merged = state.config.theme.model_copy(
                update={"panels": panels, "id": uuid.uuid4().hex[:12]}
            )
            state.config.theme = _theme_with_media(merged, store)
        else:
            state.config.theme = _theme_with_media(preset, store)
        state.save()
        return {"theme": state.config.theme.model_dump(mode="json")}

    # -- saved library --------------------------------------------------
    @app.get("/api/library")
    def get_library() -> dict[str, object]:
        return state.library.list()

    @app.post("/api/library/themes")
    def save_library_theme(body: SaveThemeRequest) -> dict[str, object]:
        try:
            item = state.library.save_theme(body.name, state.config.theme)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"item": item, "library": state.library.list()}

    @app.post("/api/library/panels")
    def save_library_panel(body: SavePanelRequest) -> dict[str, object]:
        panel = state.config.theme.panels[body.panel]
        try:
            item = state.library.save_panel(body.name, panel)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"item": item, "library": state.library.list()}

    @app.get("/api/library/panels/{saved_id}/export")
    def export_saved_panel(saved_id: str) -> Response:
        try:
            saved = state.library.get_panel(saved_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="saved panel not found") from exc
        try:
            payload = build_panel_export(saved, store.media_dir)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{export_filename(saved.name)}"'
            },
        )

    @app.post("/api/library/panels/import")
    async def import_saved_panel(file: UploadFile) -> dict[str, object]:
        data = await file.read(MAX_PANEL_FILE_BYTES + 1)
        if len(data) > MAX_PANEL_FILE_BYTES:
            raise HTTPException(status_code=413, detail="panel file must be 12 MB or smaller")
        try:
            imported = parse_panel_import(data, store)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        item = state.library.save_panel_unique(imported.name, imported.panel)
        return {"item": item, "library": state.library.list()}

    @app.post("/api/library/themes/{saved_id}/apply")
    def apply_saved_theme(saved_id: str) -> dict[str, object]:
        try:
            saved = state.library.get_theme(saved_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="saved theme not found") from exc
        theme = saved.theme.model_copy(deep=True)
        theme.id = uuid.uuid4().hex[:12]
        theme.name = saved.name
        state.config.theme = _theme_with_media(theme, store)
        state.save()
        return {"theme": state.config.theme.model_dump(mode="json")}

    @app.post("/api/library/panels/{saved_id}/apply")
    def apply_saved_panel(
        saved_id: str, body: ApplySavedPanelRequest
    ) -> dict[str, object]:
        try:
            saved = state.library.get_panel(saved_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="saved panel not found") from exc
        panels = list(state.config.theme.panels)
        panels[body.panel] = saved.panel.model_copy(deep=True)
        merged = state.config.theme.model_copy(
            update={"panels": panels, "id": uuid.uuid4().hex[:12]}
        )
        state.config.theme = _theme_with_media(merged, store)
        state.save()
        return {"theme": state.config.theme.model_dump(mode="json")}

    # -- media ---------------------------------------------------------
    @app.post("/api/media")
    async def upload_media(file: UploadFile) -> dict[str, object]:
        data = await file.read()
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="image must be 8 MB or smaller")
        try:
            name = store.save_media(file.filename or "upload.png", data)
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        return {"name": name, "url": f"/media/{name}"}

    @app.get("/media/{name}")
    def media(name: str) -> FileResponse:
        path = store.media_path(name)
        if not path.exists():
            raise HTTPException(status_code=404, detail="not found")
        if path.name.startswith("native-"):
            log.info("native background fetched: %s", path.name)
        return FileResponse(path)

    # -- sensors / push ------------------------------------------------
    @app.get("/api/sensors")
    def sensors() -> dict[str, object]:
        return {
            "values": state.collector.snapshot(),
            "history": state.collector.history(),
            "hardware": state.collector.hardware(),
        }

    @app.post("/api/send")
    def send(body: SendRequest | None = None) -> dict[str, object]:
        if body is not None and body.theme is not None:
            # The UI sends the live draft with Apply; this avoids racing its
            # debounced PUT /api/theme with the frame upload.
            state.config.theme = _theme_with_media(body.theme, store)
            state.save()
        requested = body.panels if body else None
        if requested is not None:
            if any(not 0 <= panel <= 4 for panel in requested):
                raise HTTPException(status_code=422, detail="panels must be 0..4")
            panels = requested
            skipped: list[int] = []
        else:
            panels = _edited_panels(state.config.theme)
            targets = set(panels)
            skipped = [index for index in range(5) if index not in targets]

        # Send all is a no-op when every panel is still empty. It must not
        # blank screens that the user has not designed yet.
        if not panels:
            return {"results": [], "skipped": skipped}

        _apply_draft(state, panels)
        # An explicit Apply or Send all is the user taking the screens back.
        state.resume_panels(panels)
        if (
            state.config.settings.native_stats
            and state.config.settings.allow_lan
            and _active_native_panels(state, state.applied_theme, panels)
        ):
            if _setup_native(state, state.applied_theme, panels):
                if state.last_error is not None:
                    return JSONResponse(
                        status_code=502,
                        content={"error": state.last_error},
                    )
                return {
                    "results": state.last_replies,
                    "skipped": skipped,
                    "native": True,
                }
            if state.last_error is not None:
                return JSONResponse(
                    status_code=502,
                    content={"error": state.last_error},
                )
        images = _render_theme(state, state.applied_theme)
        try:
            results = _push(state, panels, images)
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            return _error_response(exc)
        state.last_error = None
        return {"results": results, "skipped": skipped}

    @app.get("/api/diagnostics")
    def diagnostics() -> dict[str, object]:
        return {
            "device": state.device_summary(),
            "last_replies": state.last_replies,
            "last_error": state.last_error,
            "sensors": state.collector.snapshot(),
            "data_dir": str(store.data_dir),
            "auto_push": state.config.settings.auto_push,
            "last_push_at": state.last_push_at,
            "skipped_frames": state.skipped_frames,
            "pic_id": state.ids.current,
            "frames_since_reset": state.frames_since_reset,
            "pic_reset_every": PIC_RESET_EVERY,
            "paused_panels": state.paused_snapshot(),
            "external_watch": state.external_watch_state(),
            "watch_thread_alive": bool(
                state._watch_thread and state._watch_thread.is_alive()
            ),
            "watch_restarts": state._watch_restarts,
            "watch_ready": state._watch_ready.is_set(),
            "hardware": state.collector.hardware(),
            "temperature_unit": state.config.settings.temperature_unit,
        }

    # -- live preview --------------------------------------------------
    @app.websocket("/ws")
    async def preview(websocket: WebSocket) -> None:
        if websocket.query_params.get("token") != store.token():
            await websocket.close(code=4401)
            return
        await websocket.accept()
        draft: dict[str, Theme] = {}

        async def read_theme() -> None:
            try:
                while True:
                    message = await websocket.receive_json()
                    if isinstance(message, dict) and message.get("type") == "theme":
                        with contextlib.suppress(Exception):
                            draft["theme"] = Theme.model_validate(message.get("theme"))
            except (WebSocketDisconnect, RuntimeError):
                return

        reader = asyncio.create_task(read_theme())
        try:
            while True:
                theme = draft.get("theme") or state.config.theme
                values = state.collector.snapshot()
                images = _render_theme(state, theme)
                await websocket.send_json(
                    {
                        "type": "tick",
                        "sensors": values,
                        "panels": [
                            {"index": index, "png": base64.b64encode(encode_png(image)).decode()}
                            for index, image in enumerate(images)
                        ],
                        "device": state.device_summary(),
                        "paused": state.paused_snapshot(),
                        "external": state.external_watch_state(),
                    }
                )
                await asyncio.sleep(state.config.settings.refresh_interval)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    # -- static UI -----------------------------------------------------
    if static_root.exists():
        app.mount("/", StaticFiles(directory=static_root, html=True), name="ui")
    else:

        @app.get("/")
        def missing_ui() -> HTMLResponse:
            return HTMLResponse(
                "<h1>Gate Theme Studio agent is running</h1>"
                "<p>The editor bundle is not built yet. Run <code>npm install &amp;&amp; npm run build</code> "
                "in <code>ui/</code>, then reload.</p>",
                status_code=200,
            )

    return app


def app_factory() -> FastAPI:  # pragma: no cover - uvicorn entrypoint helper
    return create_app()
