import mediapipe as mp
import cv2
from PyQt5.QtCore import QThread, pyqtSignal
import os
import glob
from datetime import datetime
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint, UnifiedExporter
from core.motion_pipeline import MotionPipeline
from core.bake_filters import BakeFilters
from core.skeleton import SkeletonHierarchy

# Global MediaPipe References
mp_holistic = mp.solutions.holistic

class BakeThread(QThread):
    progress = pyqtSignal(int)
    bake_done = pyqtSignal(str) # Emits output filename; preserve QThread.finished
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
        filters = BakeFilters()
        baked_frames = []

        if os.path.splitext(self.input_video)[1].lower() == ".json":
            # A live capture is already motion data. Re-bake its landmarks
            # directly instead of asking the user to provide the original MP4.
            try:
                frames = UnifiedExporter.load_recording(self.input_video)
                total_frames = len(frames)
                for index, frame in enumerate(frames):
                    if not self.running or self.isInterruptionRequested():
                        return
                    if filters.process_frame(frame):
                        baked_frames.append(frame)
                    self.progress.emit(int((index + 1) * 100 / max(total_frames, 1)))
            except Exception as exc:
                self.status.emit(f"ERROR: Could not read motion JSON: {exc}")
                return
        else:
            cap = cv2.VideoCapture(self.input_video)
            if not cap.isOpened():
                self.status.emit("ERROR: Could not open video")
                return
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if not fps or fps <= 0:
                fps = 30.0

            with mp_holistic.Holistic(
                model_complexity=2,
                refine_face_landmarks=True
            ) as holistic:
            
                frame_idx = 0
                while self.running and not self.isInterruptionRequested() and cap.isOpened():
                    success, image = cap.read()
                    if not success:
                        break
                
                    frame_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    results = holistic.process(frame_rgb)
                
                    m_frame = MocapFrame(frame_id=frame_idx, timestamp=frame_idx / fps)
                
                    if results.pose_landmarks:
                        for i, lm in enumerate(results.pose_landmarks.landmark):
                            name = mp_holistic.PoseLandmark(i).name
                            m_frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                
                    if results.pose_world_landmarks:
                        for i, lm in enumerate(results.pose_world_landmarks.landmark):
                            name = mp_holistic.PoseLandmark(i).name
                            m_frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                
                    if filters.process_frame(m_frame):
                        baked_frames.append(m_frame)
                
                    frame_idx += 1
                    self.progress.emit(int(frame_idx * 100 / max(total_frames, 1)))

            cap.release()
        
        if not self.running: return

        # Post-Processing: depth anti-jitter, then one constant floor offset
        self.status.emit("Applying Anti-Jitter and aligning to floor...")
        baked_frames = BakeFilters.finalize(baked_frames)
        
        os.makedirs("data", exist_ok=True)
        output_filename = f"data/motion_baked_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        UnifiedExporter.save_recording(baked_frames, output_filename)
        
        self.bake_done.emit(output_filename)
        self.status.emit("Baking Complete.")

def main():
    from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox
    import sys
    app = QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else QFileDialog.getOpenFileName(
        None, "Choose a video or motion recording", "",
        "MotionForge and video (*.json *.mp4 *.mov *.avi *.mkv)"
    )[0]
    if not path:
        return
    thread = BakeThread(path)
    thread.status.connect(print)
    thread.progress.connect(lambda value: print(f"Progress: {value}%"))
    thread.bake_done.connect(lambda output: QMessageBox.information(
        None, "MotionForge", f"Processed motion saved to:\n{os.path.abspath(output)}"
    ))
    thread.start()
    app.exec_()

if __name__ == '__main__':
    main()
