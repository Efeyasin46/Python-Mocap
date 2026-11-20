"""Recording library: index of motion files in a data folder. Pure stdlib, no Qt.

Only files that are actual recordings (v1 list or v2 clip) are reported as
``kind == "recording"``. Exports written next to them (``*_blender.json``,
``*_debug_report.json``, ``*_unity.json``) are classified so a UI can hide them.
Metadata is cached per (path, mtime, size), so rescans are cheap.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core.motion_clip import FORMAT_NAME

RECORDING, EXPORT, OTHER = "recording", "export", "other"


@dataclass(frozen=True)
class RecordingInfo:
    path: str
    name: str
    kind: str
    schema_version: Optional[int] = None
    frames: int = 0
    duration: float = 0.0
    fps: Optional[float] = None
    source: Optional[str] = None
    size: int = 0
    mtime: float = 0.0
    error: Optional[str] = None


def _sniff(path: str) -> Dict:
    """Classify one file and pull header metadata. Never raises."""
    st = os.stat(path)
    base = dict(path=path, name=os.path.splitext(os.path.basename(path))[0],
                size=st.st_size, mtime=st.st_mtime)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return {**base, "kind": OTHER, "error": f"unreadable: {e}"}

    if isinstance(data, list):                                   # v1
        if data and not all(isinstance(x, dict) and "timestamp" in x and "frame_id" in x
                            for x in (data[0], data[-1])):
            return {**base, "kind": OTHER}
        ts = [data[0]["timestamp"], data[-1]["timestamp"]] if data else [0.0, 0.0]
        dur = max(0.0, float(ts[1]) - float(ts[0]))
        return {**base, "kind": RECORDING, "schema_version": 1, "frames": len(data),
                "duration": dur, "fps": (len(data) - 1) / dur if dur > 0 else None,
                "source": data[0].get("source") if data else None}
    if isinstance(data, dict):
        if data.get("format") == FORMAT_NAME:                    # v2
            ts = data.get("timestamps") or []
            dur = float(ts[-1] - ts[0]) if len(ts) > 1 else 0.0
            return {**base, "kind": RECORDING, "schema_version": data.get("schema_version"),
                    "frames": len(ts), "duration": dur, "fps": data.get("fps"),
                    "source": data.get("source")}
        if "frames" in data or "total_frames" in data:           # blender / unity / report
            return {**base, "kind": EXPORT}
    return {**base, "kind": OTHER}


class RecordingLibrary:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self._cache: Dict[str, Tuple[Tuple[float, int], RecordingInfo]] = {}

    def scan(self, include_exports: bool = False) -> List[RecordingInfo]:
        """Newest first. Missing folder -> empty list."""
        if not os.path.isdir(self.data_dir):
            self._cache.clear()
            return []
        seen, out = set(), []
        for entry in os.scandir(self.data_dir):
            if not entry.is_file() or not entry.name.lower().endswith(".json"):
                continue
            seen.add(entry.path)
            st = entry.stat()
            key = (st.st_mtime, st.st_size)
            cached = self._cache.get(entry.path)
            if cached and cached[0] == key:
                info = cached[1]
            else:
                info = RecordingInfo(**_sniff(entry.path))
                self._cache[entry.path] = (key, info)
            if info.kind == RECORDING or (include_exports and info.kind == EXPORT):
                out.append(info)
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        return sorted(out, key=lambda i: (-i.mtime, i.name))

    def delete(self, path: str) -> None:
        """Deletes one file, only if it lives directly inside the data folder."""
        real, root = os.path.realpath(path), os.path.realpath(self.data_dir)
        if os.path.dirname(real) != root:
            raise ValueError("refusing to delete a file outside the data folder")
        os.remove(real)
        self._cache.pop(path, None)
