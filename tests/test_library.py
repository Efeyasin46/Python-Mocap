import json
import os

import pytest

from core.library import EXPORT, RECORDING, RecordingLibrary
from core.frame_model import UnifiedExporter
from helpers import synth_frames


def make_dir(tmp_path):
    frames, _ = synth_frames(n=10, fps=10.0)
    d = tmp_path / "data"; d.mkdir()
    UnifiedExporter.save_recording(frames, str(d / "new_v2.json"))
    (d / "old_v1.json").write_text(json.dumps([f.to_dict() for f in frames]))
    (d / "x_blender.json").write_text(json.dumps({"frames": []}))
    (d / "x_debug_report.json").write_text(json.dumps({"total_frames": 3}))
    (d / "junk.json").write_text("{not json")
    (d / "notes.txt").write_text("hi")
    (d / "calibration.json").write_text(json.dumps({"skeleton": {}}))
    return d


def test_scan_lists_only_recordings_with_metadata(tmp_path):
    d = make_dir(tmp_path)
    items = {i.name: i for i in RecordingLibrary(str(d)).scan()}
    assert set(items) == {"new_v2", "old_v1"}
    v2, v1 = items["new_v2"], items["old_v1"]
    assert (v2.schema_version, v2.frames, v2.kind) == (2, 10, RECORDING)
    assert v2.duration == pytest.approx(0.9) and v2.fps == pytest.approx(10.0)
    assert (v1.schema_version, v1.frames) == (1, 10) and v1.fps == pytest.approx(10.0)
    assert v2.source == v1.source == "webcam"


def test_exports_are_optional(tmp_path):
    d = make_dir(tmp_path)
    names = {i.name for i in RecordingLibrary(str(d)).scan(include_exports=True)}
    assert {"x_blender", "x_debug_report"} <= names
    assert all(i.kind in (RECORDING, EXPORT) for i in RecordingLibrary(str(d)).scan(True))


def test_newest_first_and_cache_refresh(tmp_path):
    d = make_dir(tmp_path)
    lib = RecordingLibrary(str(d))
    os.utime(d / "old_v1.json", (1_000, 1_000))
    os.utime(d / "new_v2.json", (2_000, 2_000))
    assert [i.name for i in lib.scan()] == ["new_v2", "old_v1"]
    os.utime(d / "old_v1.json", (3_000, 3_000))           # touched -> now newest
    assert [i.name for i in lib.scan()] == ["old_v1", "new_v2"]
    (d / "old_v1.json").write_text("[]")                  # content changed -> cache invalidated
    assert {i.name: i.frames for i in lib.scan()}["old_v1"] == 0


def test_missing_folder_is_empty(tmp_path):
    assert RecordingLibrary(str(tmp_path / "nope")).scan() == []


def test_delete_only_inside_data_dir(tmp_path):
    d = make_dir(tmp_path)
    lib = RecordingLibrary(str(d))
    lib.delete(str(d / "old_v1.json"))
    assert "old_v1" not in {i.name for i in lib.scan()}
    outside = tmp_path / "keep.json"; outside.write_text("[]")
    with pytest.raises(ValueError):
        lib.delete(str(outside))
    with pytest.raises(ValueError):
        lib.delete(str(d / ".." / "keep.json"))
    assert outside.exists()
