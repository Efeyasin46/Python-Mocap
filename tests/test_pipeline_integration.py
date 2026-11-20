"""Headless integration tests: synthetic landmarks -> bake filter chain -> v2 file
-> Blender/BVH/Unity export. Covers everything except MediaPipe inference itself."""
import json

import numpy as np
import pytest
from helpers import parse_bvh, render_video, synth_frames

from core.bake_filters import BakeFilters
from core.frame_model import UnifiedExporter

FPS = 24.0


def jittered(frames, sigma=0.01, seed=0):
    rng = np.random.default_rng(seed)
    for f in frames:
        for j in f.world_joints.values():
            j.x += rng.normal(0, sigma); j.y += rng.normal(0, sigma); j.z += rng.normal(0, sigma)
    return frames


def bake(frames):
    f = BakeFilters()
    kept = [fr for fr in frames if f.process_frame(fr)]
    return BakeFilters.finalize(kept)


def test_synthetic_video_has_expected_timing(tmp_path):
    import cv2
    frames, _ = synth_frames(n=24, fps=FPS)
    p = render_video(frames, tmp_path / "s.mp4", fps=FPS)
    cap = cv2.VideoCapture(str(p))
    assert cap.isOpened()
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    assert n == 24 and fps == pytest.approx(FPS)
    # Deterministic timestamps as bake.py computes them: frame index / fps
    assert [i / fps for i in range(n)][-1] == pytest.approx(23 / FPS)
    ok, img = cap.read()
    assert ok and img.shape[:2] == (240, 320) and img.max() > 0   # something was drawn
    cap.release()


def test_filters_reduce_jitter():
    clean, _ = synth_frames(n=60)
    noisy = jittered(synth_frames(n=60)[0])
    baked = bake(noisy)

    def err(frames):
        return np.mean([abs(f.world_joints["LEFT_WRIST"].x - c.world_joints["LEFT_WRIST"].x)
                        for f, c in zip(frames, clean)])
    assert len(baked) == 60
    assert err(baked) < err(jittered(synth_frames(n=60)[0]))


def test_dropped_frames_are_not_fabricated():
    frames, _ = synth_frames(n=10)
    for i in range(3, 10):            # pose lost: MediaPipe drops image AND world landmarks
        frames[i].world_joints = {}
        frames[i].joints = {}
    f = BakeFilters()
    kept = [f.process_frame(fr) for fr in frames]
    assert kept == [True] * 3 + [False] * 7
    assert all(not frames[i].world_joints for i in range(3, 10))


def test_low_confidence_landmarks_are_omitted():
    frames, _ = synth_frames(n=1)
    wrist = frames[0].world_joints["LEFT_WRIST"]
    wrist.x = 100.0
    wrist.confidence = 0.2
    assert BakeFilters(min_confidence=0.65).process_frame(frames[0])
    assert "LEFT_WRIST" not in frames[0].world_joints


def test_floor_alignment_is_constant_and_keeps_jump():
    frames, _ = synth_frames(n=30)
    for i, fr in enumerate(frames):    # lift the whole body (a jump) mid-clip
        lift = 0.5 if 10 <= i < 20 else 0.0
        for j in fr.world_joints.values():
            j.y -= lift                # MediaPipe Y points down
            j.y += 3.0                 # arbitrary global offset
    frames = BakeFilters.finalize(frames)
    ankle_up = np.array([-min(f.world_joints["LEFT_ANKLE"].y, f.world_joints["RIGHT_ANKLE"].y)
                         for f in frames])
    low = np.array([-max(f.world_joints["LEFT_ANKLE"].y, f.world_joints["RIGHT_ANKLE"].y)
                    for f in frames])
    assert low.min() == pytest.approx(0.0, abs=1e-9)           # clip touches the floor
    assert low[10:20].min() > low[:10].min() + 0.4              # airborne frames stay airborne


def test_end_to_end_capture_file_to_exports(tmp_path, monkeypatch):
    import export_blender
    frames = bake(jittered(synth_frames(n=40, fps=FPS)[0], sigma=0.004))
    rec = tmp_path / "rec.json"
    UnifiedExporter.save_recording(frames, str(rec))
    assert json.loads(rec.read_text())["schema_version"] == 2

    out_json, report, bvh, unity = export_blender.BlenderExporter(str(rec)).export(
        str(tmp_path / "o.json"), str(tmp_path / "r.json"))
    rep = json.loads(open(report).read())
    assert rep["total_frames"] == 40 and rep["bvh_status"] == "Success"

    _, _, n, ft, data = parse_bvh(open(bvh).read())
    assert n == 40 and ft == pytest.approx(1 / FPS, rel=1e-3) and np.isfinite(data).all()
    u = json.loads(open(unity).read())
    assert u["fps"] == pytest.approx(FPS, rel=1e-3) and len(u["frames"]) == 40
