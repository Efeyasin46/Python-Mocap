from typing import Dict, Any, Optional
import json
import os
from .logger import engine_logger

class EngineContext:
    """
    Shared runtime state for the MotionForge Engine.
    """
    def __init__(self):
        self.calibration: Dict[str, Any] = {}
        self.current_user: str = "DefaultUser"
        self.is_camera_ready: bool = False
        self.active_recording_path: Optional[str] = None
        
        self.load_calibration()

    def load_calibration(self):
        # Prioritize v2
        paths = ["data/calibration_v2.json", "data/calibration_v1.json"]
        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        self.calibration = json.load(f)
                    engine_logger.info(f"Context: Loaded calibration from {path}")
                    return True
                except Exception as e:
                    engine_logger.error(f"Context: Failed to load {path}: {e}")
        return False

# Global Context Singleton
global_context = EngineContext()
