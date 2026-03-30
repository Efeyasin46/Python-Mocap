from typing import List, Dict, Optional, Any
import numpy as np
from dataclasses import dataclass

@dataclass
class BoneInfo:
    name: str
    parent: Optional[str]
    length: float = 0.0

class SkeletonHierarchy:
    def __init__(self):
        # 🟢 AAA HUMAN HIERARCHY (UPGRADED)
        self.bones: Dict[str, BoneInfo] = {
            "HIPS": BoneInfo("HIPS", None),
            
            # Spine Chain
            "SPINE": BoneInfo("SPINE", "HIPS"),
            "CHEST": BoneInfo("CHEST", "SPINE"),
            "NECK": BoneInfo("NECK", "CHEST"),
            "HEAD": BoneInfo("HEAD", "NECK"),
            
            # Left Arm
            "LEFT_SHOULDER": BoneInfo("LEFT_SHOULDER", "CHEST"),
            "LEFT_ELBOW": BoneInfo("LEFT_ELBOW", "LEFT_SHOULDER"),
            "LEFT_WRIST": BoneInfo("LEFT_WRIST", "LEFT_ELBOW"),
            
            # Right Arm
            "RIGHT_SHOULDER": BoneInfo("RIGHT_SHOULDER", "CHEST"),
            "RIGHT_ELBOW": BoneInfo("RIGHT_ELBOW", "RIGHT_SHOULDER"),
            "RIGHT_WRIST": BoneInfo("RIGHT_WRIST", "RIGHT_ELBOW"),
            
            # Left Leg
            "LEFT_HIP": BoneInfo("LEFT_HIP", "HIPS"),
            "LEFT_KNEE": BoneInfo("LEFT_KNEE", "LEFT_HIP"),
            "LEFT_ANKLE": BoneInfo("LEFT_ANKLE", "LEFT_KNEE"),
            
            # Right Leg
            "RIGHT_HIP": BoneInfo("RIGHT_HIP", "HIPS"),
            "RIGHT_KNEE": BoneInfo("RIGHT_KNEE", "RIGHT_HIP"),
            "RIGHT_ANKLE": BoneInfo("RIGHT_ANKLE", "RIGHT_KNEE"),
        }

    def get_parent(self, bone_name: str) -> Optional[str]:
        if bone_name in self.bones:
            return self.bones[bone_name].parent
        return None

    def enforce_lengths(self, points: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Enforce bone length stability to prevent collapses.
        """
        new_points = points.copy()
        # Traverse hierarchy from root down
        for name, info in self.bones.items():
            if info.parent and name in new_points and info.parent in new_points:
                parent_pos = new_points[info.parent]
                child_pos = new_points[name]
                
                # Direction vector
                vec = child_pos - parent_pos
                length = np.linalg.norm(vec)
                
                if length < 0.001: continue # Safety clamp
                
                # If we have a target length (from calibration), enforce it
                if info.length > 0:
                    # Target strict length vector
                    target_vec = (vec / length) * info.length
                    
                    # v2.8 Blend Factor (0.0 to 1.0)
                    # If we simply overwrite, jitter becomes snapping.
                    # We blend slowly if the difference is small, snap if it's huge (prevent tearing)
                    diff_ratio = abs(length - info.length) / info.length
                    blend = 0.5 if diff_ratio < 0.2 else 0.9 # Aggressively snap if stretched > 20%
                    
                    final_vec = vec * (1 - blend) + target_vec * blend
                    new_points[name] = parent_pos + final_vec
                    
        return new_points

    def set_lengths_from_calibration(self, calibration_data: Dict[str, Any]):
        # Map JSON calibration keys to bone names
        mapping = {
            "shoulder_width": ["LEFT_SHOULDER", "RIGHT_SHOULDER"],
            "arm_upper": ["LEFT_ELBOW", "RIGHT_ELBOW"],
            "arm_lower": ["LEFT_WRIST", "RIGHT_WRIST"],
            "leg_upper": ["LEFT_KNEE", "RIGHT_KNEE"],
            "leg_lower": ["LEFT_ANKLE", "RIGHT_ANKLE"],
            "torso": ["CHEST", "SPINE"]
        }
        
        skeleton_data = calibration_data.get("skeleton", {})
        for cal_key, bone_names in mapping.items():
            if cal_key in skeleton_data:
                length = skeleton_data[cal_key]
                for b_name in bone_names:
                    if b_name in self.bones:
                        self.bones[b_name].length = length
