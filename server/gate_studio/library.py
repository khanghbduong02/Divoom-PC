"""User-saved panel and full-theme designs, kept beside the config."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field

from .models import Panel, Theme

LIBRARY_FILE = "saved.json"


class SavedTheme(BaseModel):
    id: str
    name: str
    created_at: float
    updated_at: float
    theme: Theme


class SavedPanel(BaseModel):
    id: str
    name: str
    created_at: float
    updated_at: float
    panel: Panel


class _LibraryData(BaseModel):
    themes: list[SavedTheme] = Field(default_factory=list)
    panels: list[SavedPanel] = Field(default_factory=list)


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        raise ValueError("a saved design needs a name")
    return cleaned[:80]


def _meta(item: SavedTheme | SavedPanel) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


class SavedLibrary:
    """One ``saved.json`` shared by the editor, the tray and restarts."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / LIBRARY_FILE
        self._lock = Lock()

    def _read(self) -> _LibraryData:
        if not self.path.exists():
            return _LibraryData()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _LibraryData()
        if not isinstance(raw, dict):
            return _LibraryData()
        themes: list[SavedTheme] = []
        for entry in raw.get("themes") or []:
            try:
                themes.append(SavedTheme.model_validate(entry))
            except ValueError:
                continue
        panels: list[SavedPanel] = []
        for entry in raw.get("panels") or []:
            try:
                panels.append(SavedPanel.model_validate(entry))
            except ValueError:
                continue
        return _LibraryData(themes=themes, panels=panels)

    def _write(self, data: _LibraryData) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=str(self.data_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data.model_dump(mode="json"), handle, indent=2)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def list(self) -> dict[str, list[dict[str, object]]]:
        with self._lock:
            data = self._read()
            themes = sorted(data.themes, key=lambda item: item.updated_at, reverse=True)
            panels = sorted(data.panels, key=lambda item: item.updated_at, reverse=True)
            return {
                "themes": [_meta(item) for item in themes],
                "panels": [_meta(item) for item in panels],
            }

    def save_theme(self, name: str, theme: Theme) -> dict[str, object]:
        cleaned = _clean_name(name)
        now = time.time()
        with self._lock:
            data = self._read()
            existing = next(
                (item for item in data.themes if item.name.casefold() == cleaned.casefold()),
                None,
            )
            if existing is not None:
                existing.name = cleaned
                existing.theme = theme.model_copy(deep=True)
                existing.updated_at = now
                saved = existing
            else:
                saved = SavedTheme(
                    id=uuid.uuid4().hex[:12],
                    name=cleaned,
                    created_at=now,
                    updated_at=now,
                    theme=theme.model_copy(deep=True),
                )
                data.themes.append(saved)
            self._write(data)
        return _meta(saved)

    def save_panel(self, name: str, panel: Panel) -> dict[str, object]:
        cleaned = _clean_name(name)
        now = time.time()
        with self._lock:
            data = self._read()
            existing = next(
                (item for item in data.panels if item.name.casefold() == cleaned.casefold()),
                None,
            )
            if existing is not None:
                existing.name = cleaned
                existing.panel = panel.model_copy(deep=True)
                existing.updated_at = now
                saved = existing
            else:
                saved = SavedPanel(
                    id=uuid.uuid4().hex[:12],
                    name=cleaned,
                    created_at=now,
                    updated_at=now,
                    panel=panel.model_copy(deep=True),
                )
                data.panels.append(saved)
            self._write(data)
        return _meta(saved)

    def get_theme(self, saved_id: str) -> SavedTheme:
        with self._lock:
            data = self._read()
            for item in data.themes:
                if item.id == saved_id:
                    return item.model_copy(deep=True)
        raise KeyError(saved_id)

    def get_panel(self, saved_id: str) -> SavedPanel:
        with self._lock:
            data = self._read()
            for item in data.panels:
                if item.id == saved_id:
                    return item.model_copy(deep=True)
        raise KeyError(saved_id)


__all__ = ["LIBRARY_FILE", "SavedLibrary", "SavedPanel", "SavedTheme"]
