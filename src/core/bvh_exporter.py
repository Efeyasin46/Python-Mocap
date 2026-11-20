"""BVH exporter built around a derived humanoid rig.

Pipeline
--------
1. ``MotionClip.world`` (MediaPipe world landmarks, metres, X right / Y down /
   Z depth) -> low-confidence/missing samples are interpolated over time.
2. Axis conversion happens in exactly one place (``mp_to_bvh``):
   BVH = (x, -y, -z)  -> X = image-right (= subject's left), Y up, Z toward
   the camera (= the direction a camera-facing subject looks). Proper rotation.
3. Rig joints that MediaPipe does not have (Hips, Spine, Spine1, Neck, Head,
   clavicles) are derived from landmarks.
4. Bone lengths are constant for the whole clip: median of the observed
   lengths, left/right averaged. The rest pose is a T-pose with identity joint
   orientations, so ``OFFSET`` values are pure bone vectors.
5. Per frame, global joint orientations are solved from bone *directions*
   (shortest-arc swing, or a full basis for Hips / chest / head where a side
   axis is known), then converted to local ZXY Euler angles (channel order
   ``Zrotation Xrotation Yrotation``, matrix = Rz @ Rx @ Ry).

Known limits: no bone-twist information for arms/legs (swing only); root
translation is whatever the world landmarks give (MediaPipe world space is
hip-centred, so only height changes unless the clip was floor aligned).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial.transform import Rotation

from core.frame_model import MocapFrame
from core.motion_clip import MotionClip

# (joint, parent) in DFS order; the order defines the MOTION column order.
RIG: List[Tuple[str, Optional[str]]] = [
    ("Hips", None),
    ("Spine", "Hips"),
    ("Spine1", "Spine"),
    ("Neck", "Spine1"),
    ("Head", "Neck"),
    ("LeftShoulder", "Spine1"),
    ("LeftArm", "LeftShoulder"),
    ("LeftForeArm", "LeftArm"),
    ("LeftHand", "LeftForeArm"),
    ("RightShoulder", "Spine1"),
    ("RightArm", "RightShoulder"),
    ("RightForeArm", "RightArm"),
    ("RightHand", "RightForeArm"),
    ("LeftUpLeg", "Hips"),
    ("LeftLeg", "LeftUpLeg"),
    ("LeftFoot", "LeftLeg"),
    ("RightUpLeg", "Hips"),
    ("RightLeg", "RightUpLeg"),
    ("RightFoot", "RightLeg"),
]
PARENT = dict(RIG)
CHILDREN: Dict[str, List[str]] = {n: [] for n, _ in RIG}
for _n, _p in RIG:
    if _p:
        CHILDREN[_p].append(_n)

# Joints that get an End Site, and the rest direction of that end site.
END_SITES = {
    "Head": np.array([0.0, 1.0, 0.0]),
    "LeftHand": np.array([1.0, 0.0, 0.0]),
    "RightHand": np.array([-1.0, 0.0, 0.0]),
    "LeftFoot": np.array([0.0, -0.35, 1.0]) / np.linalg.norm([0.0, -0.35, 1.0]),
    "RightFoot": np.array([0.0, -0.35, 1.0]) / np.linalg.norm([0.0, -0.35, 1.0]),
}

REQUIRED = ("LEFT_HIP", "RIGHT_HIP", "LEFT_SHOULDER", "RIGHT_SHOULDER")


def mp_to_bvh(p: np.ndarray) -> np.ndarray:
    """MediaPipe world (X right, Y down, Z depth) -> BVH (X, Y up, Z forward)."""
    return p * np.array([1.0, -1.0, -1.0])


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def arc(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Shortest-arc rotation matrix taking unit vector a onto unit vector b."""
    a, b = _unit(a), _unit(b)
    c = float(np.dot(a, b))
    if c > 1.0 - 1e-9:
        return np.eye(3)
    if c < -1.0 + 1e-9:  # 180 degrees: pick any perpendicular axis
        axis = _unit(np.cross(a, [1.0, 0.0, 0.0]))
        if np.linalg.norm(axis) < 1e-6:
            axis = _unit(np.cross(a, [0.0, 1.0, 0.0]))
        return Rotation.from_rotvec(axis * np.pi).as_matrix()
    v = np.cross(a, b)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def basis(side: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Right-handed orientation: x along ``side``, y as close to ``up`` as possible."""
    x = _unit(side)
    z = np.cross(x, up)
    if np.linalg.norm(z) < 1e-9:
        return np.eye(3)
    z = _unit(z)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


class BVHExporter:
    MIN_CONF = 0.2          # landmark samples below this are treated as missing
    DEFAULT_FPS = 30.0

    def __init__(self, frames: Sequence[MocapFrame], scale: float = 100.0,
                 fps: Optional[float] = None):
        """``scale`` converts metres to BVH units (100 -> centimetres)."""
        self.frames = list(frames)
        self.scale = scale
        self.clip = MotionClip.from_frames(self.frames)
        self.fps = fps or self.clip.fps or self.DEFAULT_FPS
        self.rest_offsets: Dict[str, np.ndarray] = {}   # metres, BVH axes
        self.motion_order = [n for n, _ in RIG]

    # ------------------------------------------------------------------ input
    def _landmarks(self) -> Dict[str, np.ndarray]:
        """Name -> (T, 3) BVH-space metres with gaps interpolated; absent -> omitted."""
        clip = self.clip
        use_world = clip.has_world
        arr = clip.world if use_world else clip.image
        out: Dict[str, np.ndarray] = {}
        t = np.arange(len(clip))
        for k, name in enumerate(clip.joint_names):
            xyz = arr[:, k, :3].copy()
            bad = np.isnan(xyz).any(axis=1) | (arr[:, k, 3] < self.MIN_CONF)
            if bad.all():
                continue
            if bad.any():
                for c in range(3):
                    xyz[bad, c] = np.interp(t[bad], t[~bad], xyz[~bad, c])
            out[name] = mp_to_bvh(xyz)
        missing = [n for n in REQUIRED if n not in out]
        if missing:
            raise ValueError(f"cannot build BVH: no usable landmarks for {missing}")
        if not use_world:
            # Normalized image coords are not metric: scale so torso ~= 0.5 m.
            hips = (out["LEFT_HIP"] + out["RIGHT_HIP"]) / 2
            neck = (out["LEFT_SHOULDER"] + out["RIGHT_SHOULDER"]) / 2
            torso = float(np.median(np.linalg.norm(neck - hips, axis=1)))
            s = 0.5 / torso if torso > 1e-6 else 1.0
            out = {k: v * s for k, v in out.items()}
        return out

    @staticmethod
    def derive_rig_points(lm: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Rig joint positions, each (T, 3). Joints without data are omitted."""
        P: Dict[str, np.ndarray] = {}
        hips = (lm["LEFT_HIP"] + lm["RIGHT_HIP"]) / 2
        neck = (lm["LEFT_SHOULDER"] + lm["RIGHT_SHOULDER"]) / 2
        P["Hips"], P["Neck"] = hips, neck
        P["Spine"] = hips + (neck - hips) * 0.34
        P["Spine1"] = hips + (neck - hips) * 0.66
        if "LEFT_EAR" in lm and "RIGHT_EAR" in lm:
            P["Head"] = (lm["LEFT_EAR"] + lm["RIGHT_EAR"]) / 2
        elif "NOSE" in lm:
            P["Head"] = lm["NOSE"]
        else:
            P["Head"] = neck + (neck - hips) * 0.5
        for side, S in (("Left", "LEFT"), ("Right", "RIGHT")):
            P[f"{side}Shoulder"] = neck           # clavicle pivot at the neck base
            P[f"{side}Arm"] = lm[f"{S}_SHOULDER"]
            P[f"{side}UpLeg"] = lm[f"{S}_HIP"]
            for rig, mp in (("ForeArm", "ELBOW"), ("Hand", "WRIST"),
                            ("Leg", "KNEE"), ("Foot", "ANKLE")):
                if f"{S}_{mp}" in lm:
                    P[f"{side}{rig}"] = lm[f"{S}_{mp}"]
        return P

    # --------------------------------------------------------------- rest rig
    def _med(self, a: Optional[np.ndarray], b: Optional[np.ndarray], default: float) -> float:
        if a is None or b is None:
            return default
        return float(np.median(np.linalg.norm(b - a, axis=1)))

    def build_rest_offsets(self, lm: Dict[str, np.ndarray], P: Dict[str, np.ndarray]
                           ) -> Dict[str, np.ndarray]:
        def L(a: str, b: str, src: Dict[str, np.ndarray], default: float) -> float:
            return self._med(src.get(a), src.get(b), default)

        def both(a: str, b: str, default: float) -> float:
            vals = [L(f"{s}_{a}", f"{s}_{b}", lm, np.nan) for s in ("LEFT", "RIGHT")]
            vals = [v for v in vals if np.isfinite(v)]
            return float(np.mean(vals)) if vals else default

        hip_w = L("LEFT_HIP", "RIGHT_HIP", lm, 0.2)
        sh_w = L("LEFT_SHOULDER", "RIGHT_SHOULDER", lm, 0.36)
        torso = L("Hips", "Neck", P, 0.5)
        head = L("Neck", "Head", P, 0.25 * torso)
        upper = both("SHOULDER", "ELBOW", 0.3)
        fore = both("ELBOW", "WRIST", 0.27)
        thigh = both("HIP", "KNEE", 0.42)
        shin = both("KNEE", "ANKLE", 0.42)
        o = {
            "Hips": np.zeros(3),
            "Spine": np.array([0, 0.34 * torso, 0]),
            "Spine1": np.array([0, 0.32 * torso, 0]),
            "Neck": np.array([0, 0.34 * torso, 0]),
            "Head": np.array([0, head, 0]),
            "LeftShoulder": np.array([0, 0.34 * torso, 0]),   # clavicle pivot = Neck base
            "RightShoulder": np.array([0, 0.34 * torso, 0]),
            "LeftArm": np.array([sh_w / 2, 0, 0]),
            "RightArm": np.array([-sh_w / 2, 0, 0]),
            "LeftForeArm": np.array([upper, 0, 0]),
            "RightForeArm": np.array([-upper, 0, 0]),
            "LeftHand": np.array([fore, 0, 0]),
            "RightHand": np.array([-fore, 0, 0]),
            "LeftUpLeg": np.array([hip_w / 2, 0, 0]),
            "RightUpLeg": np.array([-hip_w / 2, 0, 0]),
            "LeftLeg": np.array([0, -thigh, 0]),
            "RightLeg": np.array([0, -thigh, 0]),
            "LeftFoot": np.array([0, -shin, 0]),
            "RightFoot": np.array([0, -shin, 0]),
        }
        self.end_site_len = {
            "Head": 0.5 * head,
            "LeftHand": 0.35 * fore, "RightHand": 0.35 * fore,
            "LeftFoot": both("ANKLE", "FOOT_INDEX", 0.2),
            "RightFoot": both("ANKLE", "FOOT_INDEX", 0.2),
        }
        return o

    # ------------------------------------------------------------- pose solve
    def solve(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (root_positions (T,3) metres, euler (T, J, 3) degrees ZXY order z,x,y)."""
        lm = self._landmarks()
        P = self.derive_rig_points(lm)
        self.rest_offsets = self.build_rest_offsets(lm, P)
        T, names = len(self.clip), self.motion_order
        euler = np.zeros((T, len(names), 3))
        idx = {n: i for i, n in enumerate(names)}
        side_hip = lm["LEFT_HIP"] - lm["RIGHT_HIP"]
        side_sh = lm["LEFT_SHOULDER"] - lm["RIGHT_SHOULDER"]
        ear_axis = None
        if "LEFT_EAR" in lm and "RIGHT_EAR" in lm:
            ear_axis = lm["LEFT_EAR"] - lm["RIGHT_EAR"]

        for t in range(T):
            up = P["Neck"][t] - P["Hips"][t]
            G: Dict[str, np.ndarray] = {}
            for name in names:
                parent_g = G[PARENT[name]] if PARENT[name] else np.eye(3)
                G[name] = parent_g  # default: inherit (leaf / no data)
                if name == "Hips":
                    G[name] = basis(side_hip[t], up)
                elif name == "Spine1":
                    G[name] = basis(side_sh[t], up)
                elif name == "Head" and ear_axis is not None:
                    G[name] = basis(ear_axis[t], P["Head"][t] - P["Neck"][t])
                else:
                    kids = [c for c in CHILDREN[name] if c in P and name in P]
                    # Only single-chain joints are solved by swing; branching joints
                    # (Hips, Spine1) were handled above.
                    if len(CHILDREN[name]) == 1 and kids:
                        c = kids[0]
                        cur = P[c][t] - P[name][t]
                        if np.linalg.norm(cur) > 1e-6:
                            # Swing relative to the parent's current pose, so the bone
                            # inherits parent twist and stays near-identity locally.
                            G[name] = arc(parent_g @ self.rest_offsets[c], cur) @ parent_g
                local = parent_g.T @ G[name]
                euler[t, idx[name]] = Rotation.from_matrix(local).as_euler("ZXY", degrees=True)

        # Keep angles continuous across +-180 wraps.
        euler = np.degrees(np.unwrap(np.radians(euler), axis=0))
        return P["Hips"], euler

    # ------------------------------------------------------------------ output
    def _joint_lines(self, name: str, indent: int) -> List[str]:
        sp = "  " * indent
        off = self.rest_offsets[name] * self.scale
        kind = "ROOT" if PARENT[name] is None else "JOINT"
        ch = ("6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"
              if PARENT[name] is None else "3 Zrotation Xrotation Yrotation")
        lines = [f"{sp}{kind} {name}", f"{sp}{{",
                 f"{sp}  OFFSET {off[0]:.6f} {off[1]:.6f} {off[2]:.6f}",
                 f"{sp}  CHANNELS {ch}"]
        for c in CHILDREN[name]:
            lines += self._joint_lines(c, indent + 1)
        if name in END_SITES:
            e = END_SITES[name] * self.end_site_len[name] * self.scale
            lines += [f"{sp}  End Site", f"{sp}  {{",
                      f"{sp}    OFFSET {e[0]:.6f} {e[1]:.6f} {e[2]:.6f}", f"{sp}  }}"]
        lines.append(f"{sp}}}")
        return lines

    def to_string(self) -> str:
        root, euler = self.solve()
        lines = ["HIERARCHY"] + self._joint_lines("Hips", 0)
        lines += ["MOTION", f"Frames: {len(self.clip)}", f"Frame Time: {1.0 / self.fps:.8f}"]
        for t in range(len(self.clip)):
            vals = list(root[t] * self.scale) + list(euler[t].reshape(-1))
            lines.append(" ".join(f"{v:.6f}" for v in vals))
        return "\n".join(lines) + "\n"

    def export(self, output_path: str) -> Optional[str]:
        if not self.frames:
            return None
        text = self.to_string()
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return output_path
