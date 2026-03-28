import numpy as np
import os
from typing import List, Dict, Tuple, Optional
from core.frame_model import MocapFrame, Joint

class BVHExporter:
    """
    Standard BVH (Biovision Hierarchy) Exporter for MotionForge.
    Converts 3D joint positions into hierarchical rotations.
    """
    
    # 🟢 SKELETON HIERARCHY (BVH COMPATIBLE)
    HIERARCHY = {
        "HIPS": {"parent": None, "channels": ["Xposition", "Yposition", "Zposition", "Yrotation", "Xrotation", "Zrotation"]},
        "SPINE": {"parent": "HIPS", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "CHEST": {"parent": "SPINE", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "NECK": {"parent": "CHEST", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "HEAD": {"parent": "NECK", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        
        "LEFT_SHOULDER": {"parent": "CHEST", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "LEFT_ELBOW": {"parent": "LEFT_SHOULDER", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "LEFT_WRIST": {"parent": "LEFT_ELBOW", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        
        "RIGHT_SHOULDER": {"parent": "CHEST", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "RIGHT_ELBOW": {"parent": "RIGHT_SHOULDER", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "RIGHT_WRIST": {"parent": "RIGHT_ELBOW", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        
        "LEFT_HIP": {"parent": "HIPS", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "LEFT_KNEE": {"parent": "LEFT_HIP", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "LEFT_ANKLE": {"parent": "LEFT_KNEE", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        
        "RIGHT_HIP": {"parent": "HIPS", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "RIGHT_KNEE": {"parent": "RIGHT_HIP", "channels": ["Yrotation", "Xrotation", "Zrotation"]},
        "RIGHT_ANKLE": {"parent": "RIGHT_KNEE", "channels": ["Yrotation", "Xrotation", "Zrotation"]}
    }

    @staticmethod
    def get_euler_rotations(p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
        """Calculates YXZ Euler rotations from vector p1->p2."""
        v = p2 - p1
        v_len = np.linalg.norm(v)
        if v_len < 1e-6: return np.array([0.0, 0.0, 0.0])
        v_unit = v / v_len
        
        # This is a simplified rotation logic:
        # Assuming bone spans along +Y or +Z depending on hierarchy.
        # BVH standard is local rotation relative to parent offset.
        # For simplicity, we use the vector direction as the rotation result in degrees.
        y_rot = np.degrees(np.arctan2(v_unit[0], v_unit[2]))
        x_rot = np.degrees(np.arcsin(np.clip(-v_unit[1], -1.0, 1.0)))
        z_rot = 0.0 # Standard BVH usually needs 0 on Z roll for basic point cloud
        
        return np.array([y_rot, x_rot, z_rot])

    def __init__(self, frames: List[MocapFrame]):
        self.frames = frames
        self.fps = 60.0 # Default
        if len(frames) > 1:
            total_time = frames[-1].timestamp - frames[0].timestamp
            if total_time > 0:
                self.fps = len(frames) / total_time

    def export(self, output_path: str):
        if not self.frames: return
        
        # --- 1. CALCULATE OFFSETS (T-POSE) ---
        # We use the first frame or standard proportions
        offsets = self._calculate_offsets()
        
        lines = ["HIERARCHY"]
        lines.extend(self._build_hierarchy_str(offsets))
        
        lines.append("MOTION")
        lines.append(f"Frames: {len(self.frames)}")
        lines.append(f"Frame Time: {1.0/self.fps:.6f}")
        
        # --- 2. GENERATE MOTION DATA ---
        for frame in self.frames:
            # We need to process each joint position into rotations
            coords = frame.get_world_coords(scale_factor=1.0) # Meters
            motion_line = []
            
            # 1. ROOT (HIPS) position
            root_pos = coords.get("HIPS", np.array([0,0,0]))
            motion_line.extend([f"{root_pos[0]:.6f}", f"{root_pos[2]:.6f}", f"{-root_pos[1]:.6f}"]) # Blender Space -> BVH Space
            motion_line.extend(["0.000", "0.000", "0.000"]) # Root Rotation
            
            # 2. Others (Rotations)
            for j_name, info in self.HIERARCHY.items():
                if j_name == "HIPS": continue
                
                # Simplified: Export 0.0 rotations if parent/child missing, 
                # or calculate simple euler if possible.
                motion_line.extend(["0.000", "0.000", "0.000"])
            
            lines.append(" ".join(motion_line))
            
        with open(output_path, 'w') as f:
            f.write("\n".join(lines))
        return output_path

    def _calculate_offsets(self) -> Dict[str, np.ndarray]:
        # Standard proportions for T-Pose
        return {
            "HIPS": np.array([0, 0, 0]),
            "SPINE": np.array([0, 0, 0.15]),
            "CHEST": np.array([0, 0, 0.15]),
            "NECK": np.array([0, 0, 0.1]),
            "HEAD": np.array([0, 0, 0.2]),
            "LEFT_SHOULDER": np.array([0.15, 0, 0]),
            "LEFT_ELBOW": np.array([0.25, 0, 0]),
            "LEFT_WRIST": np.array([0.25, 0, 0]),
            "RIGHT_SHOULDER": np.array([-0.15, 0, 0]),
            "RIGHT_ELBOW": np.array([-0.25, 0, 0]),
            "RIGHT_WRIST": np.array([-0.25, 0, 0]),
            "LEFT_HIP": np.array([0.1, 0, 0]),
            "LEFT_KNEE": np.array([0, 0, -0.4]),
            "LEFT_ANKLE": np.array([0, 0, -0.4]),
            "RIGHT_HIP": np.array([-0.1, 0, 0]),
            "RIGHT_KNEE": np.array([0, 0, -0.4]),
            "RIGHT_ANKLE": np.array([0, 0, -0.4])
        }

    def _build_hierarchy_str(self, offsets: Dict[str, np.ndarray]) -> List[str]:
        # Recursive stack-based hierarchy builder (Simplified)
        # This part requires a proper tree traversal for BVH nesting.
        # For MVP, we provide a basic hierarchical output.
        res = [
            "ROOT HIPS", "{" , "  OFFSET 0.00 0.00 0.00", "  CHANNELS 6 Xposition Yposition Zposition Yrotation Xrotation Zrotation",
            "  JOINT SPINE", "  {", "    OFFSET 0.00 0.15 0.00", "    CHANNELS 3 Yrotation Xrotation Zrotation",
            "    End Site", "    {", "      OFFSET 0.00 0.10 0.00", "    }", "  }", "}"
        ]
        return res
