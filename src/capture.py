from PyQt5.QtCore import QThread, pyqtSignal, Qt
import cv2
import mediapipe as mp
import numpy as np
import os
from datetime import datetime
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint, UnifiedExporter
from core.motion_pipeline import MotionPipeline
from core.constraints import AdaptiveSmoothingFilter, MotionStabilizer, FrameDropCompensator
from core.skeleton import SkeletonHierarchy
from core.mobile_camera import MobileCameraManager, CameraSourceType

# Global MediaPipe References
mp_holistic = mp.solutions.holistic
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

class CaptureThread(QThread):
    frame_ready = pyqtSignal(object)  # Emits MocapFrame
    image_ready = pyqtSignal(np.ndarray) # Emits processed CV2 image for ref
    status_msg = pyqtSignal(str)

    def __init__(self, source_type=CameraSourceType.WEBCAM, source_info=0):
        super().__init__()
        self.source_type = source_type
        self.source_info = source_info
        self.running = True
        self.is_recording = False
        self.recorded_frames = []
        self.video_writer = None
        
        # Engine Components
        self.pipeline = MotionPipeline()
        self.drop_compensator = FrameDropCompensator(max_drop_frames=3)
        self.smoother = AdaptiveSmoothingFilter(min_alpha=0.4, max_alpha=0.8)
        self.stabilizer = MotionStabilizer(lock_threshold=0.003)
        self.hierarchy = SkeletonHierarchy()

    def stop(self):
        self.running = False
        self.wait()

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.recorded_frames = []
        self.is_recording = True
        self.pipeline.reset()
        self.status_msg.emit("Recording STARTED")

    def stop_recording(self):
        self.is_recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"data/motion_nexus_{timestamp}.json"
        UnifiedExporter.save_recording(self.recorded_frames, out_path)
        self.status_msg.emit(f"Recording SAVED: {os.path.basename(out_path)}")

    def run(self):
        engine_logger.info(f"CaptureThread started with {self.source_type}")
        
        # 1. Camera Setup
        cap = None
        if self.source_type == CameraSourceType.MOBILE_WIFI:
            cap = MobileCameraManager.connect_wifi(self.source_info)
        elif self.source_type == CameraSourceType.MOBILE_USB:
            cap = MobileCameraManager.connect_usb(preferred_index=1)
            
        if cap is None and self.source_type != CameraSourceType.MOBILE_WIFI:
            for idx in [0, 1, 2]:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
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
            
            while self.running and cap.isOpened():
                success, image = cap.read()
                if not success: break

                # Auto-Exposure
                avg_brightness = np.mean(image)
                if 0 < avg_brightness < 50:
                    image = cv2.LUT(image, gamma_table)

                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                results = holistic.process(image_rgb)

                # Process Frame
                frame = self.pipeline.process_frame(results)
                
                if results.pose_landmarks:
                    for i, lm in enumerate(results.pose_landmarks.landmark):
                        name = mp_holistic.PoseLandmark(i).name
                        frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                
                if results.pose_world_landmarks:
                    for i, lm in enumerate(results.pose_world_landmarks.landmark):
                        name = mp_holistic.PoseLandmark(i).name
                        frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)

                # Guardrails
                frame.joints = self.drop_compensator.process(frame.joints)
                frame.joints = self.smoother.process(frame.joints)
                frame.joints = self.stabilizer.process(frame.joints)
                frame.source = self.source_type

                # Emit Data
                self.frame_ready.emit(frame)
                
                # Draw for Reference UI
                if results.pose_landmarks:
                    mp_drawing.draw_landmarks(
                        image, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS,
                        landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                    )
                
                self.image_ready.emit(cv2.flip(image, 1))

                if self.is_recording:
                    if frame.is_valid():
                        self.recorded_frames.append(frame)
                    # Video recording logic could go here if needed

            cap.release()
            engine_logger.info("CaptureThread stopped")

def main():
    # Legacy entry point for testing
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    thread = CaptureThread()
    thread.start()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
