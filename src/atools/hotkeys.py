from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, QAbstractNativeEventFilter, QTimer, Signal


user32 = ctypes.windll.user32

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

VK_MAP = {
    **{f"F{i}": 0x6F + i for i in range(1, 25)},
    **{chr(letter): letter for letter in range(0x41, 0x5B)},
    **{str(num): 0x30 + num for num in range(0, 10)},
    **{f"NUM{i}": 0x60 + i for i in range(0, 10)},
    "NUMPLUS": 0x6B,
    "NUMMINUS": 0x6D,
    "NUMMULT": 0x6A,
    "NUMDIV": 0x6F,
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "HOME": 0x24,
    "END": 0x23,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
}

MOD_MAP = {
    "ALT": MOD_ALT,
    "CTRL": MOD_CONTROL,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
}

MODIFIER_KEYS = {
    "ALT": (VK_MENU,),
    "CTRL": (VK_CONTROL,),
    "SHIFT": (VK_SHIFT,),
    "WIN": (VK_LWIN, VK_RWIN),
}


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    modifiers, vk, _ = parse_hotkey_parts(hotkey)
    return modifiers, vk


def parse_hotkey_parts(hotkey: str) -> tuple[int, int, tuple[int, ...]]:
    if not hotkey:
        raise ValueError("empty hotkey")
    parts = [part.strip().upper() for part in hotkey.split("+") if part.strip()]
    modifiers = 0
    key_name = ""
    watched_keys: list[int] = []
    for part in parts:
        if part in MOD_MAP:
            modifiers |= MOD_MAP[part]
            watched_keys.extend(MODIFIER_KEYS[part])
            continue
        key_name = part
    if not key_name or key_name not in VK_MAP:
        raise ValueError(f"unsupported hotkey: {hotkey}")
    watched_keys.append(VK_MAP[key_name])
    return modifiers, VK_MAP[key_name], tuple(dict.fromkeys(watched_keys))


class HotkeyEventFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "GlobalHotkeyManager") -> None:
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, event_type, message):
        event_name = bytes(event_type).decode(errors="ignore") if hasattr(event_type, "data") else str(event_type)
        if "windows_generic_MSG" not in event_name:
            return False, 0

        address = int(message)
        if not address:
            return False, 0

        msg = wintypes.MSG.from_address(address)
        if msg.message == WM_HOTKEY:
            self._manager.hotkey_pressed.emit(int(msg.wParam))
            return True, 0
        return False, 0


class GlobalHotkeyManager(QObject):
    hotkey_pressed = Signal(int)
    _DEBOUNCE_NS = 320_000_000
    _EXECUTE_DELAY_MS = 28
    _RELEASE_POLL_MS = 12

    def __init__(self, app, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._filter = HotkeyEventFilter(self)
        self._app.installNativeEventFilter(self._filter)
        self._callbacks: dict[int, tuple[str, callable, tuple[int, ...]]] = {}
        self._last_trigger_ns: dict[int, int] = {}
        self._locked_hotkeys: set[int] = set()
        self.hotkey_pressed.connect(self._dispatch)

    def register(self, hotkey_id: int, hotkey_text: str, callback: callable) -> None:
        self.unregister(hotkey_id)
        modifiers, vk, watched_keys = parse_hotkey_parts(hotkey_text)
        if not user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            raise OSError(f"RegisterHotKey failed for {hotkey_text}")
        self._callbacks[hotkey_id] = (hotkey_text, callback, watched_keys)

    def unregister(self, hotkey_id: int) -> None:
        if hotkey_id in self._callbacks:
            user32.UnregisterHotKey(None, hotkey_id)
            self._callbacks.pop(hotkey_id, None)
            self._last_trigger_ns.pop(hotkey_id, None)
            self._locked_hotkeys.discard(hotkey_id)

    def clear(self) -> None:
        for hotkey_id in list(self._callbacks):
            self.unregister(hotkey_id)

    def _dispatch(self, hotkey_id: int) -> None:
        if hotkey_id in self._locked_hotkeys:
            return

        now = time.monotonic_ns()
        last = self._last_trigger_ns.get(hotkey_id, 0)
        if now - last < self._DEBOUNCE_NS:
            return
        self._last_trigger_ns[hotkey_id] = now

        callback = self._callbacks.get(hotkey_id)
        if callback:
            self._locked_hotkeys.add(hotkey_id)
            QTimer.singleShot(self._EXECUTE_DELAY_MS, callback[1])
            self._unlock_after_release(hotkey_id, callback[2])

    def _unlock_after_release(self, hotkey_id: int, watched_keys: tuple[int, ...]) -> None:
        if hotkey_id not in self._locked_hotkeys:
            return
        if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in watched_keys):
            QTimer.singleShot(self._RELEASE_POLL_MS, lambda: self._unlock_after_release(hotkey_id, watched_keys))
            return
        self._locked_hotkeys.discard(hotkey_id)
