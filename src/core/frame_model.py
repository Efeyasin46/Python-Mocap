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
        
        # Check if critical joints exist and are visible
        critical = ["LEFT_HIP", "RIGHT_HIP"]
        for c in critical:
            j = source.get(c)
            if not j or np.isnan(j.x) or j.confidence < 0.3:
                return False
        return True

    def get_world_coords(self) -> Dict[str, np.ndarray]:
        """
        Converts MediaPipe World (Meters) to Engine Space with requested mapping:
        X_eng = X_mp
        Y_eng = -Z_mp (Corrects depth to vertical UP)
        Z_eng = Y_mp (Forward/Back)
        """
        source = self.world_joints if self.world_joints else self.joints
        if not source: return {}

        # 1. Calculate ROOT (Midpoint of Hips)
        lh = source.get("LEFT_HIP")
        rh = source.get("RIGHT_HIP")
        if not lh or not rh: return {}
        
        root_x = (lh.x + rh.x) / 2
        root_y = (lh.y + rh.y) / 2
        root_z = (lh.z + rh.z) / 2
        
        world_points = {}
        for name, joint in source.items():
            # 2. To Local Space (Relative to Hips)
            lx = joint.x - root_x
            ly = joint.y - root_y
            lz = joint.z - root_z
            
            # 3. Apply User's Axis Mapping: X=X, Y=-Z, Z=Y
            ex = lx
            ey = -lz # -Depth -> UP
            ez = ly  # Vertical -> Forward/Back
            
            world_points[name] = np.array([ex, ey, ez])
            
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
