"""BVH exporter tests. An independent BVH parser + forward kinematics checks that
the exported angles reproduce the joint positions the landmarks described."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation as R

from core.bvh_exporter import BVHExporter, mp_to_bvh
from core.frame_model import Joint, MocapFrame
from helpers import fk, parse_bvh, synth_frames


def test_fk_reproduces_landmark_positions():
    frames, truth = synth_frames()
    text = BVHExporter(frames, scale=1.0).to_string()
    joints, order, n, ft, data = parse_bvh(text)
    assert n == len(frames) and ft == pytest.approx(1 / 30)
    for t in range(n):
        pos = fk(joints, order, data[t])
        for name, want in truth[t].items():
            assert np.allclose(pos[name], want, atol=2e-3), (t, name, pos[name], want)


def test_frame_time_uses_n_minus_one_intervals():
    frames, _ = synth_frames(n=11, fps=25.0)
    assert BVHExporter(frames).fps == pytest.approx(25.0)


def test_missing_limb_landmarks_still_exports():
    frames, _ = synth_frames()
    for f in frames:
        for k in ("LEFT_ELBOW", "LEFT_WRIST"):
            del f.world_joints[k]
    text = BVHExporter(frames).to_string()
    _, _, n, _, data = parse_bvh(text)
    assert n == len(frames) and np.isfinite(data).all()


def test_gap_is_interpolated():
    frames, _ = synth_frames(n=7)
    frames[3].world_joints["LEFT_ELBOW"].confidence = 0.0
    assert np.isfinite(parse_bvh(BVHExporter(frames).to_string())[4]).all()


def test_missing_required_landmarks_raises():
    frames, _ = synth_frames()
    for f in frames:
        del f.world_joints["LEFT_HIP"]
        del f.joints["LEFT_HIP"]
    with pytest.raises(ValueError):
        BVHExporter(frames).to_string()


def test_euler_continuous_over_wrap():
    # 360 degrees of body yaw must not produce 360-degree jumps between frames.
    frames = []
    for t in range(37):
        Rb = R.from_euler("y", 10 * t, degrees=True).as_matrix()
        hips = np.array([0, 1.0, 0]); right = Rb @ [1, 0, 0]; neck = hips + [0, .5, 0]
        L = {"LEFT_HIP": hips + right * .1, "RIGHT_HIP": hips - right * .1,
             "LEFT_SHOULDER": neck + right * .18, "RIGHT_SHOULDER": neck - right * .18}
        frames.append(MocapFrame(frame_id=t, timestamp=t / 30,
                                 world_joints={k: Joint(*mp_to_bvh(v), 0.9) for k, v in L.items()}))
    _, _, _, _, data = parse_bvh(BVHExporter(frames).to_string())
    assert np.abs(np.diff(data[:, 3:], axis=0)).max() < 45


def test_export_writes_file(tmp_path):
    frames, _ = synth_frames()
    p = BVHExporter(frames).export(str(tmp_path / "a.bvh"))
    assert (tmp_path / "a.bvh").read_text().startswith("HIERARCHY")
    assert BVHExporter([]).export(str(tmp_path / "b.bvh")) is None
