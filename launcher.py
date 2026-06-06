from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _is_windows_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> None:
    if os.name != "nt" or _is_windows_admin():
        return

    import ctypes

    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = subprocess.list2cmdline(sys.argv[1:])
    else:
        executable = sys.executable
        parameters = subprocess.list2cmdline([str(Path(__file__).resolve()), *sys.argv[1:]])

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        str(Path(__file__).resolve().parent),
        1,
    )
    if int(result) <= 32:
        raise SystemExit("RichCore needs administrator permissions to start.")
    raise SystemExit(0)


_relaunch_as_admin()

if sys.version_info < (3, 14):
    # Try to re-launch with Python 3.14 automatically if available.
    python_launcher = "py"
    try:
        result = subprocess.run(
            [python_launcher, "-3.14", __file__] + sys.argv[1:],
            check=False,
        )
        raise SystemExit(result.returncode)
    except FileNotFoundError:
        raise SystemExit(
            "RichCore V12 requires Python 3.14 to run this build.\n"
            "Install Python 3.14 or run with 'py -3.14 launcher.py'."
        )

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atools.main import run


if __name__ == "__main__":
    raise SystemExit(run())
