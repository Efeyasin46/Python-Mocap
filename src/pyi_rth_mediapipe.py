"""PyInstaller runtime hook: expose MediaPipe's bundled OpenCV DLL directory."""
import os
import sys

_runtime_root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
_mediapipe_dll_dir = os.path.join(_runtime_root, "mediapipe", "python")
if os.path.isdir(_mediapipe_dll_dir):
    # Keep the handle alive for the lifetime of the process.
    _mediapipe_dll_dir_handle = os.add_dll_directory(_mediapipe_dll_dir)

# This hook runs before PyInstaller's PyQt runtime hook. Loading the native
# MediaPipe runtime here avoids late DLL initialization after Qt is loaded.
import mediapipe  # noqa: F401,E402
