"""Update-check parsing and version tests; no network is used."""

from __future__ import annotations

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
