"""Workspace launcher used to run MotionForge under the pinned Python runtime."""
from pathlib import Path
import subprocess
import sys
import ctypes


def main() -> int:
    executable = Path(sys.executable).resolve()
    project_root = executable.parents[2]
    pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.is_file():
        pythonw = project_root.parent.parent / ".venv" / "Scripts" / "pythonw.exe"
    app_script = project_root / "src" / "nexus.py"
    if not pythonw.is_file() or not app_script.is_file():
        ctypes.windll.user32.MessageBoxW(
            None,
            "MotionForge workspace runtime was not found. Keep this launcher inside the project dist folder and run uv sync first.",
            "MotionForge launcher",
            0x10,
        )
        return 1
    subprocess.Popen([str(pythonw), str(app_script)], cwd=str(project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
