from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "RichCore"


def source_root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def bundle_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return source_root_dir()


def app_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root_dir()


def asset_path(name: str) -> Path:
    return bundle_root_dir() / "assets" / name


def ai_seed_dir() -> Path:
    return source_root_dir().parent.parent / "AI TEST 2"


def ai_resource_path(name: str) -> Path:
    candidates = [
        app_root_dir() / "ai" / name,
        source_root_dir() / "ai" / name,
        bundle_root_dir() / "ai" / name,
        ai_seed_dir() / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def ai_config_path() -> Path:
    local_config = config_dir() / "ai_config.json"
    if local_config.exists():
        return local_config

    candidates = [
        app_root_dir() / "ai" / "config.json",
        source_root_dir() / "ai" / "config.json",
        bundle_root_dir() / "ai" / "config.json",
        ai_seed_dir() / "config.json",
        app_root_dir() / "ai" / "config.example.json",
        source_root_dir() / "ai" / "config.example.json",
        bundle_root_dir() / "ai" / "config.example.json",
        ai_seed_dir() / "config.example.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return local_config

def config_dir() -> Path:
    path = app_root_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_root_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_appdata_dir(app_name: str = APP_NAME) -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return base / app_name
