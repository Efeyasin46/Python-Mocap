import copy
import os
import sys
import threading
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from core.constraints import AdaptiveSmoothingFilter, FrameDropCompensator, MotionStabilizer
from core.frame_model import Joint, UnifiedExporter, filter_joints_by_confidence
from core.logger import engine_logger
from core.mobile_camera import CameraSourceType, MobileCameraManager
from core.motion_pipeline import MotionPipeline
from core.skeleton import SkeletonHierarchy

# Global MediaPipe References
mp_holistic = mp.solutions.holistic
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

class CaptureThread(QThread):
    frame_ready = pyqtSignal(object)  # Emits MocapFrame
    image_ready = pyqtSignal(np.ndarray) # Emits processed CV2 image for ref
    status_msg = pyqtSignal(str)

    def __init__(
        self, source_type=CameraSourceType.WEBCAM, source_info=0,
        min_confidence=0.65, capture_mode="full_body",
    ):
        super().__init__()
        self.source_type = source_type
        self.source_info = source_info
        self.running = True
        self.is_recording = False
        self.recorded_frames = []
        self._record_lock = threading.Lock()
        self.video_writer = None
        self.min_confidence = float(min_confidence)
        self.capture_mode = capture_mode
        
        # Engine Components
        self.pipeline = MotionPipeline()
        # Do not repeat stale coordinates when tracking disappears; missing data stays missing.
        self.drop_compensator = FrameDropCompensator(max_drop_frames=0)
        self.smoother = AdaptiveSmoothingFilter(min_alpha=0.4, max_alpha=0.8)
        self.stabilizer = MotionStabilizer(lock_threshold=0.003)
        self.hierarchy = SkeletonHierarchy()

    def stop(self):
        self.running = False
        self.requestInterruption()
        self.wait(3000)

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        with self._record_lock:
            self.recorded_frames = []
            self.is_recording = True
        self.pipeline.reset()
        self.status_msg.emit("Recording STARTED")

    def stop_recording(self, output_path=None):
        with self._record_lock:
            self.is_recording = False
            frames = list(self.recorded_frames)
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("data", exist_ok=True)
            output_path = f"data/motion_nexus_{timestamp}.json"
        parent = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(parent, exist_ok=True)
        UnifiedExporter.save_recording(frames, output_path)
        self.status_msg.emit(f"Recording SAVED: {os.path.basename(output_path)}")

    def run(self):
        try:
            self._run_capture()
        except Exception as exc:
            engine_logger.exception("Camera capture failed")
            self.status_msg.emit(f"ERROR: Camera capture failed: {exc}")

    def _run_capture(self):
        engine_logger.info(f"CaptureThread started with {self.source_type}")
        
        # 1. Camera Setup
        cap = None
        if self.source_type == CameraSourceType.MOBILE_WIFI:
            cap = MobileCameraManager.connect_wifi(self.source_info)
        elif self.source_type == CameraSourceType.MOBILE_USB:
            cap = MobileCameraManager.connect_usb(preferred_index=1)
            
        if cap is None and self.source_type != CameraSourceType.MOBILE_WIFI:
            for idx in [0, 1, 2]:
                if os.name == "nt":
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                elif sys.platform == "darwin":
                    cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
                else:
                    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                if cap.isOpened(): break
        
        if not cap or not cap.isOpened():
            self.status_msg.emit("ERROR: No Camera Found")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Pre-compute Gamma
        gamma_table = np.array([((i / 255.0) ** (1.0/1.3)) * 255 for i in np.arange(0, 256)]).astype("uint8")

        with mp_holistic.Holistic(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=1,
            refine_face_landmarks=True
        ) as holistic:
            
            while self.running and not self.isInterruptionRequested() and cap.isOpened():
                success, image = cap.read()
                if not success:
                    if self.running and not self.isInterruptionRequested():
                        self.status_msg.emit(
                            "ERROR: Camera stopped providing frames. Check the cable and camera connection."
                        )
                    break

                # Auto-Exposure
                avg_brightness = np.mean(image)
                if 0 < avg_brightness < 50:
                    image = cv2.LUT(image, gamma_table)

                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                results = holistic.process(image_rgb)

                # Process Frame
                frame = self.pipeline.process_frame(results)

                if self.capture_mode == "face":
                    frame.meta["capture_mode"] = "face"
                    if results.face_landmarks:
                        for i, lm in enumerate(results.face_landmarks.landmark):
                            frame.joints[f"FACE_{i:03d}"] = Joint(
                                x=lm.x, y=lm.y, z=lm.z, confidence=1.0
                            )
                elif results.pose_landmarks:
                    for i, lm in enumerate(results.pose_landmarks.landmark):
                        name = mp_holistic.PoseLandmark(i).name
                        frame.joints[name] = Joint(
                            x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility
                        )
                    frame.joints = filter_joints_by_confidence(
                        frame.joints, self.min_confidence
                    )
                
                if self.capture_mode != "face" and results.pose_world_landmarks:
                    for i, lm in enumerate(results.pose_world_landmarks.landmark):
                        name = mp_holistic.PoseLandmark(i).name
                        frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                    frame.world_joints = filter_joints_by_confidence(
                        frame.world_joints, self.min_confidence
                    )

                # Guardrails
                if self.capture_mode != "face":
                    frame.world_joints = self.drop_compensator.process(frame.world_joints)
                    frame.world_joints = self.smoother.process(frame.world_joints)
                    frame.world_joints = self.stabilizer.process(frame.world_joints)
                frame.source = self.source_type

                # Emit Data
                self.frame_ready.emit(frame)
                
                # Draw for Reference UI
                if self.capture_mode == "face" and results.face_landmarks:
                    mp_drawing.draw_landmarks(
                        image,
                        results.face_landmarks,
                        mp.solutions.face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style(),
                    )
                elif results.pose_landmarks:
                    visible_pose = copy.deepcopy(results.pose_landmarks)
                    for landmark in visible_pose.landmark:
                        if landmark.visibility < self.min_confidence:
                            landmark.visibility = 0.0
                    mp_drawing.draw_landmarks(
                        image, visible_pose, mp_holistic.POSE_CONNECTIONS,
                        landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                    )
                
                self.image_ready.emit(cv2.flip(image, 1))

                with self._record_lock:
                    if self.is_recording and frame.is_valid():
                        self.recorded_frames.append(frame)
                    # Video recording logic could go here if needed

            cap.release()
            if self.is_recording:
                self.stop_recording()
            engine_logger.info("CaptureThread stopped")

def main():
    # Legacy entry point for testing
    import sys

    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    thread = CaptureThread()
    thread.start()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
