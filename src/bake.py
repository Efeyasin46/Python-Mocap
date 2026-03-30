import cv2
import mediapipe as mp
import os
import glob
import json
import time
import sys
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint, UnifiedExporter
from core.motion_pipeline import MotionPipeline
from core.constraints import AdaptiveSmoothingFilter, MotionStabilizer, GroundAligner, FrameDropCompensator, OfflinePostProcessor
from core.skeleton import SkeletonHierarchy

# Global MediaPipe References
mp_holistic = mp.solutions.holistic

def get_latest_video(directory):
    files = glob.glob(os.path.join(directory, 'raw_video_*.mp4'))
    if not files: return None
    return max(files, key=os.path.getctime)

def main():
    # 1. Komut satırı argümanı kontrolü (Launcher'dan gelmiş olabilir)
    if len(sys.argv) > 1:
        input_video = sys.argv[1]
    else:
        root = tk.Tk()
        root.withdraw()
        data_dir = 'data'
        latest_video = get_latest_video(data_dir)
        input_video = None
        if latest_video:
            print(f"\nSon kayıt bulundu: {os.path.basename(latest_video)}")
            choice = input("Bu dosyayı mı işleyelim? (E/H): ").lower()
            if choice == 'e' or choice == '':
                input_video = latest_video
        if not input_video:
            input_video = filedialog.askopenfilename(initialdir=data_dir, title="Mocap Videosu Seç", filetypes=(("Video", "*.mp4"), ("All", "*.*")))

    if not input_video or not os.path.exists(input_video):
        engine_logger.error("No input video selected for baking.")
        return

    engine_logger.info(f"Engine Baking Started: {os.path.basename(input_video)}")
    
    # 2. Pipeline ve Engine Kurulumu
    pipeline = MotionPipeline()
    drop_compensator = FrameDropCompensator(max_drop_frames=5) # Bake allows longer interpolation
    smoother = AdaptiveSmoothingFilter(min_alpha=0.3, max_alpha=0.9) # v2.8 Adaptive
    stabilizer = MotionStabilizer(lock_threshold=0.005, still_threshold=0.01) # v2.8 Stricter FootLock
    hierarchy = SkeletonHierarchy()

    cap = cv2.VideoCapture(input_video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    baked_frames = []

    with mp_holistic.Holistic(
        model_complexity=2,        # EN ÜST DÜZEY HASSASİYET
        refine_face_landmarks=True 
    ) as holistic:
        
        frame_idx = 0
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = holistic.process(frame_rgb)
            
            # Pipeline İşlemi
            m_frame = pipeline.process_frame(results)
            
            # MediaPipe Verilerini Doldur
            if results.pose_landmarks:
                for i, lm in enumerate(results.pose_landmarks.landmark):
                    name = mp_holistic.PoseLandmark(i).name
                    m_frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
            
            if results.pose_world_landmarks:
                for i, lm in enumerate(results.pose_world_landmarks.landmark):
                    name = mp_holistic.PoseLandmark(i).name
                    m_frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
            
            # Smoothing & Stabilization
            m_frame.joints = drop_compensator.process(m_frame.joints)
            m_frame.joints = smoother.process(m_frame.joints)
            m_frame.joints = stabilizer.process(m_frame.joints)

            if m_frame.is_valid():
                baked_frames.append(m_frame)
            frame_idx += 1
            
            progress = (frame_idx / total_frames) * 100
            print(f"\r[ENGINE BAKE] Progress: %{progress:.1f} | Frame: {frame_idx}/{total_frames} ", end="")

    cap.release()
    print("\n")
    
    # --- POST-PROCESSING ENHANCEMENTS v2.8 ---
    engine_logger.info("Applying Sequence Depth Correction (Anti-Jitter)...")
    baked_frames = OfflinePostProcessor.correct_depth_jitter(baked_frames)
    
    engine_logger.info("Applying Floor Detection & Ground Alignment...")
    for frame in baked_frames:
        GroundAligner.align_to_floor(frame)
    
    # Unified Exporter ile Kaydet
    output_filename = f"data/motion_baked_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    UnifiedExporter.save_recording(baked_frames, output_filename)
    
    engine_logger.info(f"Baking COMPLETE. Saved to {output_filename}")

if __name__ == '__main__':
    main()
