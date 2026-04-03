from PyQt5.QtCore import QThread, pyqtSignal
import cv2
import mediapipe as mp
import os
import glob
from datetime import datetime
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint, UnifiedExporter
from core.motion_pipeline import MotionPipeline
from core.constraints import AdaptiveSmoothingFilter, MotionStabilizer, GroundAligner, FrameDropCompensator, OfflinePostProcessor
from core.skeleton import SkeletonHierarchy

# Global MediaPipe References
mp_holistic = mp.solutions.holistic

class BakeThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str) # Emits output filename
    status = pyqtSignal(str)

    def __init__(self, input_video):
        super().__init__()
        self.input_video = input_video
        self.running = True

    def run(self):
        if not self.input_video or not os.path.exists(self.input_video):
            self.status.emit("ERROR: Invalid Input")
            return

        self.status.emit(f"Processing: {os.path.basename(self.input_video)}")
        
        pipeline = MotionPipeline()
        drop_compensator = FrameDropCompensator(max_drop_frames=5)
        smoother = AdaptiveSmoothingFilter(min_alpha=0.3, max_alpha=0.9)
        stabilizer = MotionStabilizer(lock_threshold=0.005, still_threshold=0.01)
        hierarchy = SkeletonHierarchy()

        cap = cv2.VideoCapture(self.input_video)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        baked_frames = []

        with mp_holistic.Holistic(
            model_complexity=2,
            refine_face_landmarks=True 
        ) as holistic:
            
            frame_idx = 0
            while self.running and cap.isOpened():
                success, frame = cap.read()
                if not success: break
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = holistic.process(frame_rgb)
                
                m_frame = pipeline.process_frame(results)
                
                if results.pose_landmarks:
                    for i, lm in enumerate(results.pose_landmarks.landmark):
                        name = mp_holistic.PoseLandmark(i).name
                        m_frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                
                if results.pose_world_landmarks:
                    for i, lm in enumerate(results.pose_world_landmarks.landmark):
                        name = mp_holistic.PoseLandmark(i).name
                        m_frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                
                m_frame.joints = drop_compensator.process(m_frame.joints)
                m_frame.joints = smoother.process(m_frame.joints)
                m_frame.joints = stabilizer.process(m_frame.joints)

                if m_frame.is_valid():
                    baked_frames.append(m_frame)
                
                frame_idx += 1
                prog_val = int((frame_idx / total_frames) * 100)
                self.progress.emit(prog_val)

        cap.release()
        
        if not self.running: return

        # Post-Processing
        self.status.emit("Applying Anti-Jitter...")
        baked_frames = OfflinePostProcessor.correct_depth_jitter(baked_frames)
        
        self.status.emit("Aligning to Floor...")
        for frame in baked_frames:
            GroundAligner.align_to_floor(frame)
        
        output_filename = f"data/motion_baked_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        UnifiedExporter.save_recording(baked_frames, output_filename)
        
        self.finished.emit(output_filename)
        self.status.emit("Baking Complete.")

def main():
    # Placeholder for direct testing
    pass

if __name__ == '__main__':
    main()
