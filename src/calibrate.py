import sys
import os
import json
import time
import numpy as np
import cv2
import mediapipe as mp
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint
from core.motion_pipeline import MotionPipeline
from core.constraints import SmoothingFilter

class Gen3Calibration(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MotionForge Pro - NEXUS CALIBRATION (Gen 3)")
        self.setFixedSize(900, 700)
        self.setStyleSheet("background-color: #050505; color: white; font-family: 'Segoe UI';")
        
        # Data Accumulation
        self.collected_samples = 0
        self.MAX_SAMPLES = 50 
        self.measurement_buffer = {
            "shoulder_width": [], "arm_upper": [], "arm_lower": [],
            "leg_upper": [], "leg_lower": [], "torso": []
        }
        
        self.init_ui()
        
        # Engine
        self.pipeline = MotionPipeline()
        self.smoother = SmoothingFilter(alpha=0.5)
        self.cap = cv2.VideoCapture(0)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.engine_step)
        self.timer.start(30)
        
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(model_complexity=2, min_detection_confidence=0.5)

    def init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        
        # Camera Container
        self.video_container = QtWidgets.QLabel("SIGNAL SEARCHING...")
        self.video_container.setAlignment(QtCore.Qt.AlignCenter)
        self.video_container.setFixedSize(800, 500)
        self.video_container.setStyleSheet("border: 1px solid #333; border-radius: 15px; background: #000;")
        layout.addWidget(self.video_container, 0, QtCore.Qt.AlignCenter)
        
        # Dashboard UI
        info_layout = QtWidgets.QHBoxLayout()
        
        # Status Card
        status_box = QtWidgets.QWidget()
        status_box.setStyleSheet("background: #111; border-radius: 8px; padding: 10px;")
        s_layout = QtWidgets.QVBoxLayout(status_box)
        self.status_title = QtWidgets.QLabel("ENGINE READY")
        self.status_title.setStyleSheet("color: #00ffcc; font-weight: bold; font-size: 14px;")
        self.status_msg = QtWidgets.QLabel("Ready to capture body dimensions")
        s_layout.addWidget(self.status_title)
        s_layout.addWidget(self.status_msg)
        info_layout.addWidget(status_box)
        
        # Signal Meter
        self.signal_bar = QtWidgets.QProgressBar()
        self.signal_bar.setOrientation(QtCore.Qt.Vertical)
        self.signal_bar.setFixedWidth(20)
        self.signal_bar.setStyleSheet("QProgressBar::chunk { background: #ff00ff; }")
        info_layout.addWidget(self.signal_bar)
        
        layout.addLayout(info_layout)
        
        # Progress
        self.main_progress = QtWidgets.QProgressBar()
        self.main_progress.setFixedHeight(10)
        self.main_progress.setStyleSheet("QProgressBar::chunk { background: #00ffcc; }")
        layout.addWidget(self.main_progress)

    def engine_step(self):
        ret, frame = self.cap.read()
        if not ret: return
        
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)
        
        m_frame = self.pipeline.process_frame(results)
        if results.pose_landmarks:
            for i, lm in enumerate(results.pose_landmarks.landmark):
                name = self.mp_pose.PoseLandmark(i).name
                m_frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
        
        m_frame.joints = self.smoother.process(m_frame.joints)
        
        self.process_calibration(m_frame)
        self.render_view(frame, results)

    def process_calibration(self, frame: MocapFrame):
        # 1. Pose Score (Similarity to T-Pose)
        score = self.calculate_pose_score(frame)
        self.signal_bar.setValue(int(score * 100))
        
        if score > 0.65: # Relaxed trigger
            self.status_title.setText("● CAPTURING SIGNAL")
            self.status_title.setStyleSheet("color: #ff00ff;")
            self.status_msg.setText("Hold T-Pose. Data is accumulating...")
            
            # Accumulate
            self.accumulate_data(frame)
            self.collected_samples += 1
            
            progress = int((self.collected_samples / self.MAX_SAMPLES) * 100)
            self.main_progress.setValue(progress)
            
            if self.collected_samples >= self.MAX_SAMPLES:
                self.save_and_exit()
        else:
            self.status_title.setText("SIGNAL SEARCH")
            self.status_title.setStyleSheet("color: #00ffcc;")
            self.status_msg.setText("Please stand in a T-Pose (Arms Spread Out)")

    def calculate_pose_score(self, frame: MocapFrame) -> float:
        j = frame.joints
        needed = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"]
        if not all(k in j for k in needed): return 0.0
        
        # Horizontal alignment score
        score = 0.0
        ls, rs = j["LEFT_SHOULDER"], j["RIGHT_SHOULDER"]
        le, re = j["LEFT_ELBOW"], j["RIGHT_ELBOW"]
        lw, rw = j["LEFT_WRIST"], j["RIGHT_WRIST"]
        
        # Arms level check
        l_diff = abs(le.y - ls.y) + abs(lw.y - ls.y)
        r_diff = abs(re.y - rs.y) + abs(rw.y - rs.y)
        
        level_score = max(0, 1.0 - (l_diff + r_diff)) # Simple diff based
        
        # Extension check
        ext_score = 1.0 if (lw.x < ls.x and rw.x > rs.x) else 0.0
        
        # Confidence multiplier
        avg_conf = sum(j[k].confidence for k in needed) / len(needed)
        
        return (level_score * 0.7 + ext_score * 0.3) * avg_conf

    def accumulate_data(self, frame: MocapFrame):
        j = frame.joints
        def dist(a, b): return np.linalg.norm(np.array([j[a].x-j[b].x, j[a].y-j[b].y, j[a].z-j[b].z]))
        
        self.measurement_buffer["shoulder_width"].append(dist("LEFT_SHOULDER", "RIGHT_SHOULDER"))
        self.measurement_buffer["arm_upper"].append((dist("LEFT_SHOULDER", "LEFT_ELBOW") + dist("RIGHT_SHOULDER", "RIGHT_ELBOW"))/2)
        self.measurement_buffer["arm_lower"].append((dist("LEFT_ELBOW", "LEFT_WRIST") + dist("RIGHT_ELBOW", "RIGHT_WRIST"))/2)
        self.measurement_buffer["leg_upper"].append((dist("LEFT_HIP", "LEFT_KNEE") + dist("RIGHT_HIP", "RIGHT_KNEE"))/2)
        self.measurement_buffer["leg_lower"].append((dist("LEFT_KNEE", "LEFT_ANKLE") + dist("RIGHT_KNEE", "RIGHT_ANKLE"))/2)
        
        sh_mid = (np.array([j["LEFT_SHOULDER"].x, j["LEFT_SHOULDER"].y]) + np.array([j["RIGHT_SHOULDER"].x, j["RIGHT_SHOULDER"].y]))/2
        hp_mid = (np.array([j["LEFT_HIP"].x, j["LEFT_HIP"].y]) + np.array([j["RIGHT_HIP"].x, j["RIGHT_HIP"].y]))/2
        self.measurement_buffer["torso"].append(np.linalg.norm(sh_mid - hp_mid))

    def save_and_exit(self):
        self.timer.stop()
        final_skeleton = {k: float(np.median(v)) for k, v in self.measurement_buffer.items()}
        output = {
            "version": "3.0",
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "height_ratio": final_skeleton["torso"] + final_skeleton["leg_upper"] + final_skeleton["leg_lower"],
                "engine_version": "NEXUS-Gen3"
            },
            "skeleton": final_skeleton
        }
        
        with open("data/calibration_v2.json", "w") as f:
            json.dump(output, f, indent=4)
            
        QtWidgets.QMessageBox.information(self, "CALIBRATION COMPLETE", "System stabilized. Nexus v3 parameters locked.")
        self.close()

    def render_view(self, frame, results):
        if results.pose_landmarks:
            mp.solutions.drawing_utils.draw_landmarks(frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS)
            
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_image = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_BGR888)
        self.video_container.setPixmap(QtGui.QPixmap.fromImage(qt_image).scaled(800, 500, QtCore.Qt.KeepAspectRatio))

    def closeEvent(self, event):
        self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    nexus = Gen3Calibration()
    nexus.show()
    sys.exit(app.exec_())
