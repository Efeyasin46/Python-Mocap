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

class NexusViewport(gl.GLViewWidget):
    """
    AAA Cinematic Viewport for MotionForge Nexus.
    Supports both Live Capture and Offline Playback rendering.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundColor('#050505')
        self.opts['fov'] = 65
        self.setCameraPosition(distance=4, elevation=15, azimuth=-90)
        
        # Grid & Axis
        grid = gl.GLGridItem()
        grid.setSize(24, 24)
        grid.setSpacing(1, 1)
        self.addItem(grid)
        
        # Mesh Cache
        self.joint_meshes = {}
        self.bone_meshes = {}
        self.shadow_mesh = None
        self.sphere_data = gl.MeshData.sphere(rows=10, cols=10)
        self.cylinder_data = gl.MeshData.cylinder(rows=10, cols=10)
        
        # State
        self.hierarchy = SkeletonHierarchy()
        self.show_ghost = False
        self.ghost_history = []
        self.debug_mode = False

    def reset_view(self):
        self.setCameraPosition(distance=4, elevation=15, azimuth=-90)

    def clear_viewport(self):
        for mesh in self.joint_meshes.values(): 
            try: self.removeItem(mesh)
            except: pass
        for data in self.bone_meshes.values(): 
            try: self.removeItem(data["item"])
            except: pass
        if self.shadow_mesh: 
            try: self.removeItem(self.shadow_mesh)
            except: pass
        self.joint_meshes = {}
        self.bone_meshes = {}
        self.shadow_mesh = None

    def render_frame(self, frame, offset_z=True):
        """Main entry point for rendering a single MocapFrame."""
        if not frame: return
        points = frame.get_world_coords()
        
        # Enforce Hierarchy
        if not self.debug_mode:
            points = self.hierarchy.enforce_lengths(points)
            
        # Ground Align
        z_min = 100
        for name in ["LEFT_ANKLE", "RIGHT_ANKLE"]:
            if name in points: z_min = min(z_min, points[name][2])
        
        offset = -z_min if offset_z else 0
        for name in points: points[name][2] += offset
        
        # Ghost Trails
        if self.show_ghost:
            hist_pts = {k: np.array(v) for k, v in points.items()}
            self.ghost_history.append(hist_pts)
            if len(self.ghost_history) > 15: self.ghost_history.pop(0)
            self.draw_ghosts()
        else:
            self.clear_ghosts()
        
        self.draw_meshes(points)

    def draw_meshes(self, points):
        import mediapipe as mp
        connections = mp.solutions.holistic.POSE_CONNECTIONS
        
        colors = {
            "Spine": (0, 1, 0.76, 0.8), # Nexus Cyan
            "Arms": (1, 0, 1, 0.7),     # Nexus Magenta
            "Legs": (1, 1, 0, 0.7),     # Yellow
            "Head": (1, 0.5, 0, 0.8),   # Orange
            "Hands": (1, 1, 1, 0.5)     # White
        }

        # 1. Torso
        ls, rs = points.get("LEFT_SHOULDER"), points.get("RIGHT_SHOULDER")
        lh, rh = points.get("LEFT_HIP"), points.get("RIGHT_HIP")
        if ls is not None and rs is not None and lh is not None and rh is not None:
            chest, waist = (ls + rs) / 2, (lh + rh) / 2
            if "TORSO" not in self.joint_meshes:
                m = gl.GLMeshItem(meshdata=self.cylinder_data, color=colors["Spine"], shader='shaded', smooth=True)
                self.addItem(m); self.joint_meshes["TORSO"] = m
            tr = MeshUtils.get_bone_matrix(waist, chest, thickness=0.08)
            if tr: self.joint_meshes["TORSO"].setTransform(tr)

        # 2. Head
        nose = points.get("NOSE")
        if nose is not None:
            if "HEAD" not in self.joint_meshes:
                m = gl.GLMeshItem(meshdata=self.sphere_data, color=colors["Head"], shader='shaded', smooth=True)
                self.addItem(m); self.joint_meshes["HEAD"] = m
            ht = QtGui.QMatrix4x4()
            ht.translate(nose[0], nose[1], nose[2] + 0.05)
            ht.scale(0.08, 0.08, 0.1)
            self.joint_meshes["HEAD"].setTransform(ht)

        # 3. Joints & Bones
        for conn in connections:
            s_name = mp.solutions.holistic.PoseLandmark(conn[0]).name
            e_name = mp.solutions.holistic.PoseLandmark(conn[1]).name
            if s_name in points and e_name in points:
                bid = f"{s_name}_{e_name}"
                p1, p2 = points[s_name], points[e_name]
                
                if bid not in self.bone_meshes:
                    color = colors["Arms"]
                    if "HIP" in s_name or "SHOULDER" in s_name: color = colors["Spine"]
                    if "KNEE" in s_name or "ANKLE" in s_name: color = colors["Legs"]
                    
                    thick = 0.03
                    if "HIP" in s_name and "KNEE" in e_name: thick = 0.05
                    
                    m = gl.GLMeshItem(meshdata=self.cylinder_data, color=color, shader='shaded', smooth=True)
                    self.addItem(m)
                    self.bone_meshes[bid] = {"item": m, "thick": thick}
                
                tr = MeshUtils.get_bone_matrix(p1, p2, thickness=self.bone_meshes[bid]["thick"])
                if tr: self.bone_meshes[bid]["item"].setTransform(tr)

        # 4. Shadow
        root = points.get("LEFT_HIP", np.array([0,0,0]))
        if not self.shadow_mesh:
            self.shadow_mesh = gl.GLMeshItem(meshdata=self.sphere_data, color=(0,0,0,0.3), shader='shaded')
            self.addItem(self.shadow_mesh)
        st = QtGui.QMatrix4x4()
        st.translate(root[0], root[1], 0.01)
        st.scale(0.35, 0.35, 0.001)
        self.shadow_mesh.setTransform(st)

    def draw_ghosts(self):
        for name in ["LEFT_WRIST", "RIGHT_WRIST", "LEFT_ANKLE", "RIGHT_ANKLE"]:
            path = [pts[name] for pts in self.ghost_history if name in pts]
            gid = f"ghost_{name}"
            if gid not in self.bone_meshes:
                m = gl.GLLinePlotItem(color=(0, 1, 0.76, 0.4), width=2, antialias=True)
                self.addItem(m)
                self.bone_meshes[gid] = {"item": m}
            if len(path) > 1:
                self.bone_meshes[gid]["item"].setData(pos=np.array(path))
                self.bone_meshes[gid]["item"].setVisible(True)

    def clear_ghosts(self):
        self.ghost_history = []
        for name in ["LEFT_WRIST", "RIGHT_WRIST", "LEFT_ANKLE", "RIGHT_ANKLE"]:
            gid = f"ghost_{name}"
            if gid in self.bone_meshes:
                self.bone_meshes[gid]["item"].setVisible(False)

class MocapViewerAAA(QtWidgets.QMainWindow):
    def __init__(self, filepath=None):
        super().__init__()
        self.setWindowTitle("MotionForge Nexus - Viewport Standalone")
        self.resize(1280, 720)
        self.central = QtWidgets.QWidget()
        self.setCentralWidget(self.central)
        self.layout = QtWidgets.QVBoxLayout(self.central)
        self.layout.setContentsMargins(0,0,0,0)
        self.viewport = NexusViewport()
        self.layout.addWidget(self.viewport)
        self.frames = []
        self.current_time = 0.0
        self.is_playing = True
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.last_tick = time.time()
        self.timer.start(16)
        if filepath: self.load_file(filepath)

    def load_file(self, path):
        try:
            self.frames = UnifiedExporter.load_recording(path)
            if self.frames: self.total_duration = self.frames[-1].timestamp
        except Exception as e:
            engine_logger.error(f"Viewer Error: {e}")

    def tick(self):
        now = time.time()
        dt = now - self.last_tick
        self.last_tick = now
        if self.is_playing and self.frames:
            self.current_time += dt
            if self.current_time > self.total_duration: self.current_time = 0.0
            idx = 0
            for i in range(len(self.frames)-1):
                if self.frames[i].timestamp <= self.current_time <= self.frames[i+1].timestamp:
                    idx = i; break
            self.viewport.render_frame(self.frames[idx])

def main():
    app = QtWidgets.QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    viewer = MocapViewerAAA(path)
    viewer.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
