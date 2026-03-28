import json
import os
import sys
import numpy as np
from datetime import datetime
from typing import List, Dict, Any
from core.frame_model import UnifiedExporter, MocapFrame, Joint
from core.bvh_exporter import BVHExporter
from core.logger import engine_logger

class BlenderExporter:
    def __init__(self, input_path: str):
        self.input_path = input_path
        self.frames: List[MocapFrame] = UnifiedExporter.load_recording(input_path)
        self.report = {
            "total_frames": len(self.frames),
            "missing_joints": {},
            "unstable_joints": {},
            "jitter_scores": {},
            "status": "Incomplete"
        }

    def normalize_and_validate(self) -> List[Dict[str, Any]]:
        if not self.frames:
            return []

        blender_frames = []
        prev_joints = None
        
        for f_idx, frame in enumerate(self.frames):
            # 1. Hips (Merkez) Bul
            hip_l = frame.joints.get("LEFT_HIP")
            hip_r = frame.joints.get("RIGHT_HIP")
            
            if not hip_l or not hip_r:
                # Hips yoksa (0.5, 0.5, 0.5) varsay
                hip_center = np.array([0.5, 0.5, 0.0])
            else:
                hip_center = np.array([
                    (hip_l.x + hip_r.x) / 2,
                    (hip_l.y + hip_r.y) / 2,
                    (hip_l.z + hip_r.z) / 2
                ])

            blender_joints = {}
            for name, joint in frame.joints.items():
                # NAN Check
                if np.isnan(joint.x) or np.isnan(joint.y) or np.isnan(joint.z):
                    self.report["missing_joints"][name] = self.report["missing_joints"].get(name, 0) + 1
                    continue

                # Coordinate Conversion: MP(x, y, z) -> Blender(x, -z, -y)
                # Blender X = Left/Right (MP X)
                # Blender Y = Front/Back (-MP Z)
                # Blender Z = Up/Down (-MP Y)
                bx = (joint.x - hip_center[0])
                by = -(joint.z - hip_center[2])
                bz = -(joint.y - hip_center[1])
                
                blender_joints[name] = [float(bx), float(by), float(bz)]

                # Jitter Detection
                if prev_joints and name in prev_joints:
                    dist = np.linalg.norm(np.array(blender_joints[name]) - np.array(prev_joints[name]))
                    if name not in self.report["jitter_scores"]: self.report["jitter_scores"][name] = []
                    self.report["jitter_scores"][name].append(float(dist))
            
            blender_frames.append({
                "frame": frame.frame_id,
                "timestamp": frame.timestamp,
                "joints": blender_joints
            })
            prev_joints = blender_joints

        # Finalize Report
        self._calculate_final_report()
        return blender_frames

    def _calculate_final_report(self):
        for name, scores in self.report["jitter_scores"].items():
            avg_jitter = np.mean(scores)
            variance = np.var(scores)
            self.report["unstable_joints"][name] = {
                "avg_delta": float(avg_jitter),
                "variance": float(variance),
                "status": "UNSTABLE" if avg_jitter > 0.05 else "STABLE"
            }
        self.report["status"] = "Validated"

    def export(self, output_path: str, report_path: str):
        engine_logger.info(f"Exporting to Blender format: {output_path}")
        blender_data = self.normalize_and_validate()
        
        # 🟢 NEW: Industry Standard BVH Export
        bvh_path = output_path.replace(".json", ".bvh")
        engine_logger.info(f"Generating Industry Standard BVH: {bvh_path}")
        try:
            bvh_exp = BVHExporter(self.frames)
            bvh_exp.export(bvh_path)
            self.report["bvh_status"] = "Success"
        except Exception as e:
            engine_logger.error(f"BVH Export Error: {e}")
            self.report["bvh_status"] = f"Failed: {e}"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({"frames": blender_data}, f, indent=4)
            
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.report, f, indent=4)
            
        return output_path, report_path, bvh_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/export_blender.py <motion_file.json>")
        return

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return

    exporter = BlenderExporter(input_file)
    basename = os.path.splitext(os.path.basename(input_file))[0]
    out_json = f"data/{basename}_blender.json"
    out_report = f"data/{basename}_debug_report.json"
    
    exporter.export(out_json, out_report)
    print(f"\n--- BLENDER EXPORT COMPLETE ---")
    print(f"Ready for Blender: {out_json}")
    print(f"Debug Report: {out_report}")

if __name__ == "__main__":
    main()
