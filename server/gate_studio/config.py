"""On-disk state: one ``config.json`` plus a ``media/`` folder.

Location follows the platform convention (``%APPDATA%\\GateThemeStudio`` on
Windows) and can be overridden with ``GATE_STUDIO_DATA_DIR`` for tests.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from threading import Lock

from .models import CONFIG_VERSION, AppConfig, AppSettings

APP_DIR_NAME = "GateThemeStudio"
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
CONFIG_FILE = "config.json"
TOKEN_FILE = "token"


def platform_data_dir() -> Path:
    override = os.environ.get("GATE_STUDIO_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


class ConfigStore:
    """Loads and saves the agent config, generating an auth token on first run."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else platform_data_dir()
        self.media_dir = self.data_dir / "media"
        self._lock = Lock()
        self._config: AppConfig | None = None

    # -- paths ---------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.data_dir / CONFIG_FILE

    def ensure_dirs(self) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def media_path(self, name: str) -> Path:
        safe = Path(name.replace("\\", "/")).name
        return self.media_dir / safe

    # -- auth token ----------------------------------------------------
    def token(self) -> str:
        self.ensure_dirs()
        path = self.data_dir / TOKEN_FILE
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        token = secrets.token_urlsafe(24)
        path.write_text(token + "\n", encoding="utf-8")
        try:  # best effort: keep the token private on POSIX
            path.chmod(0o600)
        except OSError:
            pass
        return token

    # -- config --------------------------------------------------------
    def load(self) -> AppConfig:
        with self._lock:
            if self._config is not None:
                return self._config
            self.ensure_dirs()
            if self.config_path.exists():
                try:
                    raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                    migrated = self._migrate(raw)
                    self._config = AppConfig.model_validate(migrated)
                except (ValueError, OSError):
                    self._config = AppConfig()
            else:
                self._config = AppConfig()
            return self._config

    @staticmethod
    def _migrate(raw: object) -> object:
        """Older configs predate always-on updates; enable them on upgrade."""
        if not isinstance(raw, dict):
            return raw
        if int(raw.get("schema_version") or 1) >= CONFIG_VERSION:
            return raw
        settings = raw.get("settings")
        if isinstance(settings, dict):
            # v1 had no switch for this at all, so its stored False was just the default
            settings["auto_push"] = True
            settings.setdefault("push_interval", 2.0)
            settings.setdefault("autostart", True)
        raw["schema_version"] = CONFIG_VERSION
        return raw

    def save(self, config: AppConfig | None = None) -> AppConfig:
        with self._lock:
            if config is not None:
                self._config = config
            current = self._config or AppConfig()
            self.ensure_dirs()
            payload = current.model_dump(mode="json")
            # atomic replace so a crash mid-write cannot blank the theme
            fd, tmp_name = tempfile.mkstemp(dir=str(self.data_dir), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                os.replace(tmp_name, self.config_path)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            return current

    # -- media ---------------------------------------------------------
    def save_media(self, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in MEDIA_SUFFIXES:
            raise ValueError(f"unsupported image type {suffix or '(none)'}")
        self.ensure_dirs()
        name = f"{secrets.token_hex(6)}{suffix}"
        self.media_path(name).write_bytes(data)
        return name

    def delete_media(self, name: str) -> None:
        path = self.media_path(name)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
