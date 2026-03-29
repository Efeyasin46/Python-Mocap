import time
from typing import List, Optional, Callable, Any
from core.frame_model import MocapFrame, Joint
from core.logger import engine_logger

class MotionPipeline:
    """
    Unified Engine Controller for Mocap Data Flow.
    Stages: Input -> Smoothing -> Calibration -> Output
    """
    def __init__(self):
        self.stages: List[Callable] = []
        self.is_running = False
        self.frame_count = 0
        self.start_time = time.time()

    def add_stage(self, stage_func: Callable):
        self.stages.append(stage_func)
        engine_logger.info(f"Pipeline: added stage {stage_func.__name__}")

    def process_frame(self, raw_data: Any) -> MocapFrame:
        """
        Main loop for a single frame.
        """
        timestamp = time.time() - self.start_time
        
        # 1. Start with a blank frame or raw conversion
        # This will be refined based on the input source (Realtime or Video)
        frame = MocapFrame(frame_id=self.frame_count, timestamp=timestamp)
        
        # 2. Sequential Processing through stages
        for stage in self.stages:
            try:
                frame = stage(frame, raw_data)
            except Exception as e:
                engine_logger.error(f"Pipeline Stage Error [{stage.__name__}]: {e}")

        self.frame_count += 1
        return frame

    def reset(self):
        self.frame_count = 0
        self.start_time = time.time()
        engine_logger.info("Pipeline Reset.")
