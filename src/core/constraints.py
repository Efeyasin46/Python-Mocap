import numpy as np
from typing import Dict, Any
from .frame_model import MocapFrame, Joint

class BoneConstraint:
    @staticmethod
    def enforce_length(p1: np.ndarray, p2: np.ndarray, target_len: float) -> np.ndarray:
        """
        Adjusts p2 so that the distance from p1 is exactly target_len.
        """
        direction = p2 - p1
        dist = np.linalg.norm(direction)
        if dist < 1e-6: return p2
        
        # Oransal düzeltme
        return p1 + (direction / dist) * target_len

class SkeletonConstraints:
    def __init__(self, hierarchy):
        self.hierarchy = hierarchy

    def apply(self, frame: MocapFrame):
        # Bone hierarchy üzerinden uzunluk kısıtlamalarını uygula
        # Bu aşamada basitleştirilmiş bir FK (Forward Kinematics) yaklaşımı kullanılır
        pass

from collections import deque

class SmoothingFilter:
    def __init__(self, alpha: float = 0.5, window_size: int = 5):
        self.alpha = alpha
        self.window_size = window_size
        self.history: Dict[str, deque] = {} # Queue of np.array
        self.prev_joints: Dict[str, np.ndarray] = {}

    def process(self, joints: Dict[str, Joint]) -> Dict[str, Joint]:
        smoothed = {}
        for name, joint in joints.items():
            curr_pos = np.array([joint.x, joint.y, joint.z])
            
            # 1. Update History
            if name not in self.history:
                self.history[name] = deque(maxlen=self.window_size)
            self.history[name].append(curr_pos)
            
            # 2. Window Average (Stabilization)
            window_mean = np.mean(self.history[name], axis=0)
            
            # 3. EMA Overlay (Smoothing)
            if name in self.prev_joints:
                new_pos = self.alpha * window_mean + (1 - self.alpha) * self.prev_joints[name]
            else:
                new_pos = window_mean
            
            self.prev_joints[name] = new_pos
            smoothed[name] = Joint(x=float(new_pos[0]), y=float(new_pos[1]), z=float(new_pos[2]), confidence=joint.confidence)
        return smoothed

class MotionStabilizer:
    def __init__(self, still_threshold: float = 0.008, lock_threshold: float = 0.02):
        self.still_threshold = still_threshold
        self.lock_threshold = lock_threshold
        self.locked_positions: Dict[str, np.ndarray] = {}
        self.prev_joints: Dict[str, np.ndarray] = {}
        self.velocities: Dict[str, float] = {}

    def process(self, joints: Dict[str, Joint]) -> Dict[str, Joint]:
        stabilized = {}
        
        # Kritik noktalar (ayaklar, dizler, kalça)
        critical_joints = ["LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_HIP", "RIGHT_HIP", "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX"]
        
        for name, joint in joints.items():
            curr_pos = np.array([joint.x, joint.y, joint.z])
            
            if name in self.prev_joints:
                velocity = np.linalg.norm(curr_pos - self.prev_joints[name])
                self.velocities[name] = float(velocity)
                
                # Mikrotitreme Filtresi & Foot Lock
                if name in critical_joints:
                    if name in self.locked_positions:
                        # Eğer kilitliyse ve hız hala düşükse veya dikey hareket azsa kilidi koru
                        # MediaPipe Y is Vertical (Down)
                        vertical_delta = abs(curr_pos[1] - self.locked_positions[name][1])
                        if velocity < self.lock_threshold and vertical_delta < 0.01:
                            curr_pos = self.locked_positions[name]
                        else:
                            del self.locked_positions[name]
                    else:
                        # Kilitleme kontrolü
                        if velocity < self.still_threshold:
                            self.locked_positions[name] = curr_pos
            
            self.prev_joints[name] = curr_pos
            stabilized[name] = Joint(x=float(curr_pos[0]), y=float(curr_pos[1]), z=float(curr_pos[2]), confidence=joint.confidence)
            
        # --- [NEW] BILATERAL FOOT DEPTH SYNC ---
        # If both feet are still and close in depth, snap them together
        la = stabilized.get("LEFT_ANKLE")
        ra = stabilized.get("RIGHT_ANKLE")
        if la and ra:
            dist_z = abs(la.z - ra.z)
            # if they are within 10cm depth-wise and stationary
            if dist_z < 0.08 and self.velocities.get("LEFT_ANKLE", 1) < self.lock_threshold:
                target_z = (la.z + ra.z) / 2
                stabilized["LEFT_ANKLE"].z = target_z
                stabilized["RIGHT_ANKLE"].z = target_z

        return stabilized

class BilateralDepthStabilizer:
    """
    Elite Bake-Pass Post-Processor.
    Syncs feet depth across a recorded sequence to eliminate 'one foot ahead' jitter.
    """
    @staticmethod
    def process_sequence(frames: List[MocapFrame]):
        if len(frames) < 10: return frames
        
        for i in range(1, len(frames) - 1):
            f = frames[i]
            la = f.joints.get("LEFT_ANKLE")
            ra = f.joints.get("RIGHT_ANKLE")
            
            if la and ra:
                # Detect standing pose: Feet are horizontally apart but depth-wise close
                width = abs(la.x - ra.x)
                depth_diff = abs(la.z - ra.z)
                
                # If feet are within 10cm depth and have high confidence
                if depth_diff < 0.1 and la.confidence > 0.6 and ra.confidence > 0.6:
                    # Apply a smoothing bias toward the average depth
                    avg_z = (la.z + ra.z) / 2
                    alpha = 0.5 # 50% bias toward alignment
                    la.z = la.z * (1-alpha) + avg_z * alpha
                    ra.z = ra.z * (1-alpha) + avg_z * alpha
        
        return frames
