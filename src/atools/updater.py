from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from .paths import source_root_dir
from .version import __version__


GITHUB_OWNER = "OlekseiyKolovanov"
GITHUB_REPO = "RichCore"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
USER_AGENT = f"RichCore/{__version__}"


@dataclass(slots=True)
class UpdateInfo:
    version: str
    mode: str
    url: str = ""
    asset_name: str = ""


class UpdateCheckThread(QThread):
    update_available = Signal(object)

    def run(self) -> None:
        try:
            info = check_for_update()
        except Exception:
            return
        if info is not None:
            self.update_available.emit(info)


def _request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.replace("-", ".").split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def _is_newer(remote_version: str, current_version: str) -> bool:
    remote = _version_tuple(remote_version)
    current = _version_tuple(current_version)
    if remote and current:
        return remote > current
    return remote_version.strip().lower() != current_version.strip().lower()


def _release_update() -> UpdateInfo | None:
    release = _request_json(f"{GITHUB_API}/releases/latest")
    version = str(release.get("tag_name") or "").lstrip("vV")
    if not version or not _is_newer(version, __version__):
        return None

    assets = release.get("assets") or []
    for asset in assets:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name.lower() == "richcore_v12.zip" and url:
            return UpdateInfo(version=version, mode="release", url=url, asset_name=name)
    for asset in assets:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name.lower().endswith(".exe") and "richcore" in name.lower() and url:
            return UpdateInfo(version=version, mode="release", url=url, asset_name=name)
    return None


def _git_update() -> UpdateInfo | None:
    root = source_root_dir()
    if not (root / ".git").exists():
        return None

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode != 0:
        return None
    fetch = git("fetch", "--quiet")
    if fetch.returncode != 0:
        return None
    local = git("rev-parse", "HEAD")
    remote = git("rev-parse", "@{u}")
    if local.returncode != 0 or remote.returncode != 0:
        return None
    if local.stdout.strip() == remote.stdout.strip():
        return None
    return UpdateInfo(version=remote.stdout.strip()[:7], mode="git")


def check_for_update() -> UpdateInfo | None:
    if getattr(sys, "frozen", False):
        return _release_update()
    return _git_update()


def maybe_prompt_for_update(parent: QWidget) -> None:
    if os.environ.get("RICHCORE_SKIP_UPDATE_CHECK") == "1":
        return
    thread = UpdateCheckThread(parent)
    parent._richcore_update_thread = thread
    thread.update_available.connect(lambda info: _prompt_for_update(parent, info))
    thread.finished.connect(lambda: setattr(parent, "_richcore_update_thread", None))
    thread.start()


def _prompt_for_update(parent: QWidget, info: UpdateInfo) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle("Оновлення RichCore")
    if info.mode == "git":
        box.setText("У GitHub-репозиторії є нові зміни.")
    else:
        box.setText(f"Доступна нова версія RichCore {info.version}.")
    box.setInformativeText("Встановити оновлення зараз?")
    install_button = box.addButton("Встановити", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Пізніше", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is install_button:
        install_update(parent, info)


def install_update(parent: QWidget, info: UpdateInfo) -> None:
    if info.mode == "git":
        _install_git_update(parent)
    elif info.mode == "release":
        _install_release_update(parent, info)


def _install_git_update(parent: QWidget) -> None:
    root = source_root_dir()
    result = subprocess.run(
        ["git", "-C", str(root), "pull", "--ff-only"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        QMessageBox.warning(parent, "Оновлення RichCore", result.stderr.strip() or "Не вдалося виконати git pull.")
        return

    QMessageBox.information(parent, "Оновлення RichCore", "Оновлення встановлено. RichCore перезапуститься.")
    subprocess.Popen([sys.executable, *sys.argv], cwd=str(root))
    app = QApplication.instance()
    if app is not None:
        QTimer.singleShot(200, app.quit)


def _install_release_update(parent: QWidget, info: UpdateInfo) -> None:
    target = Path(sys.executable).resolve()
    target_dir = target.parent
    temp_dir = Path(tempfile.gettempdir()) / "RichCoreUpdate"
    temp_dir.mkdir(parents=True, exist_ok=True)
    downloaded = temp_dir / (info.asset_name or "RichCore_v12.zip")

    request = urllib.request.Request(info.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            downloaded.write_bytes(response.read())
    except Exception as exc:
        QMessageBox.warning(parent, "Оновлення RichCore", f"Не вдалося завантажити оновлення: {exc}")
        return

    if downloaded.suffix.lower() == ".zip":
        extracted = temp_dir / "extracted"
        if extracted.exists():
            import shutil

            shutil.rmtree(extracted, ignore_errors=True)
        extracted.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(downloaded) as archive:
                archive.extractall(extracted)
        except Exception as exc:
            QMessageBox.warning(parent, "Оновлення RichCore", f"Не вдалося розпакувати оновлення: {exc}")
            return

        source_dir = extracted / "RichCore_v12"
        if not source_dir.exists():
            source_dir = extracted
        script = _write_folder_update_script(temp_dir, source_dir, target_dir, target)
    else:
        script = _write_exe_update_script(temp_dir, downloaded, target)

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ProcessId",
            str(os.getpid()),
        ],
        cwd=str(target.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    app = QApplication.instance()
    if app is not None:
        QTimer.singleShot(250, app.quit)


def _write_exe_update_script(temp_dir: Path, new_exe: Path, target: Path) -> Path:
    script = temp_dir / "apply_update.ps1"
    script.write_text(
        """
param(
  [int]$ProcessId
)
$NewExe = '%NEW_EXE%'
$TargetExe = '%TARGET_EXE%'
Wait-Process -Id $ProcessId -Timeout 30 -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $NewExe -Destination $TargetExe -Force
Start-Process -FilePath $TargetExe -WorkingDirectory (Split-Path -Parent $TargetExe)
Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
""".strip()
        .replace("%NEW_EXE%", str(new_exe).replace("'", "''"))
        .replace("%TARGET_EXE%", str(target).replace("'", "''")),
        encoding="utf-8",
    )
    return script


def _write_folder_update_script(temp_dir: Path, source_dir: Path, target_dir: Path, target_exe: Path) -> Path:
    script = temp_dir / "apply_update.ps1"
    script.write_text(
        """
param(
  [int]$ProcessId
)
$SourceDir = '%SOURCE_DIR%'
$TargetDir = '%TARGET_DIR%'
$TargetExe = '%TARGET_EXE%'
Wait-Process -Id $ProcessId -Timeout 30 -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
Get-ChildItem -LiteralPath $SourceDir -Force | Copy-Item -Destination $TargetDir -Recurse -Force
Start-Process -FilePath $TargetExe -WorkingDirectory $TargetDir
Remove-Item -LiteralPath '%TEMP_DIR%' -Recurse -Force -ErrorAction SilentlyContinue
""".strip()
        .replace("%SOURCE_DIR%", str(source_dir).replace("'", "''"))
        .replace("%TARGET_DIR%", str(target_dir).replace("'", "''"))
        .replace("%TARGET_EXE%", str(target_exe).replace("'", "''"))
        .replace("%TEMP_DIR%", str(temp_dir).replace("'", "''")),
        encoding="utf-8",
    )
    return script
