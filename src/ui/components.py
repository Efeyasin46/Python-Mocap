from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal
import numpy as np

class ReferenceCameraWidget(QtWidgets.QLabel):
    """
    A small, floating-style camera reference widget for the Nexus UI.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 180)
        self.setStyleSheet("border: 2px solid #00ffc3; border-radius: 8px; background: #000;")
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setText("WAITING FOR CAMERA...")
        self.setScaledContents(True)

    def update_image(self, cv_img):
        rgb_image = cv_img # Assuming already RGB from CaptureThread
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        self.setPixmap(QtGui.QPixmap.fromImage(qt_img))

class NexusTimelineWidget(QtWidgets.QFrame):
    """
    Studio-grade timeline for playback and progress tracking.
    """
    scrubbed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomTimeline")
        self.setFixedHeight(80)
        layout = QtWidgets.QVBoxLayout(self)
        
        # Timeline Slider
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 1000)
        layout.addWidget(self.slider)
        
        # Controls Row
        controls = QtWidgets.QHBoxLayout()
        self.btn_play = QtWidgets.QPushButton("▶ PLAY")
        self.btn_play.setFixedWidth(100)
        controls.addWidget(self.btn_play)
        
        self.lbl_time = QtWidgets.QLabel("00:00:00 / 00:00:00")
        controls.addWidget(self.lbl_time)
        
        controls.addStretch()
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        controls.addWidget(self.progress_bar)
        
        layout.addLayout(controls)

class SectionHeader(QtWidgets.QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("font-weight: bold; color: #00ffc3; margin-top: 10px; border-bottom: 1px solid #1a212b; padding-bottom: 5px;")

class ControlPanelWidget(QtWidgets.QFrame):
    """
    Sidebar for camera and engine settings.
    """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setObjectName("SidePanel")
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 20, 15, 20)
        layout.setSpacing(10)
        
        title_lbl = QtWidgets.QLabel(title.upper())
        title_lbl.setObjectName("Title")
        layout.addWidget(title_lbl)
        
        layout.addSpacing(10)
        self.content_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(self.content_layout)
        layout.addStretch()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
    
    def add_section(self, title):
        self.content_layout.addWidget(SectionHeader(title))
