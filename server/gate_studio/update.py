"""Check GitHub Releases and install the portable Windows build in place."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from . import __version__

GITHUB_REPO = "khanghbduong02/Divoom-PC"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
APP_ASSET_NAME = "GateThemeStudio.exe"
CHECKSUM_ASSET_NAME = "GateThemeStudio.exe.sha256"
USER_AGENT = "GateThemeStudio-updater"
REQUEST_TIMEOUT = 12.0
DOWNLOAD_TIMEOUT = 180.0
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


class UpdateError(RuntimeError):
    """An update cannot be checked, downloaded or started."""


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str | None
    available: bool
    can_install: bool
    install_supported: bool
    download_url: str | None
    checksum_url: str | None
    checksum: str | None
    download_size: int | None
    notes: str | None
    tag: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "available": self.available,
            "can_install": self.can_install,
            "install_supported": self.install_supported,
            "download_size": self.download_size,
            "notes": self.notes,
            "tag": self.tag,
        }


def install_supported() -> bool:
    """The portable exe can replace itself; a source checkout cannot."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _version_parts(value: str) -> tuple[int, ...]:
    cleaned = str(value).strip().lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    return tuple(int(part) for part in re.findall(r"\d+", cleaned))


def is_newer(candidate: str, current: str) -> bool:
    """Compare dotted numeric versions without requiring packaging."""
    left = _version_parts(candidate)
    right = _version_parts(current)
    if not left or not right:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _asset_by_name(assets: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((asset for asset in assets if asset.get("name") == name), None)


def _sha256_from_digest(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", value.strip())
    return match.group(1).lower() if match else None


def _sha256_from_checksum(text: str) -> str | None:
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    return match.group(1).lower() if match else None


def _request(client: httpx.Client | None, method: str, url: str, **kwargs: Any) -> httpx.Response:
    request_client = client or httpx
    headers = {"User-Agent": USER_AGENT}
    headers.update(kwargs.pop("headers", {}) or {})
    try:
        response = request_client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise UpdateError("Could not reach GitHub to check for updates.") from exc
    return response


def check_for_update(
    current_version: str | None = None,
    client: httpx.Client | None = None,
) -> UpdateInfo:
    """Return the latest release details, without downloading anything."""
    current = current_version or __version__
    supported = install_supported()
    response = _request(
        client,
        "GET",
        LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    if response.status_code == 404:
        raise UpdateError("No published Gate Theme Studio release was found.")
    if response.status_code != 200:
        raise UpdateError(f"GitHub returned HTTP {response.status_code} while checking for updates.")
    try:
        release = response.json()
    except ValueError as exc:
        raise UpdateError("GitHub returned an invalid release response.") from exc
    if not isinstance(release, dict):
        raise UpdateError("GitHub returned an invalid release response.")

    tag = str(release.get("tag_name") or "").strip()
    latest = tag.lstrip("vV") if tag else ""
    if not latest:
        raise UpdateError("The latest release has no version tag.")
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        assets = []
    app_asset = _asset_by_name(assets, APP_ASSET_NAME)
    if not app_asset or not app_asset.get("browser_download_url"):
        raise UpdateError("The latest release has no GateThemeStudio.exe download.")
    checksum_asset = _asset_by_name(assets, CHECKSUM_ASSET_NAME)
    size_value = app_asset.get("size")
    try:
        size = int(size_value) if size_value is not None else None
    except (TypeError, ValueError):
        size = None
    notes = release.get("body")
    if notes is not None:
        notes = str(notes).strip()[:4000] or None

    return UpdateInfo(
        current_version=current,
        latest_version=latest,
        available=is_newer(latest, current),
        can_install=supported,
        install_supported=supported,
        download_url=str(app_asset["browser_download_url"]),
        checksum_url=(
            str(checksum_asset["browser_download_url"])
            if checksum_asset and checksum_asset.get("browser_download_url")
            else None
        ),
        checksum=_sha256_from_digest(app_asset.get("digest")),
        download_size=size,
        notes=notes,
        tag=tag,
    )


def _download_checksum(info: UpdateInfo, client: httpx.Client | None) -> str:
    if info.checksum:
        return info.checksum
    if not info.checksum_url:
        raise UpdateError("The latest release has no SHA-256 checksum to verify the download.")
    response = _request(
        client,
        "GET",
        info.checksum_url,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    if response.status_code != 200:
        raise UpdateError("Could not download the update checksum.")
    checksum = _sha256_from_checksum(response.text)
    if not checksum:
        raise UpdateError("The update checksum file is invalid.")
    return checksum


def download_update(
    info: UpdateInfo,
    target_dir: Path,
    client: httpx.Client | None = None,
) -> Path:
    """Download and verify the release executable, returning its local path."""
    if not info.download_url:
        raise UpdateError("The latest release has no downloadable app.")
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    version = re.sub(r"[^A-Za-z0-9._-]+", "-", info.latest_version or "latest").strip(".-") or "latest"
    target = target_dir / f"GateThemeStudio-{version}.exe"
    partial = target.with_suffix(".exe.download")
    if partial.exists():
        partial.unlink()

    expected = _download_checksum(info, client)
    hasher = hashlib.sha256()
    total = 0
    request_client = client or httpx
    try:
        with request_client.stream(
            "GET",
            info.download_url,
            headers={"User-Agent": USER_AGENT},
            timeout=DOWNLOAD_TIMEOUT,
            follow_redirects=True,
        ) as response:
            if response.status_code != 200:
                raise UpdateError(f"GitHub returned HTTP {response.status_code} for the update.")
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise UpdateError("The update file is unexpectedly large.")
                    handle.write(chunk)
                    hasher.update(chunk)
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("The update download was interrupted.") from exc
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    if hasher.hexdigest().lower() != expected.lower():
        partial.unlink(missing_ok=True)
        raise UpdateError("The downloaded update did not match its SHA-256 checksum.")
    if info.download_size is not None and total != info.download_size:
        partial.unlink(missing_ok=True)
        raise UpdateError("The downloaded update was incomplete.")

    try:
        os.replace(partial, target)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("Could not save the downloaded update.") from exc
    return target


def _ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _restart_args() -> list[str]:
    return [str(value) for value in sys.argv[1:]]


_TARGET_LINE = re.compile(r"^\$target\s*=\s*'((?:[^']|'')*)'\s*$", re.MULTILINE)


def _target_from_update_script(script: Path) -> Path | None:
    """Read the install path an interrupted update helper was about to use."""
    try:
        text = script.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    match = _TARGET_LINE.search(text)
    if not match:
        return None
    value = match.group(1).replace("''", "'").strip()
    return Path(value) if value else None


def _clean_pyinstaller_environment() -> dict[str, str]:
    """Do not let a restarted PyInstaller app inherit the old temp folder.

    A one-file app starts its child with ``_PYI_APPLICATION_HOME_DIR`` set. If
    the app starts another copy without clearing that variable, the new copy
    reuses the old ``_MEI`` directory after it has been deleted and fails to
    load ``python313.dll`` before any Python code runs.
    """
    env = os.environ.copy()
    for name in (
        "_PYI_APPLICATION_HOME_DIR",
        "_PYI_ARCHIVE_FILE",
        "_PYI_PARENT_PROCESS_LEVEL",
        "_MEIPASS2",
        "_MEIPASS",
    ):
        env.pop(name, None)
    return env


def recover_from_failed_update() -> bool:
    """Finish an update that the old helper left sitting in the updates folder.

    A copy of the new exe can be launched directly from
    ``%APPDATA%\\GateThemeStudio\\updates`` after an interrupted update. If the
    previous helper left ``apply-update.ps1`` behind, use its target path to put
    this newer exe back in the installed location and start that copy.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    here = Path(sys.executable).resolve()
    target = _target_from_update_script(here.parent / "apply-update.ps1")
    if target is None:
        return False
    target = target.resolve()
    if target == here or not target.is_file():
        return False
    try:
        shutil.copy2(here, target)
    except OSError:
        return False
    try:
        with (here.parent / "apply-update.log").open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} recovery: installed to {target}\n")
    except OSError:
        pass
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(
            [str(target)],
            cwd=str(target.parent),
            env=_clean_pyinstaller_environment(),
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def launch_updater(
    new_exe: Path,
    *,
    current_exe: Path | None = None,
    restart_args: list[str] | None = None,
    data_dir: Path | None = None,
) -> Path:
    """Start a detached PowerShell helper that replaces the exe after exit."""
    if sys.platform != "win32":
        raise UpdateError("In-app updates are available in the Windows app only.")
    new_exe = Path(new_exe).resolve()
    target = Path(current_exe or sys.executable).resolve()
    if not new_exe.is_file():
        raise UpdateError("The downloaded update file is missing.")
    if not target.is_file():
        raise UpdateError("The running application path could not be found.")

    script_dir = (Path(data_dir) if data_dir else new_exe.parent).resolve()
    script_dir.mkdir(parents=True, exist_ok=True)
    script = script_dir / "apply-update.ps1"
    # These must be absolute: the helper's working directory is script_dir,
    # so a relative marker would resolve to script_dir/updates/... and never
    # be seen by the app waiting in script_dir.
    log = (script_dir / "apply-update.log").resolve()
    ready = (script_dir / "apply-update.ready").resolve()
    ready.unlink(missing_ok=True)
    args = restart_args if restart_args is not None else _restart_args()
    arg_array = "@(" + ", ".join(_ps_quote(arg) for arg in args) + ")"
    script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$target = {_ps_quote(target)}",
                f"$new = {_ps_quote(new_exe)}",
                f"$backup = {_ps_quote(str(target) + '.old')}",
                f"$selfPid = {os.getpid()}",
                f"$restartArgs = {arg_array}",
                f"$log = {_ps_quote(log)}",
                f"$ready = {_ps_quote(ready)}",
                "function Write-UpdateLog([string]$message) {",
                "  try { Add-Content -LiteralPath $log -Value ((Get-Date -Format o) + ' ' + $message) -ErrorAction SilentlyContinue } catch {}",
                "}",
                "function Clear-PyInstallerEnvironment() {",
                "  foreach ($name in @('_PYI_APPLICATION_HOME_DIR','_PYI_ARCHIVE_FILE','_PYI_PARENT_PROCESS_LEVEL','_MEIPASS2','_MEIPASS')) {",
                "    Remove-Item -Path ('Env:' + $name) -ErrorAction SilentlyContinue",
                "  }",
                "}",
                "trap { Write-UpdateLog ('fatal: ' + $_); exit 1 }",
                "Write-UpdateLog ('helper started; target=' + $target + '; new=' + $new)",
                "try { Set-Content -LiteralPath $ready -Value 'ready' -Encoding ASCII -ErrorAction Stop } catch { Write-UpdateLog ('ready marker failed: ' + $_) }",
                "try { Wait-Process -Id $selfPid -Timeout 60 -ErrorAction SilentlyContinue } catch { Write-UpdateLog ('wait failed: ' + $_) }",
                "Write-UpdateLog 'application process exited'",
                "Start-Sleep -Milliseconds 600",
                "$replaced = $false",
                "for ($i = 0; $i -lt 40; $i++) {",
                "  try {",
                "    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction Stop }",
                "    Move-Item -LiteralPath $target -Destination $backup -Force -ErrorAction Stop",
                "    Copy-Item -LiteralPath $new -Destination $target -Force -ErrorAction Stop",
                "    $replaced = $true",
                "    Write-UpdateLog 'replacement complete'",
                "    break",
                "  } catch {",
                "    Write-UpdateLog ('replace attempt ' + ($i + 1) + ' failed: ' + $_)",
                "    if (-not (Test-Path -LiteralPath $target) -and (Test-Path -LiteralPath $backup)) {",
                "      try { Move-Item -LiteralPath $backup -Destination $target -Force -ErrorAction Stop } catch {}",
                "    }",
                "    Start-Sleep -Milliseconds 500",
                "  }",
                "}",
                "if ($replaced) {",
                "  try {",
                "    Clear-PyInstallerEnvironment",
                "    $startArgs = @{ FilePath = $target; WorkingDirectory = (Split-Path -Parent $target) }",
                "    if ($restartArgs.Count -gt 0) { $startArgs.ArgumentList = $restartArgs }",
                "    Start-Process @startArgs -ErrorAction Stop",
                "    Write-UpdateLog 'new process started'",
                "    Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue } catch {",
                "    Write-UpdateLog ('could not start new process: ' + $_)",
                "    if (Test-Path -LiteralPath $backup) {",
                "      Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue",
                "      Move-Item -LiteralPath $backup -Destination $target -Force -ErrorAction SilentlyContinue",
                "      Clear-PyInstallerEnvironment",
                "      $fallbackArgs = @{ FilePath = $target; WorkingDirectory = (Split-Path -Parent $target) }",
                "      if ($restartArgs.Count -gt 0) { $fallbackArgs.ArgumentList = $restartArgs }",
                "      Start-Process @fallbackArgs",
                "      Write-UpdateLog 'fallback process started'",
                "    }",
                "  }",
                "} elseif (Test-Path -LiteralPath $backup) {",
                "  Write-UpdateLog 'replacement failed; starting the previous version'",
                "  Move-Item -LiteralPath $backup -Destination $target -Force -ErrorAction SilentlyContinue",
                "  Clear-PyInstallerEnvironment",
                "  $fallbackArgs = @{ FilePath = $target; WorkingDirectory = (Split-Path -Parent $target) }",
                "  if ($restartArgs.Count -gt 0) { $fallbackArgs.ArgumentList = $restartArgs }",
                "  Start-Process @fallbackArgs",
                "}",
                "Remove-Item -LiteralPath $ready -Force -ErrorAction SilentlyContinue",
                "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
                "",
            ]
        ),
        encoding="utf-8-sig",
    )
    # DETACHED_PROCESS makes Windows PowerShell exit without running the script.
    # A new process group with no console keeps the helper independent of the app.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        helper = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script),
            ],
            cwd=str(script_dir),
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError("Could not start the update helper.") from exc

    # Do not leave the app until the helper has really started. This turns a
    # silent PowerShell failure into a visible message instead of a closed app.
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        if ready.exists():
            return script
        if helper.poll() is not None:
            break
        time.sleep(0.1)
    try:
        helper.terminate()
    except OSError:
        pass
    raise UpdateError(
        "The update helper did not start. Gate Theme Studio is still running; try again."
    )


def schedule_app_exit(delay: float = 1.2) -> None:
    """Give the HTTP response time to leave before the updater takes over."""
    import threading

    def _exit() -> None:
        time.sleep(delay)
        os._exit(0)

    threading.Thread(target=_exit, name="update-exit", daemon=True).start()


__all__ = [
    "UpdateError",
    "UpdateInfo",
    "check_for_update",
    "download_update",
    "install_supported",
    "is_newer",
    "launch_updater",
    "recover_from_failed_update",
    "schedule_app_exit",
]
