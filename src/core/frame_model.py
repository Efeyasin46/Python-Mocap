import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

@dataclass
class Joint:
    x: float
    y: float
    z: float
    confidence: float = 0.0

@dataclass
class Bone:
    a: str
    b: str
    length: float = 0.0

@dataclass
class MocapFrame:
    frame_id: int
    timestamp: float
    joints: Dict[str, Joint] = field(default_factory=dict) # Normalized [0, 1]
    world_joints: Dict[str, Joint] = field(default_factory=dict) # Meters
    bones: List[Bone] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MocapFrame':
        joints = {
            name: Joint(**j_data) for name, j_data in data.get("joints", {}).items()
        }
        world_joints = {
            name: Joint(**wj_data) for name, wj_data in data.get("world_joints", {}).items()
        }
        bones = [Bone(**b_data) for b_data in data.get("bones", [])]
        return cls(
            frame_id=data["frame_id"],
            timestamp=data["timestamp"],
            joints=joints,
            world_joints=world_joints,
            bones=bones,
            meta=data.get("meta", {})
        )

    def is_valid(self) -> bool:
        """Checks if the frame has sufficient and non-corrupt data."""
        # Use world_joints if available, else joints
        source = self.world_joints if self.world_joints else self.joints
        if not source: return False
        
        # 1. Hips check (Critical for Root)
        lh, rh = source.get("LEFT_HIP"), source.get("RIGHT_HIP")
        if not lh or not rh or lh.confidence < 0.3 or rh.confidence < 0.3:
            return False
            
        # 2. Shoulders check (Critical for Spine)
        ls, rs = source.get("LEFT_SHOULDER"), source.get("RIGHT_SHOULDER")
        if not ls or not rs or ls.confidence < 0.3 or rs.confidence < 0.3:
            return False
            
        return True

    def get_world_coords(self, scale_factor=5.0) -> Dict[str, np.ndarray]:
        """
        --- NEXUS PATCH 2: AUTO-HEIGHT NORMALIZER ---
        1. Correct Axis Mapping: X=x, Y=-z, Z=y
        2. Auto-Scale: Prevents 'nested spheres' by ensuring human proportions.
        """
        # Source Priority: World Meters > Normalized 
        has_world = bool(self.world_joints)
        source = self.world_joints if has_world else self.joints
        if not source or not self.is_valid(): return {}

        # 1. HIPS ROOT (Central Pivot)
        lh, rh = source["LEFT_HIP"], source["RIGHT_HIP"]
        root = np.array([(lh.x + rh.x) / 2, (lh.y + rh.y) / 2, (lh.z + rh.z) / 2])
        
        # 2. AUTO-SCALE CALCULATION (Keep skeleton readable)
        # We target a height of approx 2.0 units in the world.
        actual_height = 1.0
        if "LEFT_SHOULDER" in source and "LEFT_HIP" in source:
            # Measure torso length as a proxy for scale
            sh, hp = source["LEFT_SHOULDER"], source["LEFT_HIP"]
            actual_height = np.sqrt((sh.x-hp.x)**2 + (sh.y-hp.y)**2 + (sh.z-hp.z)**2)
        
        # If height is too small (e.g. normalized [0,1] or missing depth), boost scale
        if has_world:
            final_scale = scale_factor 
        else:
            # Normalized Fallback: Height of torso is typically 0.3-0.4.
            # We want that 0.3 to become 2.0 units on grid.
            final_scale = 5.0 / actual_height if actual_height > 0.05 else 20.0

        world_points = {}
        for name, joint in source.items():
            # 3. RELATIVE TO ROOT
            lx = (joint.x - root[0]) * final_scale
            ly = (joint.y - root[1]) * final_scale
            lz = (joint.z - root[2]) * final_scale
            
            # 4. FINAL UPRIGHT MAPPING (NEXUS STANDARD)
            # MediaPipe: x=right, y=down, z=depth
            # PyQtGraph: X=horiz, Y=depth, Z=up
            
            pg_x = lx   # Right -> Right
            pg_y = lz   # Depth -> Depth
            pg_z = -ly  # -Down -> UP (Karakteri ayağa kaldırır)
            
            world_points[name] = np.array([pg_x, pg_y, pg_z])
            
        return world_points

    def get_hip_center(self) -> Optional[np.ndarray]:
        hl = self.joints.get("LEFT_HIP")
        hr = self.joints.get("RIGHT_HIP")
        if hl and hr:
            return np.array([(hl.x+hr.x)/2, (hl.y+hr.y)/2, (hl.z+hr.z)/2])
        return None

class UnifiedExporter:
    @staticmethod
    def save_recording(frames: List[MocapFrame], filepath: str):
        data = [f.to_dict() for f in frames]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return filepath

    @staticmethod
    def load_recording(filepath: str) -> List[MocapFrame]:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [MocapFrame.from_dict(f) for f in data]
