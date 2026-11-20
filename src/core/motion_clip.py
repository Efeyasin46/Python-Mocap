"""MotionClip: tensor-based, versioned motion container (JSON schema v2).

Pure numpy + stdlib. No GUI, camera or MediaPipe imports, so it can be used by
headless tools and tests.

Schema history
--------------
v1 (legacy): a bare JSON list of ``MocapFrame.to_dict()`` dicts.
v2:          ``{"schema_version": 2, "format": "motionforge-clip", ...}`` with
             column-oriented arrays (see ``MotionClip.to_dict``).

Layout of the arrays (T frames, J joints):
    timestamps  (T,)       seconds
    image       (T, J, 4)  x, y, z, confidence  -- normalized image landmarks
    world       (T, J, 4)  x, y, z, confidence  -- metres, MediaPipe axes
A joint that is absent in a frame is stored as NaN coordinates, confidence 0.
In JSON, NaN is written as ``null``.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

SCHEMA_VERSION = 2
FORMAT_NAME = "motionforge-clip"


class ClipFormatError(ValueError):
    """Raised when a file is not a recognizable MotionForge recording."""


def _stack(frames_maps: Sequence[Dict[str, Any]], names: List[str]) -> np.ndarray:
    out = np.full((len(frames_maps), len(names), 4), np.nan, dtype=np.float64)
    out[:, :, 3] = 0.0
    index = {n: i for i, n in enumerate(names)}
    for t, joints in enumerate(frames_maps):
        for name, j in joints.items():
            out[t, index[name]] = (j.x, j.y, j.z, j.confidence)
    return out


@dataclass
class MotionClip:
    joint_names: List[str]
    timestamps: np.ndarray
    image: np.ndarray
    world: np.ndarray
    frame_ids: np.ndarray
    confidence_avg: np.ndarray
    fps: Optional[float] = None
    source: str = "webcam"
    # Sparse per-frame data that does not fit the tensors: {frame index: value}
    frame_meta: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    frame_bones: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    # ------------------------------------------------------------------ basics
    def __len__(self) -> int:
        return int(self.timestamps.shape[0])

    @property
    def has_world(self) -> bool:
        return bool(self.world.size) and not np.isnan(self.world[..., :3]).all()

    def validate(self) -> None:
        t, j = len(self), len(self.joint_names)
        if self.image.shape != (t, j, 4) or self.world.shape != (t, j, 4):
            raise ClipFormatError(
                f"array shapes {self.image.shape}/{self.world.shape} do not match "
                f"{t} frames x {j} joints")
        if self.frame_ids.shape != (t,) or self.confidence_avg.shape != (t,):
            raise ClipFormatError("frame_ids/confidence_avg length mismatch")
        if len(set(self.joint_names)) != j:
            raise ClipFormatError("duplicate joint names")

    # ------------------------------------------------------ MocapFrame bridge
    @classmethod
    def from_frames(cls, frames: Sequence["MocapFrame"], fps: Optional[float] = None,  # noqa: F821
                    meta: Optional[Dict[str, Any]] = None) -> "MotionClip":
        names: List[str] = []
        seen = set()
        for f in frames:
            for n in list(f.joints) + list(f.world_joints):
                if n not in seen:
                    seen.add(n)
                    names.append(n)
        ts = np.array([f.timestamp for f in frames], dtype=np.float64)
        if fps is None and len(ts) > 1:
            span = float(ts[-1] - ts[0])
            fps = (len(ts) - 1) / span if span > 0 else None
        sources = {f.source for f in frames}
        source = next(iter(sources)) if len(sources) == 1 else ("mixed" if sources else "webcam")
        clip = cls(
            joint_names=names,
            timestamps=ts,
            image=_stack([f.joints for f in frames], names),
            world=_stack([f.world_joints for f in frames], names),
            frame_ids=np.array([f.frame_id for f in frames], dtype=np.int64),
            confidence_avg=np.array([f.confidence_avg for f in frames], dtype=np.float64),
            fps=fps,
            source=source,
            meta=dict(meta or {}),
        )
        for i, f in enumerate(frames):
            if f.meta:
                clip.frame_meta[i] = dict(f.meta)
            if f.bones:
                clip.frame_bones[i] = [{"a": b.a, "b": b.b, "length": b.length} for b in f.bones]
        if clip.source == "mixed":
            clip.meta["frame_sources"] = [f.source for f in frames]
        return clip

    def to_frames(self) -> List["MocapFrame"]:  # noqa: F821
        from core.frame_model import Bone, Joint, MocapFrame

        per_frame_src = self.meta.get("frame_sources")
        frames = []
        for t in range(len(self)):
            def joints(arr: np.ndarray) -> Dict[str, Joint]:
                d = {}
                for k, name in enumerate(self.joint_names):
                    x, y, z, c = arr[t, k]
                    if math.isnan(x) and math.isnan(y) and math.isnan(z):
                        continue
                    d[name] = Joint(float(x), float(y), float(z), float(c))
                return d

            frames.append(MocapFrame(
                frame_id=int(self.frame_ids[t]),
                timestamp=float(self.timestamps[t]),
                joints=joints(self.image),
                world_joints=joints(self.world),
                bones=[Bone(**b) for b in self.frame_bones.get(t, [])],
                confidence_avg=float(self.confidence_avg[t]),
                source=per_frame_src[t] if per_frame_src else self.source,
                meta=dict(self.frame_meta.get(t, {})),
            ))
        return frames

    # ------------------------------------------------------------ (de)serialize
    @staticmethod
    def _arr(a: np.ndarray) -> Any:
        return np.where(np.isnan(a), None, a).tolist() if a.size else []

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "format": FORMAT_NAME,
            "fps": self.fps,
            "source": self.source,
            "joint_names": list(self.joint_names),
            "frame_ids": self.frame_ids.tolist(),
            "timestamps": self.timestamps.tolist(),
            "confidence_avg": self.confidence_avg.tolist(),
            "image": self._arr(self.image),
            "world": self._arr(self.world),
            "frame_meta": {str(k): v for k, v in self.frame_meta.items()},
            "frame_bones": {str(k): v for k, v in self.frame_bones.items()},
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MotionClip":
        """Accepts v2 dicts and legacy v1 lists; always returns a v2 clip."""
        from core.frame_model import MocapFrame

        if isinstance(data, list):  # v1
            try:
                frames = [MocapFrame.from_dict(f) for f in data]
            except (KeyError, TypeError) as e:
                raise ClipFormatError(f"invalid v1 recording: {e!r}") from e
            return cls.from_frames(frames, meta={"migrated_from": 1})
        if not isinstance(data, dict):
            raise ClipFormatError("recording must be a JSON list (v1) or object (v2)")
        version = data.get("schema_version")
        if version is None and "frames" in data:
            raise ClipFormatError("looks like a Blender export, not a recording")
        if version != SCHEMA_VERSION:
            raise ClipFormatError(
                f"unsupported schema_version {version!r}; this build reads 1 (list) and "
                f"{SCHEMA_VERSION}")
        if data.get("format") != FORMAT_NAME:
            raise ClipFormatError(f"unexpected format {data.get('format')!r}")

        def tensor(key: str, t: int, j: int) -> np.ndarray:
            raw = data.get(key) or []
            a = np.array(raw, dtype=object).reshape(t, j, 4) if t * j else np.zeros((t, j, 4), dtype=object)
            a = np.where(a == None, np.nan, a).astype(np.float64)  # noqa: E711
            a[..., 3] = np.nan_to_num(a[..., 3], nan=0.0)
            return a

        names = list(data["joint_names"])
        ts = np.array(data["timestamps"], dtype=np.float64)
        t, j = len(ts), len(names)
        clip = cls(
            joint_names=names,
            timestamps=ts,
            image=tensor("image", t, j),
            world=tensor("world", t, j),
            frame_ids=np.array(data["frame_ids"], dtype=np.int64),
            confidence_avg=np.array(data["confidence_avg"], dtype=np.float64),
            fps=data.get("fps"),
            source=data.get("source", "webcam"),
            frame_meta={int(k): v for k, v in (data.get("frame_meta") or {}).items()},
            frame_bones={int(k): v for k, v in (data.get("frame_bones") or {}).items()},
            meta=data.get("meta") or {},
        )
        clip.validate()
        return clip

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, separators=(",", ":"))
        return path

    @classmethod
    def load(cls, path: str) -> "MotionClip":
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise ClipFormatError(f"not valid JSON: {e}") from e
        return cls.from_dict(data)
