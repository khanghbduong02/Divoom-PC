"""Update-check parsing and version tests; no network is used."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gate_studio import update


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        assert self._payload is not None
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        return self.response


def test_numeric_versions_compare_correctly() -> None:
    assert update.is_newer("0.2.2", "0.2.1")
    assert update.is_newer("v1.0", "0.9.9")
    assert not update.is_newer("0.2.1", "0.2.1")
    assert not update.is_newer("0.2.0", "0.2.1")


def test_target_from_update_script(tmp_path: Path) -> None:
    script = tmp_path / "apply-update.ps1"
    script.write_text(
        "$target = 'C:\\Users\\test\\GateThemeStudio.exe'\n$new = 'C:\\Temp\\new.exe'\n",
        encoding="utf-8-sig",
    )
    assert update._target_from_update_script(script) == Path(
        r"C:\Users\test\GateThemeStudio.exe"
    )


def test_target_from_update_script_rejects_missing_target(tmp_path: Path) -> None:
    script = tmp_path / "apply-update.ps1"
    script.write_text("$new = 'C:\\Temp\\new.exe'\n", encoding="utf-8-sig")
    assert update._target_from_update_script(script) is None


def test_check_for_update_reads_the_release_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update, "install_supported", lambda: True)
    client = FakeClient(
        FakeResponse(
            200,
            {
                "tag_name": "v0.2.2",
                "body": "Small fixes.",
                "assets": [
                    {
                        "name": "GateThemeStudio.exe",
                        "size": 1234,
                        "browser_download_url": "https://example.test/app.exe",
                        "digest": "sha256:" + "a" * 64,
                    },
                    {
                        "name": "GateThemeStudio.exe.sha256",
                        "browser_download_url": "https://example.test/app.sha256",
                    },
                ],
            },
        )
    )

    info = update.check_for_update("0.2.1", client=client)

    assert info.latest_version == "0.2.2"
    assert info.available is True
    assert info.can_install is True
    assert info.download_url == "https://example.test/app.exe"
    assert info.checksum_url == "https://example.test/app.sha256"
    assert info.checksum == "a" * 64
    assert info.download_size == 1234
    assert info.notes == "Small fixes."


def test_check_for_update_handles_an_older_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update, "install_supported", lambda: False)
    client = FakeClient(
        FakeResponse(
            200,
            {
                "tag_name": "v0.2.1",
                "assets": [
                    {
                        "name": "GateThemeStudio.exe",
                        "browser_download_url": "https://example.test/app.exe",
                    }
                ],
            },
        )
    )

    info = update.check_for_update("0.2.1", client=client)

    assert info.available is False
    assert info.can_install is False
    assert info.install_supported is False


def test_check_for_update_rejects_a_release_without_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(update, "install_supported", lambda: True)
    client = FakeClient(FakeResponse(200, {"tag_name": "v0.2.2", "assets": []}))

    with pytest.raises(update.UpdateError, match="no GateThemeStudio.exe"):
        update.check_for_update("0.2.1", client=client)


def test_clean_pyinstaller_environment_drops_restart_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEIold")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\App.exe")
    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "0")
    monkeypatch.setenv("KEEP_ME", "yes")
    env = update._clean_pyinstaller_environment()
    assert "_PYI_APPLICATION_HOME_DIR" not in env
    assert "_PYI_ARCHIVE_FILE" not in env
    assert "_PYI_PARENT_PROCESS_LEVEL" not in env
    assert env["KEEP_ME"] == "yes"


def test_updater_helper_clears_pyinstaller_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        pytest.skip("The in-app updater is Windows-only")
    target = tmp_path / "GateThemeStudio.exe"
    new = tmp_path / "GateThemeStudio-new.exe"
    target.write_bytes(b"old")
    new.write_bytes(b"new")

    class FakeHelper:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    def fake_popen(*args: object, **kwargs: object) -> FakeHelper:
        (tmp_path / "apply-update.ready").write_text("ready", encoding="ascii")
        return FakeHelper()

    monkeypatch.setattr(update.subprocess, "Popen", fake_popen)
    script = update.launch_updater(
        new, current_exe=target, restart_args=[], data_dir=tmp_path
    )
    text = script.read_text(encoding="utf-8-sig")
    assert "Clear-PyInstallerEnvironment" in text
    assert "_PYI_APPLICATION_HOME_DIR" in text
    assert "_PYI_PARENT_PROCESS_LEVEL" in text
    # The helper runs with its workdir inside the updates folder. Relative
    # log/marker paths made it look for updates/updates/... and never signal
    # readiness, so the app timed out and stayed open after downloading.
    assert f"$log = '{tmp_path / 'apply-update.log'}'" in text
    assert f"$ready = '{tmp_path / 'apply-update.ready'}'" in text


def test_download_rejects_a_bad_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    info = update.UpdateInfo(
        current_version="0.2.1",
        latest_version="0.2.2",
        available=True,
        can_install=True,
        install_supported=True,
        download_url="https://example.test/app.exe",
        checksum_url=None,
        checksum="0" * 64,
        download_size=None,
        notes=None,
        tag="v0.2.2",
    )

    class StreamResponse:
        status_code = 200

        def iter_bytes(self, size: int):
            yield b"not the right bytes"

    class Stream:
        def __enter__(self) -> StreamResponse:
            return StreamResponse()

        def __exit__(self, *args: object) -> None:
            return None

    class DownloadClient:
        def stream(self, *args: object, **kwargs: object) -> Stream:
            return Stream()

    with pytest.raises(update.UpdateError, match="checksum"):
        update.download_update(info, tmp_path, client=DownloadClient())  # type: ignore[arg-type]

    assert not list(tmp_path.glob("*.exe"))
