"""Config storage: first run, migration from v1, atomic save."""

from __future__ import annotations

import json
from pathlib import Path

from gate_studio.config import ConfigStore


def test_first_run_creates_defaults(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "data")
    config = store.load()
    assert config.schema_version >= 2
    assert config.settings.auto_push is True
    assert config.settings.native_stats is True
    assert config.settings.push_interval > 0


def test_v1_config_turns_updates_on(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "device": {"host": "192.168.1.5", "port": 9000, "protocol": "hw402"},
                "settings": {"refresh_interval": 2.0, "auto_push": False},
                "theme": {"name": "Old", "panels": []},
            }
        ),
        encoding="utf-8",
    )
    config = ConfigStore(tmp_path).load()
    assert config.settings.auto_push is True
    assert config.settings.push_interval == 2.0
    assert config.device.host == "192.168.1.5"


def test_v2_config_keeps_its_update_choice(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "settings": {"auto_push": False, "push_interval": 4.0},
                "theme": {"name": "Old", "panels": []},
            }
        ),
        encoding="utf-8",
    )
    config = ConfigStore(tmp_path).load()
    assert config.settings.auto_push is False
    assert config.settings.push_interval == 4.0
    assert config.settings.external_watch is True


def test_save_is_atomic_and_reloadable(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    config = store.load()
    config.settings.push_interval = 7.5
    store.save(config)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["settings"]["push_interval"] == 7.5
    assert ConfigStore(tmp_path).load().settings.push_interval == 7.5
