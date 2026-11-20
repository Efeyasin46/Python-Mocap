import json

import numpy as np
import pytest

from core.frame_model import Bone, Joint, MocapFrame, UnifiedExporter
from core.motion_clip import SCHEMA_VERSION, ClipFormatError, MotionClip


def make_frames(n=5, fps=30.0):
    frames = []
    for i in range(n):
        j = {
            "LEFT_HIP": Joint(0.4, 0.5 + i * 0.01, 0.0, 0.9),
            "RIGHT_HIP": Joint(0.6, 0.5, 0.0, 0.9),
            "LEFT_SHOULDER": Joint(0.4, 0.3, 0.0, 0.8),
            "RIGHT_SHOULDER": Joint(0.6, 0.3, 0.0, 0.8),
        }
        w = {k: Joint(v.x - 0.5, v.y - 0.5, v.z, v.confidence) for k, v in j.items()}
        if i == 2:
            del w["RIGHT_SHOULDER"]  # joint missing in one frame
        f = MocapFrame(frame_id=i, timestamp=i / fps, joints=j, world_joints=w,
                       confidence_avg=0.85, source="video")
        if i == 1:
            f.meta = {"note": "x"}
            f.bones = [Bone("LEFT_HIP", "RIGHT_HIP", 0.2)]
        frames.append(f)
    return frames


def test_roundtrip_v2_lossless(tmp_path):
    frames = make_frames()
    p = tmp_path / "c.json"
    UnifiedExporter.save_recording(frames, str(p))
    raw = json.loads(p.read_text())
    assert raw["schema_version"] == SCHEMA_VERSION
    back = UnifiedExporter.load_recording(str(p))
    assert [f.to_dict() for f in back] == [f.to_dict() for f in frames]


def test_v1_list_migrates(tmp_path):
    frames = make_frames()
    p = tmp_path / "old.json"
    p.write_text(json.dumps([f.to_dict() for f in frames]))
    clip = MotionClip.load(str(p))
    assert clip.schema_version == 2 and len(clip) == 5
    assert clip.meta["migrated_from"] == 1
    assert clip.fps == pytest.approx(30.0)
    assert [f.to_dict() for f in clip.to_frames()] == [f.to_dict() for f in frames]


def test_missing_joint_is_nan_with_zero_conf():
    clip = MotionClip.from_frames(make_frames())
    k = clip.joint_names.index("RIGHT_SHOULDER")
    assert np.isnan(clip.world[2, k, :3]).all() and clip.world[2, k, 3] == 0.0
    assert clip.has_world


def test_empty_clip_roundtrip(tmp_path):
    p = tmp_path / "e.json"
    UnifiedExporter.save_recording([], str(p))
    assert UnifiedExporter.load_recording(str(p)) == []


def test_mixed_sources_preserved():
    frames = make_frames(3)
    frames[1].source = "mobile_wifi"
    back = MotionClip.from_frames(frames).to_frames()
    assert [f.source for f in back] == ["video", "mobile_wifi", "video"]


@pytest.mark.parametrize("payload", [
    {"schema_version": 3, "format": "motionforge-clip"},
    {"schema_version": 2, "format": "other"},
    {"frames": []},
    "nope",
])
def test_bad_files_rejected(payload):
    with pytest.raises(ClipFormatError):
        MotionClip.from_dict(payload)


def test_shape_mismatch_rejected():
    d = MotionClip.from_frames(make_frames()).to_dict()
    d["frame_ids"] = d["frame_ids"][:-1]
    with pytest.raises(ClipFormatError):
        MotionClip.from_dict(d)


def test_invalid_json_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{")
    with pytest.raises(ClipFormatError):
        MotionClip.load(str(p))
