import sys
import os
import json
import time
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
import pyqtgraph.opengl as gl
from core.frame_model import UnifiedExporter, MocapFrame, Joint
from core.skeleton import SkeletonHierarchy
from core.logger import engine_logger

class MeshUtils:
    @staticmethod
    def get_bone_matrix(p1, p2, thickness=0.015):
        """
        Calculates the transformation matrix for a cylinder bone between p1 and p2.
        """
        v = p2 - p1
        length = np.linalg.norm(v)
        if length < 1e-6: return None
        
        # Unit vector
        v_unit = v / length
        
        # Rotation to align Z-axis (default cylinder direction) with v_unit
        z_axis = np.array([0, 0, 1])
        if np.allclose(v_unit, z_axis):
            angle = 0
            axis = np.array([1, 0, 0])
        elif np.allclose(v_unit, -z_axis):
            angle = 180
            axis = np.array([1, 0, 0])
        else:
            cos_theta = np.dot(z_axis, v_unit)
            axis = np.cross(z_axis, v_unit)
            angle = np.arccos(np.clip(cos_theta, -1.0, 1.0))
        
        # Build transform
        tr = QtGui.QMatrix4x4()
        tr.translate(p1[0], p1[1], p1[2])
        tr.rotate(np.degrees(angle), axis[0], axis[1], axis[2])
        tr.scale(thickness, thickness, length)
        return tr

