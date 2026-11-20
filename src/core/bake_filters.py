"""Headless filter chain used by the offline bake.

Extracted from ``bake.py`` so it can be tested without MediaPipe / Qt. Behaviour
is unchanged: per-frame filters run on ``world_joints`` (what the viewer and the
exporters consume), then clip-level depth de-jitter and one constant floor offset.
"""
from typing import Dict, List

from core.constraints import (
    AdaptiveSmoothingFilter,
    FrameDropCompensator,
    GroundAligner,
    MotionStabilizer,
    OfflinePostProcessor,
)
from core.frame_model import Joint, MocapFrame, filter_joints_by_confidence


class BakeFilters:
    def __init__(self, min_confidence: float = 0.65):
        self.min_confidence = min_confidence
        # A missing body must not be copied forward as if it were observed.
        self.drop_compensator = FrameDropCompensator(max_drop_frames=0)
        self.smoother = AdaptiveSmoothingFilter(min_alpha=0.3, max_alpha=0.9)
        self.stabilizer = MotionStabilizer(lock_threshold=0.005, still_threshold=0.01)

    def filter_world(self, world_joints: Dict[str, Joint]) -> Dict[str, Joint]:
        """Per-frame, order matters: drop compensation -> smoothing -> foot lock."""
        joints = self.drop_compensator.process(world_joints)
        joints = self.smoother.process(joints)
        return self.stabilizer.process(joints)

    def process_frame(self, frame: MocapFrame) -> bool:
        """Filters ``frame`` in place; returns whether it should be kept."""
        frame.joints = filter_joints_by_confidence(frame.joints, self.min_confidence)
        frame.world_joints = filter_joints_by_confidence(
            frame.world_joints, self.min_confidence
        )
        frame.world_joints = self.filter_world(frame.world_joints)
        return frame.is_valid()

    @staticmethod
    def finalize(frames: List[MocapFrame]) -> List[MocapFrame]:
        """Clip-level passes: depth jitter, then constant floor alignment."""
        frames = OfflinePostProcessor.correct_depth_jitter(frames)
        GroundAligner.align_clip_to_floor(frames)
        return frames
