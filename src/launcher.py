import sys
import os
import subprocess
import threading
import time
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from core.logger import engine_logger
from core.context import global_context

class Style:
    BG_DARK = "#0a0a0a"
    BG_CARD = "#121212"
    ACCENT_CYAN = "#00ffcc"
    ACCENT_PINK = "#ff00ff"
    TEXT_MAIN = "#ffffff"
    TEXT_DIM = "#888888"
    
    FONT_TITLE = ("Courier New", 22, QtGui.QFont.Bold)
    FONT_UI = ("Segoe UI", 10)
    
    QSS = f"""
        QMainWindow {{ background-color: {BG_DARK}; }}
        QWidget {{ background-color: {BG_DARK}; color: {TEXT_MAIN}; font-family: 'Segoe UI'; }}
        
        QPushButton {{
            background-color: {BG_CARD};
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            font-size: 14px;
            font-weight: bold;
            color: {TEXT_MAIN};
        }}
        QPushButton:hover {{
            background-color: #1a1a1a;
            border: 1px solid {ACCENT_CYAN};
        }}
        QPushButton#primary {{
            border: 1px solid {ACCENT_CYAN};
            color: {ACCENT_CYAN};
        }}
        QPushButton#secondary {{
            border: 1px solid {ACCENT_PINK};
            color: {ACCENT_PINK};
        }}
        
        QLabel#title {{ color: {ACCENT_CYAN}; font-size: 28px; font-weight: bold; font-family: 'Courier New'; }}
        QLabel#status {{ color: {TEXT_DIM}; font-size: 11px; font-style: italic; }}
        
        QProgressBar {{
            border: 1px solid #333;
            border-radius: 4px;
            text-align: center;
            background-color: {BG_CARD};
        }}
        QProgressBar::chunk {{
            background-color: {ACCENT_CYAN};
        }}
    """

class MotionForgeDashboard(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        print("Initializing Dashboard...")
        self.setWindowTitle("MOTIONFORGE PRO - STUDIO DASHBOARD")
        self.setFixedSize(700, 600)
        self.setStyleSheet(Style.QSS)
        
        self.init_ui()
        print("UI Initialized")
        self.start_status_monitor()
        print("Monitor Started")

    def init_ui(self):
        container = QtWidgets.QWidget()
        self.setCentralWidget(container)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # --- Header ---
        header_layout = QtWidgets.QVBoxLayout()
        title_label = QtWidgets.QLabel("MOTIONFORGE PRO")
        title_label.setObjectName("title")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        header_layout.addWidget(title_label)
        
        subtitle = QtWidgets.QLabel("ULTIMATE AI MOTION CAPTURE ENGINE")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {Style.ACCENT_PINK}; font-size: 10px; letter-spacing: 2px;")
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        # --- Status Bar ---
        self.status_bar = QtWidgets.QLabel("SYSTEM READY")
        self.status_bar.setObjectName("status")
        self.status_bar.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_bar)

        # --- Main Actions Grid ---
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(15)

        self.btn_capture = self.create_btn("📸 LIVE CAPTURE", self.run_capture, "primary")
        self.btn_bake = self.create_btn("🤖 OFFLINE BAKE", self.select_and_bake, "secondary")
        self.btn_view = self.create_btn("🦴 3D VIEWER", self.select_and_view)
        self.btn_export = self.create_btn("🪐 BLENDER EXPORT", self.select_and_export)
        
        grid.addWidget(self.btn_capture, 0, 0)
        grid.addWidget(self.btn_bake, 0, 1)
        grid.addWidget(self.btn_view, 1, 0)
        grid.addWidget(self.btn_export, 1, 1)
        layout.addLayout(grid)

        # --- Footer Actions ---
        footer_layout = QtWidgets.QHBoxLayout()
        btn_calibrate = QtWidgets.QPushButton("⚖️ ENGINE CALIBRATION")
        btn_calibrate.clicked.connect(self.run_calibrate)
        btn_calibrate.setStyleSheet("font-size: 10px; padding: 10px;")
        footer_layout.addWidget(btn_calibrate)
        
        self.engine_health = QtWidgets.QLabel("HEALTH: INITIALIZING...")
        self.engine_health.setStyleSheet(f"color: {Style.TEXT_DIM}; font-size: 9px;")
        footer_layout.addWidget(self.engine_health, 0, QtCore.Qt.AlignRight)
        layout.addLayout(footer_layout)

    def create_btn(self, text, callback, style_id=None):
        btn = QtWidgets.QPushButton(text)
        if style_id: btn.setObjectName(style_id)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def set_status(self, msg, active=True):
        self.status_bar.setText(f"● {msg.upper()}" if active else msg)
        self.status_bar.setStyleSheet(f"color: {Style.ACCENT_CYAN if active else Style.TEXT_DIM};")

    def run_script(self, script_name, args=None):
        self.set_status(f"LAUNCHING {script_name}...")
        
        python_exe = os.path.join("env311", "Scripts", "python.exe")
        if not os.path.exists(python_exe): python_exe = sys.executable 
            
        script_path = os.path.join("src", script_name)
        cmd = [python_exe, script_path]
        if args: cmd.extend(args)
        
        def _launch():
            try:
                subprocess.Popen(cmd)
                time.sleep(1.5)
                QtCore.QMetaObject.invokeMethod(self, "reset_status", QtCore.Qt.QueuedConnection)
            except Exception as e:
                engine_logger.error(f"UI Error: {e}")

        threading.Thread(target=_launch, daemon=True).start()

    @QtCore.pyqtSlot()
    def reset_status(self):
        self.set_status("SYSTEM READY", False)

    # --- Commands ---
    def run_capture(self): self.run_script("capture.py")
    def run_calibrate(self): self.run_script("calibrate.py")
    
    def select_and_bake(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Video to Bake", "data", "Videos (*.mp4)")
        if path: self.run_script("bake.py", [path])

    def select_and_view(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Mocap Session", "data", "Mocap JSON (*.json)")
        if path: self.run_script("viewer.py", [path])

    def select_and_export(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Motion Data for Export", "data", "Mocap JSON (*.json)")
        if path:
            self.set_status("EXPORTING TO BLENDER FORMAT...")
            self.run_script("export_blender.py", [path])

    def start_status_monitor(self):
        self.monitor_timer = QtCore.QTimer()
        self.monitor_timer.timeout.connect(self.update_health)
        self.monitor_timer.start(3000)

    def update_health(self):
        # Refresh context from disk if needed
        has_cal = global_context.load_calibration()
        cal_state = "OK" if has_cal else "NEEDS CALIBRATION"
        health_text = f"ENGINE: STABLE | CALIBRATION: {cal_state}"
        self.engine_health.setText(health_text)

def main():
    print("Launcher Main Start")
    app = QtWidgets.QApplication(sys.argv)
    
    # Modern font loading (optional, using Segoe UI default)
    window = MotionForgeDashboard()
    print("Window created, calling show()")
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