class MocapViewerAAA(QtWidgets.QMainWindow):
    def __init__(self, filepath=None):
        super().__init__()
        self.setWindowTitle("MotionForge Engine - Cinematic Viewport 1.5")
        self.resize(1280, 800)
        
        # Engine Data
        self.frames = []
        self.current_time = 0.0
        self.is_playing = True
        self.playback_speed = 1.0
        self.loop = True
        
        self.setup_ui()
        self.setup_viewport()
        
        # Mesh Cache (Avoid re-creating items)
        self.joint_meshes = {} # name -> GLMeshItem
        self.bone_meshes = {}  # (start, end) -> GLMeshItem
        self.shadow_mesh = None
        
        # Timer for 60FPS loop
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.engine_tick)
        self.last_tick = time.time()
        self.timer.start(16) # ~60 FPS
        
        if filepath:
            self.load_file(filepath)

    def setup_ui(self):
        self.central = QtWidgets.QWidget()
        self.setCentralWidget(self.central)
        self.layout = QtWidgets.QVBoxLayout(self.central)
        self.layout.setContentsMargins(0,0,0,0)
        
        # Viewport Container
        self.viewport_container = QtWidgets.QFrame()
        self.v_layout = QtWidgets.QVBoxLayout(self.viewport_container)
        self.v_layout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.viewport_container, 8)
        
        # Standard ViewWidget (Will be initialized in setup_viewport)
        
        # Overlay UI (Translucent)
        self.overlay = QtWidgets.QWidget(self.viewport_container)
        self.overlay.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.overlay.setStyleSheet("color: #00ffcc; font-family: 'Segoe UI'; font-size: 10pt;")
        self.overlay.setFixedWidth(250)
        self.overlay.move(20, 20)
        
        o_layout = QtWidgets.QVBoxLayout(self.overlay)
        self.lbl_status = QtWidgets.QLabel("● NEXUS ENGINE ACTIVE")
        self.lbl_frame = QtWidgets.QLabel("FRAME: 0 / 0")
        self.lbl_fps = QtWidgets.QLabel("PLAYBACK: 60 FPS")
        o_layout.addWidget(self.lbl_status)
        o_layout.addWidget(self.lbl_frame)
        o_layout.addWidget(self.lbl_fps)
        
        # Control Panel (Bottom)
        self.controls = QtWidgets.QWidget()
        self.controls.setFixedHeight(100)
        self.controls.setStyleSheet("background: #0a0a0a; border-top: 1px solid #222;")
        c_layout = QtWidgets.QVBoxLayout(self.controls)
        
        # Timeline
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setStyleSheet("QSlider::groove:horizontal { height: 4px; background: #333; } "
                                 "QSlider::handle:horizontal { background: #00ffcc; width: 14px; margin: -5px 0; }")
        c_layout.addWidget(self.slider)
        
        # Buttons
        b_layout = QtWidgets.QHBoxLayout()
    
        self.btn_play = QtWidgets.QPushButton("PAUSE")
        self.btn_play.setFixedWidth(80)
        self.btn_play.clicked.connect(self.toggle_play)
        b_layout.addWidget(self.btn_play)
    
        self.chk_loop = QtWidgets.QCheckBox("LOOP")
        self.chk_loop.setChecked(True)
        self.chk_loop.clicked.connect(self.toggle_loop)
        b_layout.addWidget(self.chk_loop)
    
        self.speed_combo = QtWidgets.QComboBox()
        self.speed_combo.addItems(["0.5x", "1.0x", "2.0x"])
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.currentIndexChanged.connect(self.update_speed)
        b_layout.addWidget(self.speed_combo)
    
        b_layout.addStretch()
    
        self.btn_debug = QtWidgets.QPushButton("DEBUG: OFF")
        self.btn_debug.setCheckable(True)
        self.btn_debug.clicked.connect(self.toggle_debug)
        b_layout.addWidget(self.btn_debug)
    
        c_layout.addLayout(b_layout)
        self.layout.addWidget(self.controls)
    
        # Logic
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)
        self.slider.valueChanged.connect(self.slider_changed)
        self.is_scrubbing = False
        
        self.hierarchy = SkeletonHierarchy()
        self.debug_mode = False

    def setup_viewport(self):
        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor('#050505')
        self.view.setCameraPosition(distance=4, elevation=15, azimuth=-90)
        self.v_layout.addWidget(self.view)
        
        # Infinite Grid (AAA Style)
        grid = gl.GLGridItem()
        grid.setSize(20, 20)
        grid.setSpacing(1, 1)
        # grid.translate(0, 0, 0) # Ground at Y=0
        self.view.addItem(grid)
        
        # Origin Axis
        axis = gl.GLAxisItem()
        axis.setSize(1, 1, 1)
        self.view.addItem(axis)
        
        # Shared Meshes
        self.sphere_data = gl.MeshData.sphere(rows=10, cols=10)
        self.cylinder_data = gl.MeshData.cylinder(rows=10, cols=10)

    def load_file(self, path):
        try:
            self.frames = UnifiedExporter.load_recording(path)
            if not self.frames: return
            self.slider.setMaximum(len(self.frames) - 1)
            self.total_duration = self.frames[-1].timestamp
            engine_logger.info(f"AAA Viewer: Loaded {len(self.frames)} frames")
        except Exception as e:
            engine_logger.error(f"Viewer Error: {e}")

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.btn_play.setText("PAUSE" if self.is_playing else "PLAY")

    def toggle_debug(self):
        self.debug_mode = not self.debug_mode
        self.btn_debug.setText("DEBUG: ON" if self.debug_mode else "DEBUG: OFF")

    def toggle_loop(self):
        self.loop = self.chk_loop.isChecked()

    def update_speed(self):
        speed_str = self.speed_combo.currentText().replace("x", "")
        self.playback_speed = float(speed_str)

    def slider_pressed(self):
        self.is_scrubbing = True

    def slider_released(self):
        self.is_scrubbing = False

    def slider_changed(self, val):
        if self.is_scrubbing and self.frames:
            self.current_time = self.frames[val].timestamp
            self.render_interpolated(self.current_time)

    def engine_tick(self):
        now = time.time()
        dt = (now - self.last_tick) * self.playback_speed
        self.last_tick = now
        
        if self.is_playing and self.frames:
            self.current_time += dt
            if self.current_time > self.total_duration:
                if self.loop: self.current_time = 0.0
                else: self.is_playing = False
            
            # 1. Update Slider
            if self.total_duration > 0:
                progress = (self.current_time / self.total_duration) * (len(self.frames)-1)
                self.slider.blockSignals(True)
                self.slider.setValue(int(progress))
                self.slider.blockSignals(False)
                
                # 2. Render Interpolated Frame
                self.render_interpolated(self.current_time)
            else:
                self.draw_meshes(self.frames[0].get_world_coords())

    def render_interpolated(self, t):
        # Find frames for LERP
        idx = 0
        for i in range(len(self.frames)-1):
            if self.frames[i].timestamp <= t <= self.frames[i+1].timestamp:
                idx = i
                break
        
        f1 = self.frames[idx]
        f2 = self.frames[idx+1]
        
        # Alpha
        total_dt = f2.timestamp - f1.timestamp
        if total_dt > 0:
            alpha = (t - f1.timestamp) / total_dt
        else:
            alpha = 0.0
            
        # Standard Axis Mapping in data processing
        p1 = f1.get_world_coords()
        p2 = f2.get_world_coords()
        
        # Interpolated points
        points = {}
        for name in p1:
            if name in p2:
                points[name] = p1[name] * (1-alpha) + p2[name] * alpha
        
        # --- BONE HIERARCHY ENFORCEMENT ---
        # 1. First Pass: Apply absolute axis mapping (ALREADY DONE in get_world_coords)
        # 2. Second Pass: Enforce Skeleton Hierarchy
        if not self.debug_mode:
            points = self.hierarchy.enforce_lengths(points)
        
        # --- GROUND ALIGNMENT --- (Step 7)
        # In PyQtGraph: Z is Up
        ground_anchors = ["LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL"]
        z_min = 100
        for name in ground_anchors:
            if name in points:
                if points[name][2] < z_min: z_min = points[name][2]
        
        # Apply ground offset (Lowest Point = 0)
        offset = -z_min
        for name in points:
            points[name][2] += offset
        
        self.draw_meshes(points)
        
        # --- DEBUG MODE v2.7 ---
        if self.debug_mode:
            # 1. Raw comparison points
            raw_points = f1.get_world_coords(scale_factor=1.0)
            for name, r_pos in raw_points.items():
                r_pos[2] += offset # Apply same ground offset
            self.draw_debug_points(raw_points)
            
            # 2. Velocity Vectors (Example for feet)
            self.draw_velocity_vectors(f1, f2, offset)
            
        self.lbl_frame.setText(f"FRAME: {idx} / {len(self.frames)}")

    def draw_debug_points(self, points):
        """Draws small red cubes/points for RAW data comparison."""
        for name, pos in points.items():
            debug_name = f"debug_{name}"
            if debug_name not in self.joint_meshes:
                mesh = gl.GLMeshItem(meshdata=self.sphere_data, color=(1, 0, 0, 0.5), shader='shaded')
                self.view.addItem(mesh)
                self.joint_meshes[debug_name] = mesh
            
            tr = QtGui.QMatrix4x4()
            tr.translate(pos[0], pos[1], pos[2])
            tr.scale(0.01, 0.01, 0.01) # Small red dots
            self.joint_meshes[debug_name].setTransform(tr)

    def draw_velocity_vectors(self, f1, f2, z_offset):
        """Draws yellow lines indicating joint velocity in debug mode."""
        coords1 = f1.get_world_coords()
        coords2 = f2.get_world_coords()
        
        # We only draw for critical joints to avoid clutter
        critical = ["LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_WRIST", "RIGHT_WRIST", "NOSE"]
        
        for name in critical:
            if name in coords1 and name in coords2:
                p1 = coords1[name]
                p2 = coords2[name]
                p1[2] += z_offset
                p2[2] += z_offset
                
                # Draw a line between p2 and p2 + (p2-p1)*5 (velocity amplification for visibility)
                vel = (p2 - p1) * 10
                v_name = f"vel_{name}"
                
                if v_name not in self.bone_meshes:
                    mesh = gl.GLLinePlotItem(color=(1, 1, 0, 1), width=2)
                    self.view.addItem(mesh)
                    self.bone_meshes[v_name] = {"item": mesh}
                
                self.bone_meshes[v_name]["item"].setData(pos=np.array([p2, p2 + vel]))

    def draw_meshes(self, points):
        import mediapipe as mp
        connections = mp.solutions.holistic.POSE_CONNECTIONS
        
        # Color Palettes
        colors = {
            "Spine": (0, 1, 1, 0.7),    # Cyan
            "Arms": (1, 0, 1, 0.7),     # Magenta
            "Legs": (1, 1, 0, 0.7),     # Yellow
            "Head": (1, 0.5, 0, 0.8),   # Orange
            "Hands": (1, 1, 1, 0.5)     # White
        }

        # --- A. SPECIAL MESHES (TORSO & HEAD) ---
        # 1. Torso Volume
        ls, rs = points.get("LEFT_SHOULDER"), points.get("RIGHT_SHOULDER")
        lh, rh = points.get("LEFT_HIP"), points.get("RIGHT_HIP")
        if ls is not None and rs is not None and lh is not None and rh is not None:
            # Chest Center & Hip Center
            chest = (ls + rs) / 2
            waist = (lh + rh) / 2
            
            if "TORSO_BLOCK" not in self.joint_meshes:
                mesh = gl.GLMeshItem(meshdata=self.cylinder_data, color=colors["Spine"], shader='shaded', smooth=True)
                self.view.addItem(mesh)
                self.joint_meshes["TORSO_BLOCK"] = mesh
            
            # Draw as a thick cylinder
            tr = MeshUtils.get_bone_matrix(waist, chest, thickness=0.08)
            if tr: self.joint_meshes["TORSO_BLOCK"].setTransform(tr)

        # 2. Head Volume
        nose = points.get("NOSE")
        if nose is not None:
            if "HEAD_BLOCK" not in self.joint_meshes:
                mesh = gl.GLMeshItem(meshdata=self.sphere_data, color=colors["Head"], shader='shaded', smooth=True)
                self.view.addItem(mesh)
                self.joint_meshes["HEAD_BLOCK"] = mesh
            
            htrans = QtGui.QMatrix4x4()
            # Position head slightly above neck center
            head_center = nose # Simplified for now
            htrans.translate(head_center[0], head_center[1], head_center[2] + 0.05)
            htrans.scale(0.08, 0.08, 0.1) # Oval head shape
            self.joint_meshes["HEAD_BLOCK"].setTransform(htrans)

        # --- B. JOINTS (Subtle Spheres) ---
        for name, pos in points.items():
            if name in ["NOSE", "LEFT_EYE", "RIGHT_EYE", "LEFT_EAR", "RIGHT_EAR"]: continue # Hidden in head
            
            if name not in self.joint_meshes:
                # Size by importance
                size = 0.015 # default subtle
                color = colors["Hands"]
                
                if "SHOULDER" in name or "HIP" in name: size = 0.025; color = colors["Spine"]
                if "ELBOW" in name or "KNEE" in name: size = 0.02
                
                mesh = gl.GLMeshItem(meshdata=self.sphere_data, color=color, shader='shaded', smooth=True)
                self.view.addItem(mesh)
                self.joint_meshes[name] = mesh
            
            jtrans = QtGui.QMatrix4x4()
            jtrans.translate(pos[0], pos[1], pos[2])
            j_size = 0.015
            if "SHOULDER" in name or "HIP" in name: j_size = 0.025
            jtrans.scale(j_size, j_size, j_size)
            self.joint_meshes[name].setTransform(jtrans)

        # --- C. BONES (Humanoid Proportions) ---
        for conn in connections:
            start_name = mp.solutions.holistic.PoseLandmark(conn[0]).name
            end_name = mp.solutions.holistic.PoseLandmark(conn[1]).name
            
            if start_name in points and end_name in points:
                bone_id = f"{start_name}_{end_name}"
                p1, p2 = points[start_name], points[end_name]
                
                if bone_id not in self.bone_meshes:
                    # Color check
                    color = colors["Arms"]
                    if "HIP" in start_name or "SHOULDER" in start_name: color = colors["Spine"]
                    if "KNEE" in start_name or "ANKLE" in start_name: color = colors["Legs"]
                    if "EYE" in start_name or "NOSE" in start_name: color = colors["Head"]
                    
                    # Bone thickness (Humanoid Proportions)
                    thickness = 0.03 # Thicker limbs
                    if "HIP" in start_name and "KNEE" in end_name: thickness = 0.05
                    if "KNEE" in start_name and "ANKLE" in end_name: thickness = 0.04
                    if "SHOULDER" in start_name and "ELBOW" in end_name: thickness = 0.04
                    if "ELBOW" in start_name and "WRIST" in end_name: thickness = 0.025
                    
                    if "HIP" in start_name and "HIP" in end_name: thickness = 0.06
                    if "SHOULDER" in start_name and "SHOULDER" in end_name: thickness = 0.05
                    
                    mesh = gl.GLMeshItem(meshdata=self.cylinder_data, color=color, shader='shaded', smooth=True)
                    self.view.addItem(mesh)
                    self.bone_meshes[bone_id] = {"item": mesh, "thick": thickness}
                
                # Step 5: Prevent drawing if distance is near zero
                dist = np.linalg.norm(p2 - p1)
                if dist < 0.001:
                    self.bone_meshes[bone_id]["item"].setVisible(False)
                    continue
                else:
                    self.bone_meshes[bone_id]["item"].setVisible(True)

                # Update Transform
                tr = MeshUtils.get_bone_matrix(p1, p2, thickness=self.bone_meshes[bone_id]["thick"])
                if tr:
                    self.bone_meshes[bone_id]["item"].setTransform(tr)

        # 3. Update Shadow
        root_pos = points.get("LEFT_HIP", np.array([0,0,0]))
        if not self.shadow_mesh:
            self.shadow_mesh = gl.GLMeshItem(meshdata=self.sphere_data, color=(0,0,0,0.4), shader='shaded', smooth=True)
            self.view.addItem(self.shadow_mesh)
        
        strans = QtGui.QMatrix4x4()
        strans.translate(root_pos[0], root_pos[1], 0) # Ground shadow
        strans.scale(0.3, 0.3, 0.001) # Flatten sphere to disc
        self.shadow_mesh.setTransform(strans)

def main():
    app = QtWidgets.QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    viewer = MocapViewerAAA(path)
    viewer.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
