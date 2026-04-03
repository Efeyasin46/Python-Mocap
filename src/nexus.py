import sys
import os
import time
from PyQt5 import QtCore, QtGui, QtWidgets
from ui.style import NexusStyle
from ui.components import ControlPanelWidget, ReferenceCameraWidget, NexusTimelineWidget
from viewer import NexusViewport
from capture import CaptureThread
from bake import BakeThread
from core.mobile_camera import CameraSourceType
from core.logger import engine_logger

class MotionForgeNexus(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MOTIONFORGE NEXUS v3.0 - PROFESSIONAL MOCAP STUDIO")
        self.resize(1600, 900)
        self.setStyleSheet(NexusStyle.QSS)
        
        # Engine Threads
        self.capture_thread = None
        self.bake_thread = None
        
        self.init_ui()
        self.setup_connections()
        
        engine_logger.info("Nexus v3.0 Core Initialized")

    def init_ui(self):
        self.central = QtWidgets.QWidget()
        self.setCentralWidget(self.central)
        self.main_layout = QtWidgets.QHBoxLayout(self.central)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(0)
        
        # --- LEFT PANEL (CONTROLS) ---
        self.left_panel = ControlPanelWidget("Controls")
        self.main_layout.addWidget(self.left_panel)
        
        self.left_panel.add_section("Source Selection")
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems(["Webcam (Standard)", "Mobile (USB/Virtual)", "Mobile (WiFi/IP)"])
        self.left_panel.add_widget(self.source_combo)
        
        self.ip_input = QtWidgets.QLineEdit("192.168.1.55:8080")
        self.ip_input.setPlaceholderText("IP:Port for WiFi")
        self.ip_input.setVisible(False)
        self.left_panel.add_widget(self.ip_input)
        self.source_combo.currentIndexChanged.connect(lambda i: self.ip_input.setVisible(i == 2))
        
        self.btn_connect = QtWidgets.QPushButton("⚡ CONNECT ENGINE")
        self.btn_connect.setObjectName("PrimaryBtn")
        self.btn_connect.clicked.connect(self.toggle_engine)
        self.left_panel.add_widget(self.btn_connect)
        
        self.left_panel.add_section("Recording")
        self.btn_record = QtWidgets.QPushButton("● START RECORDING")
        self.btn_record.setObjectName("RecordBtn")
        self.btn_record.setEnabled(False)
        self.btn_record.clicked.connect(self.toggle_recording)
        self.left_panel.add_widget(self.btn_record)
        
        self.left_panel.add_section("Bake Offline")
        self.btn_bake = QtWidgets.QPushButton("🤖 BAKE VIDEO FILE")
        self.btn_bake.clicked.connect(self.run_bake)
        self.left_panel.add_widget(self.btn_bake)

        # --- CENTER AREA (3D VIEWPORT) ---
        center_container = QtWidgets.QVBoxLayout()
        self.main_layout.addLayout(center_container, 1) # Content expands
        
        self.header = QtWidgets.QFrame()
        self.header.setFixedHeight(60)
        self.header.setStyleSheet("border-bottom: 2px solid #1a212b;")
        h_layout = QtWidgets.QHBoxLayout(self.header)
        title_top = QtWidgets.QLabel("MOTIONFORGE NEXUS v3.0")
        title_top.setObjectName("Title")
        h_layout.addWidget(title_top)
        h_layout.addStretch()
        self.status_lbl = QtWidgets.QLabel("SYS: READY")
        self.status_lbl.setStyleSheet("color: #8b949e; font-weight: bold;")
        h_layout.addWidget(self.status_lbl)
        center_container.addWidget(self.header)
        
        self.viewport = NexusViewport()
        center_container.addWidget(self.viewport, 1)
        
        # Floating Reference Camera
        self.ref_cam = ReferenceCameraWidget(self.viewport)
        self.ref_cam.move(20, 20)
        
        # Timeline
        self.timeline = NexusTimelineWidget()
        center_container.addWidget(self.timeline)

        # --- RIGHT PANEL (SETTINGS) ---
        self.right_panel = ControlPanelWidget("Settings")
        self.main_layout.addWidget(self.right_panel)
        
        self.right_panel.add_section("AI Tracking")
        self.right_panel.add_widget(QtWidgets.QLabel("Confidence Threshold"))
        self.conf_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.conf_slider.setRange(20, 90)
        self.conf_slider.setValue(50)
        self.right_panel.add_widget(self.conf_slider)
        
        self.chk_ghost = QtWidgets.QCheckBox("Show Ghost Trails")
        self.chk_ghost.toggled.connect(lambda v: setattr(self.viewport, 'show_ghost', v))
        self.right_panel.add_widget(self.chk_ghost)
        
        self.btn_reset_cam = QtWidgets.QPushButton("Reset View")
        self.btn_reset_cam.clicked.connect(self.viewport.reset_view)
        self.right_panel.add_widget(self.btn_reset_cam)
        
    def setup_connections(self):
        pass

    def toggle_engine(self):
        if self.capture_thread and self.capture_thread.isRunning():
            self.stop_engine()
        else:
            self.start_engine()

    def start_engine(self):
        idx = self.source_combo.currentIndex()
        stype = CameraSourceType.WEBCAM
        sinfo = 0
        if idx == 1: stype = CameraSourceType.MOBILE_USB; sinfo = 1
        if idx == 2: stype = CameraSourceType.MOBILE_WIFI; sinfo = self.ip_input.text()
        
        self.capture_thread = CaptureThread(stype, sinfo)
        self.capture_thread.frame_ready.connect(self.viewport.render_frame)
        self.capture_thread.image_ready.connect(self.ref_cam.update_image)
        self.capture_thread.status_msg.connect(self.status_lbl.setText)
        
        self.capture_thread.start()
        self.btn_connect.setText("⏹ STOP ENGINE")
        self.btn_record.setEnabled(True)
        self.status_lbl.setText("SYS: ENGINE ACTIVE")

    def stop_engine(self):
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread = None
        self.btn_connect.setText("⚡ CONNECT ENGINE")
        self.btn_record.setEnabled(False)
        self.status_lbl.setText("SYS: READY")

    def toggle_recording(self):
        if self.capture_thread:
            self.capture_thread.toggle_recording()
            is_rec = self.capture_thread.is_recording
            self.btn_record.setText("⏹ STOP RECORDING" if is_rec else "● START RECORDING")
            self.btn_record.setStyleSheet("color: white; background: #ff5555;" if is_rec else "")
            
    def run_bake(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Video", "data", "Videos (*.mp4)")
        if path:
            self.stop_engine()
            self.bake_thread = BakeThread(path)
            self.bake_thread.progress.connect(self.timeline.progress_bar.setValue)
            self.bake_thread.status.connect(self.status_lbl.setText)
            self.bake_thread.finished.connect(self.on_bake_finished)
            
            self.timeline.progress_bar.setVisible(True)
            self.bake_thread.start()

    def on_bake_finished(self, out_path):
        self.timeline.progress_bar.setVisible(False)
        QtWidgets.QMessageBox.information(self, "Bake Complete", f"Saved to:\n{out_path}")

def main():
    app = QtWidgets.QApplication(sys.argv)
    # App-wide scaling fix for high DPI
    app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    
    window = MotionForgeNexus()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
