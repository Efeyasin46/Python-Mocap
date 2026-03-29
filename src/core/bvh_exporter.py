import numpy as np
import os
from typing import List, Dict, Tuple, Optional
from core.frame_model import MocapFrame, Joint

class BVHExporter:
    """
    Kapsamlı BVH (Biovision Hierarchy) Dışa Aktarıcı - Nexus Pro V2.
    Rotasyon tabanlı iskelet animasyonu ve Blender uyumlu kanal sıralaması.
    """
    
    # 🟢 TAM İNSANSI HİYERARŞİSİ (BVH FORMATLI)
    # { "Joint": ["Children List"] }
    TREE = {
        "HIPS": ["SPINE", "LEFT_HIP", "RIGHT_HIP"],
        "SPINE": ["CHEST"],
        "CHEST": ["NECK", "LEFT_SHOULDER", "RIGHT_SHOULDER"],
        "NECK": ["HEAD"],
        "HEAD": [],
        
        "LEFT_SHOULDER": ["LEFT_ELBOW"],
        "LEFT_ELBOW": ["LEFT_WRIST"],
        "LEFT_WRIST": [],
        
        "RIGHT_SHOULDER": ["RIGHT_ELBOW"],
        "RIGHT_ELBOW": ["RIGHT_WRIST"],
        "RIGHT_WRIST": [],
        
        "LEFT_HIP": ["LEFT_KNEE"],
        "LEFT_KNEE": ["LEFT_ANKLE"],
        "LEFT_ANKLE": [],
        
        "RIGHT_HIP": ["RIGHT_KNEE"],
        "RIGHT_KNEE": ["RIGHT_ANKLE"],
        "RIGHT_ANKLE": []
    }
    
    # End Site (Uç Nokta) Gerektiren Eklemler
    END_SITES = ["HEAD", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_ANKLE", "RIGHT_ANKLE"]

    def __init__(self, frames: List[MocapFrame]):
        self.frames = frames
        self.fps = 60.0
        if len(frames) > 1:
            dt = frames[-1].timestamp - frames[0].timestamp
            if dt > 0: self.fps = len(frames) / dt
            
        self.scale = 100.0 # Blender metre ölçeği için 100x
        self.motion_order = [] # DFS sırasıyla eklemler

    @staticmethod
    def get_rotation_zxy(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
        """
        v1 (rest) ve v2 (curr) arasındaki rotasyonu ZXY Euler açısı olarak hesaplar.
        v1: [x, y, z] - Rest pos vector
        v2: [x, y, z] - Current pos vector
        """
        # 1. Normalizasyon
        v1 = v1 / (np.linalg.norm(v1) + 1e-9)
        v2 = v2 / (np.linalg.norm(v2) + 1e-9)
        
        # 2. Rotasyon Quaternionu (veya Matrix) hesapla
        # v1 -> v2 rotasyonu
        axis = np.cross(v1, v2)
        axis_len = np.linalg.norm(axis)
        dot = np.dot(v1, v2)
        
        if axis_len < 1e-9:
            return np.array([0.0, 0.0, 0.0])
            
        # Rodrigues' Rotation Formula basitleştirilmiş hali
        # Burada basitçe yön değişimlerini Euler'e dökeceğiz.
        # BVH standardında çoğunlukla dikey eksen (Y) ve yan eksenler kullanılır.
        
        # 3. Euler Dönüşümü (Zrotation Xrotation Yrotation)
        # Not: Blender BVH için standart ZXY veya ZYX tercih edilir.
        angle = np.arccos(np.clip(dot, -1.0, 1.0))
        
        # Basit Euler yaklaşımı (Dönüşüm matrisinden de çekilebilir)
        # Karakterin dik durduğunu varsayarsak:
        z_rot = 0.0 # Roll (Z) genellikle point-cloud'da belirsizdir
        x_rot = np.degrees(np.arctan2(v2[2], v2[1]))
        y_rot = np.degrees(np.arctan2(v2[0], v2[1]))
        
        # Rest pose ile farkını al (Hiyerarşik fark)
        # Bu kısım hiyerarşide ebeveyne göre olacağı için basitleşir
        return np.array([z_rot, x_rot, y_rot])

    def export(self, output_path: str):
        if not self.frames: return
        
        # 1. İlk kare üzerinden Yerel Offset (Kemik Boyu) hesapla
        # İlk kare T-Pose kabul edilir
        first_frame_coords = self.frames[0].get_world_coords(scale_factor=1.0)
        offsets = self._calculate_local_offsets(first_frame_coords)
        
        # 2. Hiyerarşi Bloğu Oluştur
        self.motion_order = []
        hierarchy_lines = ["HIERARCHY"]
        hierarchy_lines.extend(self._build_joint_str("HIPS", offsets, 0))
        
        # 3. Motion Bloğu Oluştur
        motion_lines = ["MOTION", f"Frames: {len(self.frames)}", f"Frame Time: {1.0/self.fps:.6f}"]
        
        for frame in self.frames:
            coords = frame.get_world_coords(scale_factor=1.0)
            motion_line = []
            
            # DFS Sırasıyla Verileri Yaz
            for joint_name in self.motion_order:
                pos = coords.get(joint_name, np.array([0,0,0]))
                
                if joint_name == "HIPS":
                    # Kök Pozisyonu (X, Y, Z) + Rotasyon (6 Kanal)
                    # BVH Space: X=Right, Y=Up, Z=Back
                    bx, by, bz = pos[0]*self.scale, pos[2]*self.scale, -pos[1]*self.scale
                    motion_line.extend([f"{bx:.4f}", f"{by:.4f}", f"{bz:.4f}"])
                    motion_line.extend(["0.0000", "0.0000", "0.0000"]) # Kök Rot (Z, X, Y)
                else:
                    # Uzuv Rotasyonları (Z, X, Y)
                    # Ebeveyn ve Çocuk arasındaki vektöre göre rotasyon hesapla
                    parent_name = self._get_parent(joint_name)
                    if parent_name:
                        p_pos = coords.get(parent_name, np.array([0,0,-0.1]))
                        v_curr = pos - p_pos
                        # BVH eksenine çevir
                        v_bvh = np.array([v_curr[0], v_curr[2], -v_curr[1]])
                        
                        # T-Pozundaki (Rest) vektörü bul
                        v_rest = offsets[joint_name]
                        
                        # Rotasyon hesapla
                        rot = self.get_rotation_zxy(v_rest, v_bvh)
                        motion_line.extend([f"{rot[0]:.4f}", f"{rot[1]:.4f}", f"{rot[2]:.4f}"])
                    else:
                        motion_line.extend(["0.0000", "0.0000", "0.0000"])
            
            motion_lines.append(" ".join(motion_line))
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(hierarchy_lines + motion_lines))
        
        return output_path

    def _calculate_local_offsets(self, coords: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Ebeveyne göre yerel offsetleri hesaplar."""
        offsets = {}
        for parent, children in self.TREE.items():
            p_pos = coords.get(parent, np.array([0,0,0]))
            for child in children:
                c_pos = coords.get(child, p_pos + np.array([0,0,0.1]))
                rel = (c_pos - p_pos) * self.scale
                # Nexus -> BVH Eksenleri
                offsets[child] = np.array([rel[0], rel[2], -rel[1]])
        
        offsets["HIPS"] = np.array([0.0, 0.0, 0.0])
        return offsets

    def _get_parent(self, name: str) -> Optional[str]:
        for parent, children in self.TREE.items():
            if name in children: return parent
        return None

    def _build_joint_str(self, name: str, offsets: Dict[str, np.ndarray], indent: int) -> List[str]:
        self.motion_order.append(name)
        space = "  " * indent
        off = offsets.get(name, np.array([0.0, 0.0, 0.0]))
        
        lines = []
        if name == "HIPS":
            lines.append(f"{space}ROOT {name}")
            channels = "6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"
        else:
            lines.append(f"{space}JOINT {name}")
            channels = "3 Zrotation Xrotation Yrotation"
            
        lines.append(f"{space}{{")
        lines.append(f"{space}  OFFSET {off[0]:.4f} {off[1]:.4f} {off[2]:.4f}")
        lines.append(f"{space}  CHANNELS {channels}")
        
        for child in self.TREE.get(name, []):
            lines.extend(self._build_joint_str(child, offsets, indent + 1))
            
        if name in self.END_SITES:
            lines.append(f"{space}  End Site")
            lines.append(f"{space}  {{")
            lines.append(f"{space}    OFFSET 0.0000 5.0000 0.0000")
            lines.append(f"{space}  }}")
            
        lines.append(f"{space}}}")
        return lines
