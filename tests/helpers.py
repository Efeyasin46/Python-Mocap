"""Shared synthetic-data helpers (no MediaPipe, camera or Qt needed)."""
import numpy as np
from scipy.spatial.transform import Rotation as R

from core.bvh_exporter import mp_to_bvh
from core.frame_model import Joint, MocapFrame


def parse_bvh(text):
    lines = [l.strip() for l in text.splitlines()]
    joints, order, stack = {}, [], []   # stack entries: joint name or None (End Site)
    i = 0
    while lines[i] != "MOTION":
        l = lines[i]
        if l.startswith(("ROOT", "JOINT")):
            name = l.split()[1]
            joints[name] = {"parent": next((s for s in reversed(stack) if s), None),
                            "offset": None, "ch": None}
            order.append(name)
            stack.append(name)
        elif l.startswith("End Site"):
            stack.append(None)
        elif l.startswith("OFFSET") and stack[-1]:
            joints[stack[-1]]["offset"] = np.array(l.split()[1:], float)
        elif l.startswith("CHANNELS"):
            joints[stack[-1]]["ch"] = l.split()[2:]
        elif l == "}":
            stack.pop()
        i += 1
    frames = int(lines[i + 1].split()[1])
    ft = float(lines[i + 2].split()[2])
    data = np.array([[float(v) for v in l.split()] for l in lines[i + 3:i + 3 + frames]])
    return joints, order, frames, ft, data


def fk(joints, order, row):
    pos, rot, k = {}, {}, 0
    for name in order:
        j = joints[name]
        ch = j["ch"]
        vals = row[k:k + len(ch)]; k += len(ch)
        local = np.eye(3); trans = np.zeros(3)
        for c, v in zip(ch, vals):
            pass
        if len(ch) == 6:
            trans = np.array(vals[:3]); angs = vals[3:]
        else:
            angs = vals
        assert ch[-3:] == ["Zrotation", "Xrotation", "Yrotation"]
        M = (R.from_euler("z", angs[0], degrees=True) * R.from_euler("x", angs[1], degrees=True)
             * R.from_euler("y", angs[2], degrees=True)).as_matrix()
        if j["parent"] is None:
            pos[name] = trans; rot[name] = M
        else:
            pos[name] = pos[j["parent"]] + rot[j["parent"]] @ j["offset"]
            rot[name] = rot[j["parent"]] @ M
    return pos


def synth_frames(n=6, fps=30.0):
    """Landmarks from a known articulated pose (BVH space, metres) -> MediaPipe space."""
    frames, truth = [], []
    for t in range(n):
        a = t / max(n - 1, 1)
        Rb = R.from_euler("zxy", [10 * a, 15 * a, 40 * a], degrees=True).as_matrix()  # body turn/lean
        hips = np.array([0.0, 0.95 + 0.02 * a, 0.0])
        up = Rb @ [0, 1, 0]; right = Rb @ [1, 0, 0]  # subject's left = +x
        neck = hips + 0.5 * up
        sh = 0.36
        L = {
            "LEFT_HIP": hips + right * 0.1, "RIGHT_HIP": hips - right * 0.1,
            "LEFT_SHOULDER": neck + right * sh / 2, "RIGHT_SHOULDER": neck - right * sh / 2,
        }
        # left arm bent at elbow, right arm raised
        L["LEFT_ELBOW"] = L["LEFT_SHOULDER"] + Rb @ np.array([0.2, -0.2, 0.0]) * (0.3 / np.hypot(.2, .2))
        L["LEFT_WRIST"] = L["LEFT_ELBOW"] + Rb @ np.array([0.0, -0.1, 0.25 * 1.0]) / np.linalg.norm([0, .1, .25]) * 0.27
        L["RIGHT_ELBOW"] = L["RIGHT_SHOULDER"] + Rb @ np.array([-0.2, 0.2, 0.0]) / np.hypot(.2, .2) * 0.3
        L["RIGHT_WRIST"] = L["RIGHT_ELBOW"] + Rb @ np.array([-0.27, 0, 0])
        # legs: left raised forward, right straight
        L["LEFT_KNEE"] = L["LEFT_HIP"] + np.array([0, -0.3, 0.3]) / np.hypot(.3, .3) * 0.42
        L["LEFT_ANKLE"] = L["LEFT_KNEE"] + np.array([0, -0.42, 0])
        L["RIGHT_KNEE"] = L["RIGHT_HIP"] + np.array([0, -0.42, 0])
        L["RIGHT_ANKLE"] = L["RIGHT_KNEE"] + np.array([0, -0.42, 0])
        head = neck + up * 0.25
        L["LEFT_EAR"] = head + right * 0.08; L["RIGHT_EAR"] = head - right * 0.08
        truth.append({"Hips": hips, "LeftArm": L["LEFT_SHOULDER"], "LeftForeArm": L["LEFT_ELBOW"],
                      "LeftHand": L["LEFT_WRIST"], "RightForeArm": L["RIGHT_ELBOW"],
                      "RightHand": L["RIGHT_WRIST"], "LeftLeg": L["LEFT_KNEE"],
                      "LeftFoot": L["LEFT_ANKLE"], "RightFoot": L["RIGHT_ANKLE"], "Neck": neck})
        w = {k: Joint(*mp_to_bvh(v), 0.9) for k, v in L.items()}  # involution: bvh<->mp
        frames.append(MocapFrame(frame_id=t, timestamp=t / fps, world_joints=w,
                                 joints={k: Joint(0.5, 0.5, 0, 0.9) for k in w}))
    return frames, truth


def render_video(frames, path, fps=30.0, size=(320, 240)):
    """Stick-figure video (orthographic front view) from synthetic world landmarks."""
    import cv2
    w, h = size
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not vw.isOpened():
        raise RuntimeError("cv2.VideoWriter could not open " + str(path))
    bones = [("LEFT_SHOULDER", "RIGHT_SHOULDER"), ("LEFT_HIP", "RIGHT_HIP"),
             ("LEFT_SHOULDER", "LEFT_ELBOW"), ("LEFT_ELBOW", "LEFT_WRIST"),
             ("RIGHT_SHOULDER", "RIGHT_ELBOW"), ("RIGHT_ELBOW", "RIGHT_WRIST"),
             ("LEFT_HIP", "LEFT_KNEE"), ("LEFT_KNEE", "LEFT_ANKLE"),
             ("RIGHT_HIP", "RIGHT_KNEE"), ("RIGHT_KNEE", "RIGHT_ANKLE")]
    for f in frames:
        img = np.zeros((h, w, 3), np.uint8)
        pt = lambda n: (int(w / 2 + f.world_joints[n].x * 120), int(h / 2 + f.world_joints[n].y * 120))
        for a, b in bones:
            if a in f.world_joints and b in f.world_joints:
                cv2.line(img, pt(a), pt(b), (255, 255, 255), 2)
        vw.write(img)
    vw.release()
    return path
