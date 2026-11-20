"""Build the distributable Windows desktop application with PyInstaller."""
from pathlib import Path
import os
import sys
import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
sep = ";" if os.name == "nt" else ":"

if os.name != "nt":
    raise SystemExit("Build the Windows executable on Windows using build_windows.bat")

PyInstaller.__main__.run([
    str(ROOT / "src" / "nexus.py"), "--name=MotionForge", "--onedir",
    "--windowed", "--noconfirm", "--paths", str(ROOT / "src"),
    "--collect-data=mediapipe",
    "--hidden-import=mediapipe.python.solutions",
    "--hidden-import=mediapipe.python.solutions.holistic",
    "--hidden-import=core", "--hidden-import=ui", "--hidden-import=PyQt5.QtOpenGL",
    "--runtime-hook", str(ROOT / "src" / "pyi_rth_mediapipe.py"),
    "--exclude-module=scipy", "--exclude-module=matplotlib",
    "--exclude-module=pytest", "--exclude-module=jupyter",
    "--add-data", f"{ROOT / 'README.md'}{sep}.",
])
