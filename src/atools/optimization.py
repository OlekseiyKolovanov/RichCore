from __future__ import annotations

import ctypes
import locale
import os
import platform
import re
import subprocess
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_INFORMATION = 0x0200
TH32CS_SNAPPROCESS = 0x00000002
HIGH_PRIORITY_CLASS = 0x00000080
NORMAL_PRIORITY_CLASS = 0x00000020

BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE_PERFORMANCE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"

GAME_MODE_KEY = r"Software\Microsoft\GameBar"
GAME_DVR_KEY = r"System\GameConfigStore"
APP_CAPTURE_KEY = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
GPU_PREF_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
APP_COMPAT_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
VISUAL_EFFECTS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
EXPLORER_ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
WINDOW_METRICS_KEY = r"Control Panel\Desktop\WindowMetrics"
POWER_THROTTLING_KEY = r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling"

GAME_MODE_NAMES = ("AllowAutoGameMode", "AutoGameModeEnabled")
GAME_DVR_NAMES = (
    (winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_Enabled", 0),
    (winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_FSEBehaviorMode", 2),
    (winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_HonorUserFSEBehaviorMode", 1),
    (winreg.HKEY_CURRENT_USER, APP_CAPTURE_KEY, "AppCaptureEnabled", 0),
)
COMPATIBILITY_FLAGS = ("DISABLEDXMAXIMIZEDWINDOWEDMODE", "HIGHDPIAWARE")


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetPriorityClass.argtypes = [wintypes.HANDLE]
kernel32.GetPriorityClass.restype = wintypes.DWORD
kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetPriorityClass.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL


@dataclass(slots=True)
class OptimizationState:
    key: str
    title: str
    description: str
    impact: str
    active: bool
    supported: bool
    detail: str
    requires_restart: bool = False


@dataclass(slots=True)
class OptimizationSnapshot:
    is_admin: bool
    windows_label: str
    ram_gb: int | None
    cpu_threads: int | None
    game_path: str
    game_path_exists: bool
    gta_running: bool
    gta_priority: str
    active_power_plan: str
    active_power_plan_guid: str | None
    items: list[OptimizationState]

    @property
    def enabled_count(self) -> int:
        return sum(1 for item in self.items if item.active)


@dataclass(slots=True)
class CommandOutput:
    returncode: int
    stdout: str
    stderr: str


class OptimizationManager:
    RECOMMENDED_KEYS = (
        "game_mode",
        "game_dvr",
        "power_throttling",
        "desktop_effects",
        "gpu_preference",
        "fullscreen_compat",
        "power_plan",
    )

    def __init__(self, game_path: str) -> None:
        self.set_game_path(game_path)

    def set_game_path(self, game_path: str) -> None:
        self._game_path_raw = game_path.strip()

    def snapshot(self) -> OptimizationSnapshot:
        active_plan_guid, active_plan_name = self._get_active_power_plan()
        gta_priority = self._running_gta_priority()
        items = [
            self._game_mode_state(),
            self._game_dvr_state(),
            self._power_throttling_state(),
            self._desktop_effects_state(),
            self._gpu_preference_state(),
            self._fullscreen_compat_state(),
            self._power_plan_state(active_plan_guid, active_plan_name),
        ]
        return OptimizationSnapshot(
            is_admin=self._is_admin(),
            windows_label=f"Windows {platform.release()} ({platform.version()})",
            ram_gb=self._total_ram_gb(),
            cpu_threads=os.cpu_count(),
            game_path=self._game_path_raw,
            game_path_exists=self.game_path_exists,
            gta_running=gta_priority != "Не запущено",
            gta_priority=gta_priority,
            active_power_plan=active_plan_name or "Невідомий план",
            active_power_plan_guid=active_plan_guid,
            items=items,
        )

    def apply(self, key: str) -> str:
        handlers = {
            "game_mode": self._apply_game_mode,
            "game_dvr": self._apply_game_dvr_disable,
            "power_throttling": self._apply_power_throttling,
            "desktop_effects": self._apply_desktop_effects,
            "gpu_preference": self._apply_gpu_preference,
            "fullscreen_compat": self._apply_fullscreen_compat,
            "power_plan": self._apply_power_plan,
        }
        if key not in handlers:
            raise KeyError(f"Unknown optimization key: {key}")
        return handlers[key]()

    def restore(self, key: str) -> str:
        handlers = {
            "game_mode": self._restore_game_mode,
            "game_dvr": self._restore_game_dvr,
            "power_throttling": self._restore_power_throttling,
            "desktop_effects": self._restore_desktop_effects,
            "gpu_preference": self._restore_gpu_preference,
            "fullscreen_compat": self._restore_fullscreen_compat,
            "power_plan": self._restore_power_plan,
        }
        if key not in handlers:
            raise KeyError(f"Unknown optimization key: {key}")
        return handlers[key]()

    def apply_recommended(self) -> list[str]:
        results: list[str] = []
        for key in self.RECOMMENDED_KEYS:
            try:
                results.append(self.apply(key))
            except Exception as exc:
                results.append(f"{self._title_for_key(key)}: {exc}")
        return results

    def restore_defaults(self) -> list[str]:
        results: list[str] = []
        for key in self.RECOMMENDED_KEYS:
            try:
                results.append(self.restore(key))
            except Exception as exc:
                results.append(f"{self._title_for_key(key)}: {exc}")
        return results

    def boost_running_gta_priority(self) -> str:
        process = self._find_game_process()
        if process is None:
            return "gta_sa.exe зараз не запущено, тож live-пріоритет підняти нема для чого."

        pid, image_name = process
        self._set_process_priority(pid, HIGH_PRIORITY_CLASS)
        return f"Пріоритет {image_name} піднято до High. Ефект діє до завершення гри."

    @property
    def game_path(self) -> Path:
        if not self._game_path_raw:
            return Path()
        return Path(os.path.expandvars(self._game_path_raw)).expanduser().resolve(strict=False)

    @property
    def game_path_exists(self) -> bool:
        path = self.game_path
        return bool(path) and path.exists() and path.is_file()

    def _title_for_key(self, key: str) -> str:
        for item in self.snapshot().items:
            if item.key == key:
                return item.title
        return key

    @staticmethod
    def _is_admin() -> bool:
        try:
            return bool(shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def _total_ram_gb() -> int | None:
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullTotalPhys / (1024 ** 3))

    def _game_mode_state(self) -> OptimizationState:
        values = [self._read_dword(winreg.HKEY_CURRENT_USER, GAME_MODE_KEY, name) for name in GAME_MODE_NAMES]
        active = any(value == 1 for value in values)
        detail = "Windows пріоритезує ігровий процес і трохи приглушує фонові задачі."
        return OptimizationState(
            key="game_mode",
            title="Windows Game Mode",
            description="Дає грі більше системного фокусу під час сесії.",
            impact="Середній вплив",
            active=active,
            supported=True,
            detail=detail,
        )

    def _game_dvr_state(self) -> OptimizationState:
        app_capture = self._read_dword(winreg.HKEY_CURRENT_USER, APP_CAPTURE_KEY, "AppCaptureEnabled")
        game_dvr = self._read_dword(winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_Enabled")
        active = app_capture == 0 and game_dvr == 0
        detail = "Вимикає фоновий запис, який часто забирає FPS і дає мікростатери."
        return OptimizationState(
            key="game_dvr",
            title="Xbox Game Bar / DVR Off",
            description="Прибирає захоплення екрана та оверлей Windows Xbox.",
            impact="Високий вплив",
            active=active,
            supported=True,
            detail=detail,
        )

    def _power_throttling_state(self) -> OptimizationState:
        value = self._read_dword(winreg.HKEY_LOCAL_MACHINE, POWER_THROTTLING_KEY, "PowerThrottlingOff")
        active = value == 1
        detail = "Вимикає системне приглушення фонових процесів Windows, щоб CPU не занижував частоти під час гри."
        return OptimizationState(
            key="power_throttling",
            title="Power Throttling Off",
            description="Прибирає агресивне енергозбереження Windows для стабільнішого frametime.",
            impact="Середній вплив",
            active=active,
            supported=True,
            detail=detail,
            requires_restart=True,
        )

    def _gpu_preference_state(self) -> OptimizationState:
        if not self.game_path_exists:
            return OptimizationState(
                key="gpu_preference",
                title="High Performance GPU",
                description="Прив'язує gta_sa.exe до високопродуктивного GPU-профілю Windows.",
                impact="Високий вплив",
                active=False,
                supported=False,
                detail="Спочатку вкажи коректний шлях до gta_sa.exe у вкладці налаштувань.",
                requires_restart=True,
            )

        raw = self._read_string(winreg.HKEY_CURRENT_USER, GPU_PREF_KEY, str(self.game_path))
        active = bool(raw and re.search(r"GpuPreference\s*=\s*2\b", raw, re.IGNORECASE))
        detail = "Корисно для ноутбуків і ПК з кількома GPU, щоб GTA не стартувала на слабшому адаптері."
        return OptimizationState(
            key="gpu_preference",
            title="High Performance GPU",
            description="Прив'язує gta_sa.exe до високопродуктивного GPU-профілю Windows.",
            impact="Високий вплив",
            active=active,
            supported=True,
            detail=detail,
            requires_restart=True,
        )

    def _desktop_effects_state(self) -> OptimizationState:
        visual_fx = self._read_dword(winreg.HKEY_CURRENT_USER, VISUAL_EFFECTS_KEY, "VisualFXSetting")
        transparency = self._read_dword(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY, "EnableTransparency")
        taskbar_animations = self._read_dword(winreg.HKEY_CURRENT_USER, EXPLORER_ADVANCED_KEY, "TaskbarAnimations")
        min_animate = self._read_string(winreg.HKEY_CURRENT_USER, WINDOW_METRICS_KEY, "MinAnimate")
        active = visual_fx == 2 and transparency == 0 and taskbar_animations == 0 and min_animate == "0"
        detail = "Прибирає анімації та прозорість Windows, щоб менше ресурсів ішло в оболонку під час гри."
        return OptimizationState(
            key="desktop_effects",
            title="Desktop Effects Trim",
            description="Зменшує навантаження від анімацій і transparency у самій Windows.",
            impact="Середній вплив",
            active=active,
            supported=True,
            detail=detail,
            requires_restart=True,
        )

    def _fullscreen_compat_state(self) -> OptimizationState:
        if not self.game_path_exists:
            return OptimizationState(
                key="fullscreen_compat",
                title="Fullscreen & DPI Tweak",
                description="Вимикає fullscreen optimizations і фіксує DPI-поведінку для GTA.",
                impact="Середній вплив",
                active=False,
                supported=False,
                detail="Потрібен робочий шлях до gta_sa.exe, інакше Windows не збереже сумісність для гри.",
                requires_restart=True,
            )

        raw = self._read_string(winreg.HKEY_CURRENT_USER, APP_COMPAT_KEY, str(self.game_path)) or ""
        tokens = {token.upper() for token in raw.replace("~", " ").split()}
        active = all(flag in tokens for flag in COMPATIBILITY_FLAGS)
        detail = "Часто прибирає нестабільний frametime у старих іграх на Windows 10/11."
        return OptimizationState(
            key="fullscreen_compat",
            title="Fullscreen & DPI Tweak",
            description="Вимикає fullscreen optimizations і фіксує DPI-поведінку для GTA.",
            impact="Середній вплив",
            active=active,
            supported=True,
            detail=detail,
            requires_restart=True,
        )

    def _power_plan_state(self, active_guid: str | None, active_name: str) -> OptimizationState:
        active = self._is_performance_plan(active_guid, active_name)
        detail = "Перемикає Windows на продуктивний енергоплан, щоб CPU не скидав частоти під навантаженням."
        return OptimizationState(
            key="power_plan",
            title="Performance Power Plan",
            description="Активує High Performance або Ultimate Performance.",
            impact="Високий вплив",
            active=active,
            supported=True,
            detail=detail if active_name else "Не вдалося визначити активний енергоплан Windows.",
        )

    def _apply_game_mode(self) -> str:
        for name in GAME_MODE_NAMES:
            self._write_dword(winreg.HKEY_CURRENT_USER, GAME_MODE_KEY, name, 1)
        return "Windows Game Mode увімкнено."

    def _restore_game_mode(self) -> str:
        for name in GAME_MODE_NAMES:
            self._write_dword(winreg.HKEY_CURRENT_USER, GAME_MODE_KEY, name, 0)
        return "Windows Game Mode повернуто до стандартного вимкненого стану."

    def _apply_game_dvr_disable(self) -> str:
        for root, key, name, value in GAME_DVR_NAMES:
            self._write_dword(root, key, name, value)
        return "Xbox Game Bar / DVR вимкнено для зменшення фонового захоплення."

    def _restore_game_dvr(self) -> str:
        self._write_dword(winreg.HKEY_CURRENT_USER, APP_CAPTURE_KEY, "AppCaptureEnabled", 1)
        self._write_dword(winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_Enabled", 1)
        self._delete_value(winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_FSEBehaviorMode")
        self._delete_value(winreg.HKEY_CURRENT_USER, GAME_DVR_KEY, "GameDVR_HonorUserFSEBehaviorMode")
        return "Xbox Game Bar / DVR повернуто до стандартної конфігурації."

    def _apply_power_throttling(self) -> str:
        self._write_dword(winreg.HKEY_LOCAL_MACHINE, POWER_THROTTLING_KEY, "PowerThrottlingOff", 1)
        return "Windows Power Throttling вимкнено. Зміна застосовується без редагування файлів гри."

    def _restore_power_throttling(self) -> str:
        self._delete_value(winreg.HKEY_LOCAL_MACHINE, POWER_THROTTLING_KEY, "PowerThrottlingOff")
        return "Windows Power Throttling повернуто до стандартної поведінки."

    def _apply_desktop_effects(self) -> str:
        self._write_dword(winreg.HKEY_CURRENT_USER, VISUAL_EFFECTS_KEY, "VisualFXSetting", 2)
        self._write_dword(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY, "EnableTransparency", 0)
        self._write_dword(winreg.HKEY_CURRENT_USER, EXPLORER_ADVANCED_KEY, "TaskbarAnimations", 0)
        self._write_string(winreg.HKEY_CURRENT_USER, WINDOW_METRICS_KEY, "MinAnimate", "0")
        return "Візуальні ефекти Windows зменшено до продуктивного режиму."

    def _restore_desktop_effects(self) -> str:
        self._write_dword(winreg.HKEY_CURRENT_USER, VISUAL_EFFECTS_KEY, "VisualFXSetting", 0)
        self._write_dword(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY, "EnableTransparency", 1)
        self._write_dword(winreg.HKEY_CURRENT_USER, EXPLORER_ADVANCED_KEY, "TaskbarAnimations", 1)
        self._write_string(winreg.HKEY_CURRENT_USER, WINDOW_METRICS_KEY, "MinAnimate", "1")
        return "Візуальні ефекти Windows повернуто до стандартного режиму."

    def _apply_gpu_preference(self) -> str:
        if not self.game_path_exists:
            raise FileNotFoundError("Не знайдено gta_sa.exe для запису GPU-профілю.")

        raw = self._read_string(winreg.HKEY_CURRENT_USER, GPU_PREF_KEY, str(self.game_path))
        updated = self._set_gpu_preference(raw, "2")
        self._write_string(winreg.HKEY_CURRENT_USER, GPU_PREF_KEY, str(self.game_path), updated)
        return "Для gta_sa.exe увімкнено High Performance GPU профіль."

    def _restore_gpu_preference(self) -> str:
        if not self._game_path_raw:
            return "Шлях до gta_sa.exe не задано, GPU-профіль не змінювався."

        raw = self._read_string(winreg.HKEY_CURRENT_USER, GPU_PREF_KEY, str(self.game_path))
        cleaned = self._remove_gpu_preference(raw)
        if cleaned:
            self._write_string(winreg.HKEY_CURRENT_USER, GPU_PREF_KEY, str(self.game_path), cleaned)
        else:
            self._delete_value(winreg.HKEY_CURRENT_USER, GPU_PREF_KEY, str(self.game_path))
        return "GPU-перевагу для gta_sa.exe скинуто до стандартної поведінки Windows."

    def _apply_fullscreen_compat(self) -> str:
        if not self.game_path_exists:
            raise FileNotFoundError("Не знайдено gta_sa.exe для compat-твіка.")

        raw = self._read_string(winreg.HKEY_CURRENT_USER, APP_COMPAT_KEY, str(self.game_path))
        updated = self._merge_compatibility_flags(raw, COMPATIBILITY_FLAGS)
        self._write_string(winreg.HKEY_CURRENT_USER, APP_COMPAT_KEY, str(self.game_path), updated)
        return "Для gta_sa.exe вимкнено fullscreen optimizations і додано DPI-твік."

    def _restore_fullscreen_compat(self) -> str:
        if not self._game_path_raw:
            return "Шлях до gta_sa.exe не задано, compat-налаштування не змінювались."

        raw = self._read_string(winreg.HKEY_CURRENT_USER, APP_COMPAT_KEY, str(self.game_path))
        cleaned = self._remove_compatibility_flags(raw, COMPATIBILITY_FLAGS)
        if cleaned:
            self._write_string(winreg.HKEY_CURRENT_USER, APP_COMPAT_KEY, str(self.game_path), cleaned)
        else:
            self._delete_value(winreg.HKEY_CURRENT_USER, APP_COMPAT_KEY, str(self.game_path))
        return "Сумісність gta_sa.exe повернуто до базового стану."

    def _apply_power_plan(self) -> str:
        for target_guid in (ULTIMATE_PERFORMANCE_GUID, HIGH_PERFORMANCE_GUID):
            if self._try_set_power_plan(target_guid):
                _, plan_name = self._get_active_power_plan()
                return f"Активовано продуктивний енергоплан: {plan_name or target_guid}."

        duplicated_guid = self._duplicate_power_scheme(ULTIMATE_PERFORMANCE_GUID)
        if duplicated_guid and self._try_set_power_plan(duplicated_guid):
            _, plan_name = self._get_active_power_plan()
            return f"Створено й активовано Ultimate Performance: {plan_name or duplicated_guid}."

        raise RuntimeError("Не вдалося активувати продуктивний енергоплан через powercfg.")

    def _restore_power_plan(self) -> str:
        if not self._try_set_power_plan(BALANCED_GUID):
            raise RuntimeError("Не вдалося повернути Balanced power plan.")
        _, plan_name = self._get_active_power_plan()
        return f"Повернуто стандартний енергоплан: {plan_name or BALANCED_GUID}."

    def _get_active_power_plan(self) -> tuple[str | None, str]:
        result = self._run_command("powercfg", "/getactivescheme")
        if result.returncode != 0:
            return None, ""
        combined = f"{result.stdout}\n{result.stderr}"
        guid = self._extract_guid(combined)
        name_match = re.search(r"\(([^)]+)\)", combined)
        return guid, name_match.group(1).strip() if name_match else combined.strip()

    def _duplicate_power_scheme(self, base_guid: str) -> str | None:
        result = self._run_command("powercfg", "-duplicatescheme", base_guid)
        if result.returncode != 0:
            return None
        return self._extract_guid(f"{result.stdout}\n{result.stderr}")

    def _try_set_power_plan(self, guid: str) -> bool:
        result = self._run_command("powercfg", "/setactive", guid)
        return result.returncode == 0

    @staticmethod
    def _is_performance_plan(guid: str | None, name: str) -> bool:
        if guid and guid.lower() in {HIGH_PERFORMANCE_GUID, ULTIMATE_PERFORMANCE_GUID}:
            return True
        lowered = name.casefold()
        hints = ("ultimate", "high performance", "висока", "максимальна", "максимальной", "максим")
        return any(hint in lowered for hint in hints)

    def _find_game_process(self) -> tuple[int, str] | None:
        image_name = (self.game_path.name or "gta_sa.exe").casefold()
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            return None

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        try:
            has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                if entry.szExeFile.casefold() == image_name:
                    return entry.th32ProcessID, entry.szExeFile
                has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return None

    def _running_gta_priority(self) -> str:
        process = self._find_game_process()
        if process is None:
            return "Не запущено"
        pid, _image_name = process
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return "Запущено"
        try:
            priority = kernel32.GetPriorityClass(handle)
        finally:
            kernel32.CloseHandle(handle)
        return self._priority_name(priority)

    def _set_process_priority(self, pid: int, priority_class: int) -> None:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_INFORMATION, False, pid)
        if not handle:
            raise RuntimeError(f"Не вдалося відкрити процес GTA (pid={pid}).")
        try:
            if not kernel32.SetPriorityClass(handle, priority_class):
                raise RuntimeError("SetPriorityClass завершився з помилкою.")
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _priority_name(priority: int) -> str:
        mapping = {
            HIGH_PRIORITY_CLASS: "High",
            NORMAL_PRIORITY_CLASS: "Normal",
            0x00004000: "Below Normal",
            0x00008000: "Above Normal",
            0x00000040: "Idle",
            0x00000100: "Realtime",
        }
        return mapping.get(priority, "Запущено")

    @staticmethod
    def _run_command(*args: str) -> CommandOutput:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=False,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return CommandOutput(
            returncode=result.returncode,
            stdout=OptimizationManager._decode_command_output(result.stdout),
            stderr=OptimizationManager._decode_command_output(result.stderr),
        )

    @staticmethod
    def _decode_command_output(payload: bytes) -> str:
        if not payload:
            return ""

        preferred = locale.getpreferredencoding(False)
        tried: list[str] = []
        for encoding in ("utf-8", "utf-8-sig", "cp866", "cp1251", preferred):
            if not encoding or encoding in tried:
                continue
            tried.append(encoding)
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode(preferred or "utf-8", errors="replace")

    @staticmethod
    def _extract_guid(text: str) -> str | None:
        match = re.search(r"([a-fA-F0-9-]{36})", text)
        return match.group(1).lower() if match else None

    @staticmethod
    def _read_dword(root: int, subkey: str, value_name: str) -> int | None:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
        except FileNotFoundError:
            return None
        return int(value)

    @staticmethod
    def _read_string(root: int, subkey: str, value_name: str) -> str | None:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
        except FileNotFoundError:
            return None
        return str(value)

    @staticmethod
    def _write_dword(root: int, subkey: str, value_name: str, value: int) -> None:
        with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, int(value))

    @staticmethod
    def _write_string(root: int, subkey: str, value_name: str, value: str) -> None:
        with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value)

    @staticmethod
    def _delete_value(root: int, subkey: str, value_name: str) -> None:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, value_name)
        except FileNotFoundError:
            return

    @staticmethod
    def _set_gpu_preference(raw: str | None, value: str) -> str:
        parts = [part.strip() for part in (raw or "").split(";") if part.strip()]
        parts = [part for part in parts if not part.casefold().startswith("gpupreference=")]
        parts.append(f"GpuPreference={value}")
        return ";".join(parts) + ";"

    @staticmethod
    def _remove_gpu_preference(raw: str | None) -> str:
        parts = [part.strip() for part in (raw or "").split(";") if part.strip()]
        parts = [part for part in parts if not part.casefold().startswith("gpupreference=")]
        if not parts:
            return ""
        return ";".join(parts) + ";"

    @staticmethod
    def _merge_compatibility_flags(raw: str | None, flags: tuple[str, ...]) -> str:
        tokens = [token.upper() for token in (raw or "").replace("~", " ").split() if token.strip()]
        merged = list(dict.fromkeys([*tokens, *flags]))
        return "~ " + " ".join(merged)

    @staticmethod
    def _remove_compatibility_flags(raw: str | None, flags: tuple[str, ...]) -> str:
        if not raw:
            return ""
        remove_set = {flag.upper() for flag in flags}
        kept = [token.upper() for token in raw.replace("~", " ").split() if token.strip().upper() not in remove_set]
        if not kept:
            return ""
        return "~ " + " ".join(kept)
