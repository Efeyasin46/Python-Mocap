import numpy as np
from typing import Dict, Any, List
from core.frame_model import MocapFrame, Joint
from core.logger import engine_logger

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

class AdaptiveSmoothingFilter:
    """
    v2.7 Pro: Smarter smoothing that reduces lag during fast movements.
    - High Velocity -> Lower Alpha (Less smoothing, higher responsiveness)
    - Low Velocity -> Higher Alpha (More smoothing, max stability)
    """
    def __init__(self, min_alpha: float = 0.2, max_alpha: float = 0.8, velocity_threshold: float = 0.05):
        self.min_alpha = min_alpha
        self.max_alpha = max_alpha
        self.v_threshold = velocity_threshold
        self.prev_joints: Dict[str, np.ndarray] = {}

    def process(self, joints: Dict[str, Joint]) -> Dict[str, Joint]:
        smoothed = {}
        for name, joint in joints.items():
            curr_pos = np.array([joint.x, joint.y, joint.z])
            if name in self.prev_joints:
                # Calculate local velocity
                vel = np.linalg.norm(curr_pos - self.prev_joints[name])
                # Adaptive Alpha: Scale between min/max based on velocity
                # If vel is high, we want more 'current' data (low smoothing)
                # If vel is low, we want more 'prev' data (high smoothing)
                alpha = np.clip(1.0 - (vel / self.v_threshold), self.min_alpha, self.max_alpha)
                new_pos = alpha * self.prev_joints[name] + (1 - alpha) * curr_pos
            else:
                new_pos = curr_pos
            
            self.prev_joints[name] = new_pos
            smoothed[name] = Joint(x=float(new_pos[0]), y=float(new_pos[1]), z=float(new_pos[2]), confidence=joint.confidence)
        return smoothed

class MotionStabilizer:
    """
    v2.7 FootLock System:
    Pinning foot positions to floor when velocity is near zero.
    """
    def __init__(self, lock_threshold: float = 0.002, still_threshold: float = 0.005):
        self.lock_threshold = lock_threshold
        self.still_threshold = still_threshold
        self.pinned_positions: Dict[str, np.ndarray] = {}
        self.prev_joints: Dict[str, np.ndarray] = {}

    def process(self, joints: Dict[str, Joint]) -> Dict[str, Joint]:
        stabilized = {}
        # Foot Landmarks
        foot_joints = ["LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX"]
        
        for name, joint in joints.items():
            curr_pos = np.array([joint.x, joint.y, joint.z])
            
            if name in foot_joints and name in self.prev_joints:
                velocity = np.linalg.norm(curr_pos - self.prev_joints[name])
                
                if name in self.pinned_positions:
                    # If pinned, only release if it moves significantly
                    if velocity < self.still_threshold:
                        curr_pos = self.pinned_positions[name]
                    else:
                        del self.pinned_positions[name]
                else:
                    # Lock it if it's very still
                    if velocity < self.lock_threshold:
                        self.pinned_positions[name] = curr_pos
            
            self.prev_joints[name] = curr_pos
            stabilized[name] = Joint(x=float(curr_pos[0]), y=float(curr_pos[1]), z=float(curr_pos[2]), confidence=joint.confidence)
            
        return stabilized

class GroundAligner:
    """
    v2.7 Auto Floor Detection.
    """
    @staticmethod
    def align_to_floor(frame: MocapFrame):
        points = frame.world_joints
        if not points: return
        
        # Ground anchors
        anchors = ["LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL"]
        z_min = 100.0
        
        for name in anchors:
            if name in points:
                if points[name].z < z_min: z_min = points[name].z
        
        if z_min < 90.0: # Valid detection
            offset = -z_min
            for joint in points.values():
                joint.z += offset
