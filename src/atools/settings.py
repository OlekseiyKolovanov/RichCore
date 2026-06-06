from __future__ import annotations

import json
from dataclasses import asdict

from .models import AppSettings, BindConfig
from .paths import config_dir, legacy_appdata_dir


SETTINGS_PATH = config_dir() / "settings.json"
LEGACY_SETTINGS_PATH = legacy_appdata_dir("Atools") / "settings.json"


def _normalize_theme_mode(value: str | None) -> str:
    if value == "light":
        return "light"
    return "dark"


def _is_removed_checking_bind(bind: BindConfig) -> bool:
    haystack = f"{bind.name} {bind.text}".casefold()
    return "перевір" in haystack and "ситуац" in haystack


def _default_binds() -> tuple[list[BindConfig], list[BindConfig]]:
    return (
        [
            BindConfig("Вітаю", "ALT+F1", "Вітаю! Опрацьовую ваш запит.", "reply", False),
            BindConfig("Очікуйте", "ALT+F2", "Вітаю! Очікуйте.", "reply", False),
            BindConfig("Не виконуємо", "ALT+F3", "Вітаю! Адміністрація не виконує таких дій.", "reply", False),
            BindConfig("Уточніть", "ALT+F5", "Вітаю! Уточніть ваше питання у наступному репорті.", "reply", False),
            BindConfig("Предам", "ALT+F6", "Вітаю! Передам даному адміністратору ваш запит.", "reply", False),
            BindConfig("На форум", "ALT+F7", "Вітаю! Якщо не згодні з діями адміністратора, зверніться на форум.", "reply", False),
        ],
        [
            BindConfig("Телепорт", "NUM1", "/pwarp ", "command", True),
            BindConfig("Спостереження", "NUM2", "/sp ", "command", True),
            BindConfig("PM", "ALT+NUM2", "/pm {player_id} ", "command", True),
        ],
    )


def load_settings() -> AppSettings:
    if not SETTINGS_PATH.exists():
        if LEGACY_SETTINGS_PATH.exists():
            SETTINGS_PATH.write_text(LEGACY_SETTINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            reply_binds, command_binds = _default_binds()
            settings = AppSettings(reply_binds=reply_binds, command_binds=command_binds)
            save_settings(settings)
            return settings

    raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    reply_binds = [BindConfig(**item) for item in raw.get("reply_binds", [])]
    command_binds = [BindConfig(**item) for item in raw.get("command_binds", [])]
    reply_binds = [bind for bind in reply_binds if not _is_removed_checking_bind(bind)]
    vip_ad_punish_mode = raw.get("vip_ad_punish_mode", AppSettings().vip_ad_punish_mode)
    if vip_ad_punish_mode != "admin":
        vip_ad_punish_mode = "admin"

    return AppSettings(
        admin_nickname=raw.get("admin_nickname", ""),
        game_path=raw.get("game_path", AppSettings().game_path),
        console_log_path=raw.get("console_log_path", AppSettings().console_log_path),
        open_chat_before_insert=raw.get("open_chat_before_insert", True),
        overlays_enabled=raw.get("overlays_enabled", True),
        theme_mode=_normalize_theme_mode(raw.get("theme_mode", AppSettings().theme_mode)),
        vip_ad_helper_signature=raw.get("vip_ad_helper_signature", AppSettings().vip_ad_helper_signature),
        vip_ad_punish_mode=vip_ad_punish_mode,
        hotkey_other_reply=raw.get("hotkey_other_reply", AppSettings().hotkey_other_reply),
        hotkey_last_report_pm=raw.get("hotkey_last_report_pm", AppSettings().hotkey_last_report_pm),
        hotkey_last_reply_id=raw.get("hotkey_last_reply_id", AppSettings().hotkey_last_reply_id),
        reply_binds=reply_binds,
        command_binds=command_binds,
    )


def save_settings(settings: AppSettings) -> None:
    settings.theme_mode = _normalize_theme_mode(settings.theme_mode)
    payload = asdict(settings)
    SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
