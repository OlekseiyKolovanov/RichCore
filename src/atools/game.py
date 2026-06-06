from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from pathlib import Path


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_BACK = 0x08
VK_A = 0x41
VK_C = 0x43
VK_END = 0x23
VK_F8 = 0x77
VK_F6 = 0x75
VK_T = 0x54
VK_V = 0x56
VK_LWIN = 0x5B
VK_RWIN = 0x5C

KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

SW_RESTORE = 9
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HGLOBAL]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.argtypes = []
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class BackgroundSender:
    _ACTIVATE_DELAY_S = 0.024
    _CHAT_SETTLE_DELAY_S = 0.028
    _PASTE_SETTLE_DELAY_S = 0.012
    _BACKGROUND_CHAT_DELAY_S = 0.028
    _BACKGROUND_PASTE_SETTLE_DELAY_S = 0.04
    _BACKGROUND_SUBMIT_DELAY_S = 0.03
    _BACKGROUND_COPY_SETTLE_DELAY_S = 0.08
    _BACKGROUND_REPLY_SUBMIT_SETTLE_DELAY_S = 0.12
    _RESTORE_FOCUS_DELAY_S = 0.015
    _PASTE_RETRY_DELAY_S = 0.018
    _UI_DISMISS_DELAY_S = 0.02
    _HOTKEY_RELEASE_TIMEOUT_S = 0.42
    _FOREGROUND_WINDOW_TIMEOUT_S = 0.18
    _FOREGROUND_REINFORCE_DELAY_S = 0.012
    _CONSOLE_INJECT_OPEN_DELAY_S = 0.10
    _CONSOLE_INJECT_CHAR_DELAY_S = 0.001
    _CONSOLE_INJECT_SUBMIT_DELAY_S = 0.05

    def __init__(self, game_path: str) -> None:
        self._logger = logging.getLogger(__name__)
        self._game_path = game_path
        self._cached_pid: int | None = None
        self._cached_hwnd: int | None = None
        self._send_lock = threading.Lock()

    def set_game_path(self, game_path: str) -> None:
        self._game_path = game_path
        self._cached_pid = None
        self._cached_hwnd = None

    def activate_game_window(self) -> None:
        """Активирует окно игры (выводит на передний план)."""
        hwnd = self.find_game_window()
        self._activate_window(hwnd)

    def find_game_window(self) -> int:
        image_name = Path(self._game_path).name or "gta_sa.exe"

        if self._cached_hwnd and user32.IsWindow(self._cached_hwnd):
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(self._cached_hwnd, ctypes.byref(process_id))
            if process_id.value == self._cached_pid and user32.IsWindowVisible(self._cached_hwnd):
                return self._cached_hwnd

        pid = self._cached_pid
        if pid is not None:
            hwnd = self._find_window_by_pid(pid)
            if hwnd is not None:
                self._cached_hwnd = hwnd
                return hwnd

        pid = self._find_pid(image_name)
        if pid is None:
            self._cached_pid = None
            self._cached_hwnd = None
            raise RuntimeError(f"Процес гри не знайдено: {image_name}")

        hwnd = self._find_window_by_pid(pid)
        if hwnd is None:
            self._cached_pid = None
            self._cached_hwnd = None
            raise RuntimeError("Вікно гри не знайдено")

        self._cached_pid = pid
        self._cached_hwnd = hwnd
        return hwnd

    def send_background_command(
        self,
        command: str,
        *,
        open_chat: bool = True,
        submit: bool = True,
    ) -> None:
        """Надсилає текст у MTA без активації вікна гри."""
        with self._send_lock:
            self._send_background_text(command, open_chat=open_chat, submit=submit)

    def send_chat_command(
        self,
        command: str,
        *,
        open_chat: bool = True,
        submit: bool = False,
        activate_window: bool = True,
        restore_focus: bool = False,
        dismiss_ui: bool = False,
        clear_first: bool = True,
        reinforce_paste: bool = False,
    ) -> None:
        """Надсилає текст у гру через foreground paste."""
        with self._send_lock:
            self._send_foreground_text(
                command,
                open_chat=open_chat,
                submit=submit,
                activate_window=activate_window,
                restore_focus=restore_focus,
                dismiss_ui=dismiss_ui,
                clear_first=clear_first,
                reinforce_paste=reinforce_paste,
            )

    def send_ahk_text(
        self,
        text: str,
        *,
        open_chat: bool = True,
        submit: bool = False,
        dismiss_ui: bool = False,
    ) -> None:
        """Швидке вставлення для біндів через clipboard + Ctrl+V."""
        with self._send_lock:
            self._send_foreground_text(
                text,
                open_chat=open_chat,
                submit=submit,
                activate_window=True,
                restore_focus=False,
                dismiss_ui=dismiss_ui,
                clear_first=open_chat,
                reinforce_paste=False,
            )

    def send_reply_command(
        self,
        command: str,
        *,
        open_chat: bool = True,
        submit: bool = True,
        dismiss_ui: bool = False,
    ) -> None:
        """Надсилає команду через MTA console inject без активації вікна гри."""
        with self._send_lock:
            self._wait_for_hotkey_release(self._HOTKEY_RELEASE_TIMEOUT_S)
            self._release_sticky_modifiers()
            self._send_reply_background_text(
                command,
                open_chat=open_chat,
                submit=submit,
                dismiss_ui=dismiss_ui,
            )

    def preview_paste_cycle(self, text: str, *, activate_window: bool = True) -> None:
        """Відкриває чат, вставляє текст і закриває його без відправки."""
        with self._send_lock:
            hwnd = self.find_game_window()
            if activate_window:
                self._activate_window(hwnd)
                self._wait_for_foreground_window(hwnd, self._FOREGROUND_WINDOW_TIMEOUT_S)
            self._wait_for_hotkey_release(self._HOTKEY_RELEASE_TIMEOUT_S)
            self._release_sticky_modifiers()
            self._open_chat_foreground()
            self._insert_text_foreground(hwnd, text, clear_first=True, reinforce_paste=True)
            time.sleep(self._PASTE_SETTLE_DELAY_S)
            self._tap_vk(VK_ESCAPE)
            time.sleep(0.008)
            self._tap_vk(VK_ESCAPE)

    def _send_background_text(
        self,
        text: str,
        *,
        open_chat: bool,
        submit: bool,
        dismiss_ui: bool = False,
        clear_first: bool = False,
        reinforce_paste: bool = False,
        submit_settle_delay: float | None = None,
    ) -> None:
        hwnd = self.find_game_window()

        if dismiss_ui:
            self._dismiss_in_game_ui_background(hwnd)

        if open_chat:
            self._open_chat_background(hwnd)

        if text:
            self._insert_text_background(
                hwnd,
                text,
                clear_first=clear_first,
                reinforce_paste=reinforce_paste,
            )

        if submit:
            time.sleep(
                self._BACKGROUND_PASTE_SETTLE_DELAY_S
                if submit_settle_delay is None
                else submit_settle_delay
            )
            self._submit_background(hwnd)

    def _send_reply_background_text(
        self,
        text: str,
        *,
        open_chat: bool,
        submit: bool,
        dismiss_ui: bool = False,
    ) -> None:
        hwnd = self.find_game_window()
        command = self._normalize_console_command(text)

        if dismiss_ui:
            self._dismiss_in_game_ui_background(hwnd)

        if open_chat:
            # Keep the reply path synchronous so the console does not linger on
            # screen while we inject the command.
            self._send_window_vk(hwnd, VK_F8)

        if command:
            if not self._paste_text_background(
                hwnd,
                command,
                clear_first=False,
                reinforce_paste=False,
            ):
                raise RuntimeError("Не вдалося вставити текст у MTA console inject")

        if submit:
            self._send_window_vk(hwnd, VK_RETURN)

        if open_chat:
            self._send_window_vk(hwnd, VK_F8)

    def _send_foreground_text(
        self,
        text: str,
        *,
        open_chat: bool,
        submit: bool,
        activate_window: bool,
        restore_focus: bool,
        dismiss_ui: bool,
        clear_first: bool,
        reinforce_paste: bool,
    ) -> None:
        hwnd = self.find_game_window()
        previous_hwnd = user32.GetForegroundWindow() if restore_focus else 0
        if activate_window and user32.GetForegroundWindow() != hwnd:
            self._activate_window(hwnd)
            self._wait_for_foreground_window(hwnd, self._FOREGROUND_WINDOW_TIMEOUT_S)
        self._wait_for_hotkey_release(self._HOTKEY_RELEASE_TIMEOUT_S)
        self._release_sticky_modifiers()

        if dismiss_ui:
            self._dismiss_in_game_ui_foreground()

        if open_chat:
            self._open_chat_foreground()
        elif text and not clear_first:
            self._tap_vk(VK_END)
            time.sleep(self._FOREGROUND_REINFORCE_DELAY_S)

        if text:
            self._insert_text_foreground(
                hwnd,
                text,
                clear_first=clear_first,
                reinforce_paste=reinforce_paste,
            )
        if submit:
            time.sleep(self._PASTE_SETTLE_DELAY_S)
            self._tap_vk(VK_RETURN)
        if previous_hwnd and previous_hwnd != hwnd and user32.IsWindow(previous_hwnd):
            time.sleep(self._RESTORE_FOCUS_DELAY_S)
            self._restore_window(previous_hwnd)

    def _insert_text_foreground(
        self,
        hwnd: int,
        text: str,
        *,
        clear_first: bool,
        reinforce_paste: bool,
    ) -> None:
        if not self._paste_text_foreground(
            text,
            clear_first=clear_first,
            reinforce_paste=reinforce_paste,
        ):
            if clear_first:
                self._clear_chat_input_foreground()
                time.sleep(self._PASTE_RETRY_DELAY_S)
            self._send_text_internal(hwnd, text)

    def _insert_text_background(
        self,
        hwnd: int,
        text: str,
        *,
        clear_first: bool,
        reinforce_paste: bool,
    ) -> None:
        if not self._paste_text_background(
            hwnd,
            text,
            clear_first=clear_first,
            reinforce_paste=reinforce_paste,
        ):
            if clear_first:
                self._clear_chat_input_background(hwnd)
                time.sleep(self._PASTE_RETRY_DELAY_S)
            self._send_text_internal(hwnd, text)

    def _insert_verified_reply_background(
        self,
        hwnd: int,
        text: str,
        *,
        clear_first: bool,
        max_attempts: int,
    ) -> None:
        for _ in range(max_attempts):
            self._insert_text_background(
                hwnd,
                text,
                clear_first=clear_first,
                reinforce_paste=False,
            )
            if self._capture_chat_text_background(hwnd) == text:
                return
            time.sleep(self._PASTE_RETRY_DELAY_S)
        self._logger.warning("Reply verification did not confirm chat text; using best-effort background insert")
        self._insert_text_background(
            hwnd,
            text,
            clear_first=clear_first,
            reinforce_paste=False,
        )

    def _activate_window(self, hwnd: int) -> None:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        time.sleep(self._ACTIVATE_DELAY_S)

    def _restore_window(self, hwnd: int) -> None:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

    def _open_chat_background(self, hwnd: int) -> None:
        self._send_window_vk(hwnd, VK_T)
        time.sleep(self._BACKGROUND_CHAT_DELAY_S)

    def _open_chat_foreground(self) -> None:
        self._tap_vk(VK_T)
        time.sleep(self._CHAT_SETTLE_DELAY_S)

    def _dismiss_in_game_ui_background(self, hwnd: int) -> None:
        self._send_window_vk(hwnd, VK_ESCAPE)
        time.sleep(self._UI_DISMISS_DELAY_S)
        self._send_window_vk(hwnd, VK_ESCAPE)
        time.sleep(self._UI_DISMISS_DELAY_S)

    def _dismiss_in_game_ui_foreground(self) -> None:
        self._tap_vk(VK_ESCAPE)
        time.sleep(self._UI_DISMISS_DELAY_S)
        self._tap_vk(VK_ESCAPE)
        time.sleep(self._UI_DISMISS_DELAY_S)

    def _send_text_internal(self, hwnd: int, text: str) -> None:
        for index, char in enumerate(text):
            user32.SendMessageW(hwnd, WM_CHAR, ord(char), 1)
            if index and index % 160 == 0:
                time.sleep(0.0004)

    def _send_reply_text_internal(self, hwnd: int, text: str) -> None:
        for char in text:
            user32.PostMessageW(hwnd, WM_CHAR, ord(char), 0)
            time.sleep(self._CONSOLE_INJECT_CHAR_DELAY_S)

    @staticmethod
    def _normalize_console_command(command: str) -> str:
        normalized = command.strip()
        if normalized.startswith("/"):
            return normalized[1:]
        return normalized

    def _paste_text_foreground(
        self,
        text: str,
        *,
        clear_first: bool = False,
        reinforce_paste: bool = False,
    ) -> bool:
        if not text:
            return True
        if clear_first:
            self._clear_chat_input_foreground()
            time.sleep(self._PASTE_RETRY_DELAY_S)
        if not self._set_clipboard_text(text):
            return False
        self._tap_ctrl_v()
        time.sleep(self._PASTE_SETTLE_DELAY_S)
        if reinforce_paste:
            self._tap_ctrl_a()
            time.sleep(self._FOREGROUND_REINFORCE_DELAY_S)
            self._tap_ctrl_v()
            time.sleep(self._PASTE_SETTLE_DELAY_S)
            self._tap_vk(VK_END)
            time.sleep(self._FOREGROUND_REINFORCE_DELAY_S)
        return True

    def _paste_text_background(
        self,
        hwnd: int,
        text: str,
        *,
        clear_first: bool = False,
        reinforce_paste: bool = False,
    ) -> bool:
        if not text:
            return True
        if not self._set_clipboard_text(text):
            return False
        time.sleep(self._PASTE_RETRY_DELAY_S)
        if clear_first:
            self._clear_chat_input_background(hwnd)
            time.sleep(self._PASTE_RETRY_DELAY_S)
        self._send_window_key_down(hwnd, VK_CONTROL)
        self._send_window_vk(hwnd, VK_V)
        self._send_window_key_up(hwnd, VK_CONTROL)
        time.sleep(self._BACKGROUND_PASTE_SETTLE_DELAY_S)
        if reinforce_paste:
            self._send_window_key_down(hwnd, VK_CONTROL)
            self._send_window_vk(hwnd, VK_A)
            self._send_window_key_up(hwnd, VK_CONTROL)
            time.sleep(self._PASTE_RETRY_DELAY_S)
            self._send_window_key_down(hwnd, VK_CONTROL)
            self._send_window_vk(hwnd, VK_V)
            self._send_window_key_up(hwnd, VK_CONTROL)
            time.sleep(self._BACKGROUND_PASTE_SETTLE_DELAY_S)
        return True

    def _submit_background(self, hwnd: int) -> None:
        self._send_window_vk(hwnd, VK_RETURN)
        time.sleep(self._BACKGROUND_SUBMIT_DELAY_S)

    @staticmethod
    def _tap_vk(vk: int) -> None:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.004)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.002)

    @staticmethod
    def _tap_ctrl_a() -> None:
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.003)
        user32.keybd_event(VK_A, 0, 0, 0)
        time.sleep(0.004)
        user32.keybd_event(VK_A, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.002)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _tap_ctrl_v() -> None:
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.003)
        user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.004)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.002)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    @classmethod
    def _clear_chat_input_foreground(cls) -> None:
        cls._tap_ctrl_a()
        time.sleep(0.004)
        cls._tap_vk(VK_BACK)

    @classmethod
    def _clear_chat_input_background(cls, hwnd: int) -> None:
        cls._send_window_key_down(hwnd, VK_CONTROL)
        cls._send_window_vk(hwnd, VK_A)
        cls._send_window_key_up(hwnd, VK_CONTROL)
        time.sleep(0.01)
        cls._send_window_vk(hwnd, VK_BACK)

    def _capture_chat_text_background(self, hwnd: int) -> str:
        self._send_window_key_down(hwnd, VK_CONTROL)
        self._send_window_vk(hwnd, VK_A)
        self._send_window_key_up(hwnd, VK_CONTROL)
        time.sleep(self._PASTE_RETRY_DELAY_S)
        self._send_window_key_down(hwnd, VK_CONTROL)
        self._send_window_vk(hwnd, VK_C)
        self._send_window_key_up(hwnd, VK_CONTROL)
        time.sleep(self._BACKGROUND_COPY_SETTLE_DELAY_S)
        captured = self._read_clipboard_text()
        self._send_window_vk(hwnd, VK_END)
        time.sleep(self._PASTE_RETRY_DELAY_S)
        return captured

    @staticmethod
    def _release_sticky_modifiers() -> None:
        for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.001)

    @staticmethod
    def _wait_for_foreground_window(hwnd: int, timeout_s: float = 0.18) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if user32.GetForegroundWindow() == hwnd:
                return True
            time.sleep(0.004)
        return user32.GetForegroundWindow() == hwnd

    @staticmethod
    def _wait_for_hotkey_release(timeout_s: float = 0.25) -> None:
        watched_keys = (
            VK_SHIFT,
            VK_CONTROL,
            VK_MENU,
            VK_LWIN,
            VK_RWIN,
            *range(0x30, 0x3A),
            *range(0x41, 0x5B),
            *range(0x60, 0x70),
            *range(0x70, 0x88),
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in watched_keys):
                return
            time.sleep(0.003)

    @staticmethod
    def _set_clipboard_text(text: str) -> bool:
        previous_sequence = user32.GetClipboardSequenceNumber()
        for _ in range(18):
            if user32.OpenClipboard(None):
                handle = None
                try:
                    user32.EmptyClipboard()
                    payload = text + "\0"
                    buffer = ctypes.create_unicode_buffer(payload)
                    size = ctypes.sizeof(buffer)
                    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                    if not handle:
                        return False
                    pointer = kernel32.GlobalLock(handle)
                    if not pointer:
                        kernel32.GlobalFree(handle)
                        return False
                    ctypes.memmove(pointer, ctypes.addressof(buffer), size)
                    kernel32.GlobalUnlock(handle)
                    if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                        kernel32.GlobalFree(handle)
                        return False
                    handle = None
                    break
                finally:
                    user32.CloseClipboard()
                    if handle:
                        kernel32.GlobalFree(handle)
            time.sleep(0.004)
        else:
            return False

        deadline = time.monotonic() + 0.12
        while time.monotonic() < deadline:
            if user32.GetClipboardSequenceNumber() != previous_sequence:
                return True
            time.sleep(0.002)
        return True

    @staticmethod
    def _read_clipboard_text() -> str:
        for _ in range(18):
            if user32.OpenClipboard(None):
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        return ""
                    pointer = kernel32.GlobalLock(handle)
                    if not pointer:
                        return ""
                    try:
                        return ctypes.wstring_at(pointer).rstrip("\0")
                    finally:
                        kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
            time.sleep(0.004)
        return ""

    @staticmethod
    def _send_window_key_down(hwnd: int, vk: int) -> None:
        lparam = BackgroundSender._build_key_lparam(vk)
        user32.SendMessageW(hwnd, WM_KEYDOWN, vk, lparam)

    @staticmethod
    def _send_window_key_up(hwnd: int, vk: int) -> None:
        lparam = BackgroundSender._build_key_lparam(vk, key_up=True)
        user32.SendMessageW(hwnd, WM_KEYUP, vk, lparam)

    @staticmethod
    def _send_window_vk(hwnd: int, vk: int) -> None:
        BackgroundSender._send_window_key_down(hwnd, vk)
        BackgroundSender._send_window_key_up(hwnd, vk)

    @staticmethod
    def _post_window_vk(hwnd: int, vk: int) -> None:
        lparam = BackgroundSender._build_key_lparam(vk)
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam)
        time.sleep(0.01)
        user32.PostMessageW(hwnd, WM_KEYUP, vk, BackgroundSender._build_key_lparam(vk, key_up=True))

    @staticmethod
    def _build_key_lparam(vk: int, *, key_up: bool = False) -> int:
        scan_code = user32.MapVirtualKeyW(vk, 0) & 0xFF
        lparam = 1 | (scan_code << 16)
        if key_up:
            lparam |= 1 << 30
            lparam |= 1 << 31
        return lparam

    @staticmethod
    def _find_window_by_pid(pid: int) -> int | None:
        result: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_windows(hwnd, _lparam):
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if process_id.value == pid and user32.IsWindowVisible(hwnd):
                result.append(hwnd)
                return False
            return True

        user32.EnumWindows(enum_windows, 0)
        return result[0] if result else None

    @staticmethod
    def _find_pid(image_name: str) -> int | None:
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == -1:
            return None

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        try:
            has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                if entry.szExeFile.casefold() == image_name.casefold():
                    return int(entry.th32ProcessID)
                has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return None
