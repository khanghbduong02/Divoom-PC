"""The local agent: REST for editing/pushing, WebSocket for live preview."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .auth import TokenAuthMiddleware
from .config import ConfigStore
from .device import DeviceError, DeviceErrorKind, DeviceTransport, FrameIds, discover, probe_host
from .models import AppConfig, AppSettings, DeviceConfig, Theme
from .presets import list_presets, load_preset
from .render import encode_jpeg, encode_png, render_all
from .render.renderer import render_test_panel
from .sensors import SensorCollector

STATIC_DIR = Path(__file__).parent / "static"


class AppState:
    """Everything the routes share, kept off module globals so tests can isolate."""

    def __init__(self, store: ConfigStore, collector: SensorCollector | None = None) -> None:
        self.store = store
        self.config: AppConfig = store.load()
        self.collector = collector or SensorCollector()
        self.ids = FrameIds()
        self._transport: DeviceTransport | None = None
        self._transport_key: tuple | None = None
        self.frame_lock = Lock()
        self.last_replies: list[dict[str, object]] = []
        self.last_error: dict[str, object] | None = None

    # -- config --------------------------------------------------------
    def save(self) -> None:
        self.store.save(self.config)

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.close_transport()

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

    def device_summary(self) -> dict[str, object]:
        device = self.config.device
        return {
            "configured": device.configured,
            "host": device.host,
            "port": device.port,
            "protocol": device.protocol,
            "local_token_set": device.local_token is not None,
            "name": device.name,
        }


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


class TestFrameRequest(BaseModel):
    panel: int = 0


class SettingsPatch(BaseModel):
    refresh_interval: float | None = None
    allow_lan: bool | None = None
    auto_push: bool | None = None


# -- helpers -----------------------------------------------------------
def _error_response(exc: DeviceError, status: int = 502) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": exc.as_dict()})


def _push(state: AppState, panels: list[int] | None, images: list) -> list[dict[str, object]]:
    with state.frame_lock:
        transport = state.transport()
        targets = range(len(images)) if panels is None else panels
        results: list[dict[str, object]] = []
        for index in targets:
            if not 0 <= index < len(images):
                continue
            payload = encode_jpeg(images[index])
            pic_id = state.ids.next()
            reply = transport.send_frame(payload, [index], pic_id)
            results.append(
                {
                    "panel": index,
                    "ok": True,
                    "pic_id": pic_id,
                    "bytes": len(payload),
                    "reply": reply,
                }
            )
        state.last_replies = results
        return results


def _theme_with_media(theme: Theme, store: ConfigStore) -> Theme:
    for panel in theme.panels:
        image = panel.background.image
        if image and not store.media_path(image).exists():
            panel.background.image = None
            panel.background.kind = "color"
    return theme


def create_app(store: ConfigStore | None = None, static_dir: Path | None = None) -> FastAPI:
    store = store or ConfigStore()
    state = AppState(store)
    static_root = Path(static_dir) if static_dir else STATIC_DIR

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.collector.start()
        if state.config.device.configured:
            # PicIDs must start clean once per process or panels stay on "loading".
            try:
                state.transport().reset_pic_id()
            except DeviceError as exc:
                state.last_error = exc.as_dict()
        try:
            yield
        finally:
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
        if patch.auto_push is not None:
            settings.auto_push = patch.auto_push
        restart_required = False
        if patch.allow_lan is not None and patch.allow_lan != settings.allow_lan:
            settings.allow_lan = patch.allow_lan
            restart_required = True
        state.save()
        return {
            "settings": AppSettings.model_validate(settings.model_dump()).model_dump(),
            "restart_required": restart_required,
        }

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
        state.apply_config(
            state.config.model_copy(
                update={
                    "device": DeviceConfig(
                        host=host,
                        port=body.port,
                        protocol=body.protocol,  # type: ignore[arg-type]
                        local_token=body.local_token,
                        name=name,
                    )
                }
            )
        )
        state.save()
        state.last_error = None
        return {"device": state.device_summary(), "reply": reply}

    @app.delete("/api/device")
    def forget_device() -> dict[str, object]:
        state.apply_config(state.config.model_copy(update={"device": DeviceConfig()}))
        state.save()
        return {"device": state.device_summary()}

    @app.post("/api/device/test-frame")
    def test_frame(body: TestFrameRequest) -> dict[str, object]:
        """M1 proof: one coloured, numbered tile on a chosen panel."""
        if not 0 <= body.panel <= 4:
            raise HTTPException(status_code=422, detail="panel must be 0..4")
        images = [render_test_panel(i) if i == body.panel else None for i in range(5)]
        try:
            results = _push(state, [body.panel], images)
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            return _error_response(exc)
        state.last_error = None
        return {"results": results}

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
    def apply_preset(preset_id: str) -> dict[str, object]:
        try:
            theme = load_preset(preset_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        state.config.theme = _theme_with_media(theme, store)
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
        return FileResponse(path)

    # -- sensors / push ------------------------------------------------
    @app.get("/api/sensors")
    def sensors() -> dict[str, object]:
        return {"values": state.collector.snapshot(), "history": state.collector.history()}

    @app.post("/api/send")
    def send(body: SendRequest | None = None) -> dict[str, object]:
        values = state.collector.snapshot()
        images = render_all(state.config.theme, values, store.media_dir)
        panels = body.panels if body else None
        try:
            results = _push(state, panels, images)
        except DeviceError as exc:
            state.last_error = exc.as_dict()
            return _error_response(exc)
        state.last_error = None
        return {"results": results}

    @app.get("/api/diagnostics")
    def diagnostics() -> dict[str, object]:
        return {
            "device": state.device_summary(),
            "last_replies": state.last_replies,
            "last_error": state.last_error,
            "sensors": state.collector.snapshot(),
            "data_dir": str(store.data_dir),
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
                images = render_all(theme, values, store.media_dir)
                await websocket.send_json(
                    {
                        "type": "tick",
                        "sensors": values,
                        "panels": [
                            {"index": index, "png": base64.b64encode(encode_png(image)).decode()}
                            for index, image in enumerate(images)
                        ],
                        "device": state.device_summary(),
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
