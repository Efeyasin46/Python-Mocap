import cv2
import mediapipe as mp
import numpy as np
import os
import json
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint, UnifiedExporter
from core.motion_pipeline import MotionPipeline
from core.constraints import AdaptiveSmoothingFilter, MotionStabilizer, FrameDropCompensator
from core.skeleton import SkeletonHierarchy
from core.mobile_camera import MobileCameraManager, CameraSourceType

# Global MediaPipe References
mp_holistic = mp.solutions.holistic
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

def main():
    engine_logger.info("Starting MotionForge Mocap Engine (Capture v2.8 Pro)...")
    
    # --- v2.8 SOURCE SELECTION GUI ---
    source_type = CameraSourceType.WEBCAM
    source_info = 0
    
    def on_source_select():
        nonlocal source_type, source_info
        sel = var.get()
        if sel == "wifi":
            source_type = CameraSourceType.MOBILE_WIFI
            source_info = ip_entry.get().strip()
        elif sel == "usb":
            source_type = CameraSourceType.MOBILE_USB
            source_info = 1
        root.quit()

    root = tk.Tk()
    root.title("MotionForge v2.8 - Source Selection")
    root.geometry("350x250")
    
    tk.Label(root, text="Select Camera Source:", font=("Arial", 11, "bold"), fg="#333").pack(pady=10)
    var = tk.StringVar(value="webcam")
    
    tk.Radiobutton(root, text="Standard Webcam", variable=var, value="webcam").pack(anchor="w", padx=40)
    tk.Radiobutton(root, text="Mobile USB Camera (DroidCam)", variable=var, value="usb").pack(anchor="w", padx=40)
    tk.Radiobutton(root, text="Mobile WiFi Camera (IP Webcam)", variable=var, value="wifi").pack(anchor="w", padx=40)
    
    # Helper entry for IP
    ip_frame = tk.Frame(root)
    ip_frame.pack(pady=5)
    tk.Label(ip_frame, text="IP/Port:", font=("Arial", 9)).pack(side="left")
    ip_entry = tk.Entry(ip_frame, width=20)
    ip_entry.insert(0, "192.168.1.55:8080")
    ip_entry.pack(side="left", padx=5)
    
    tk.Button(root, text="CONNECT & LAUNCH", command=on_source_select, bg="#00ffcc", fg="black", font=("Arial", 10, "bold")).pack(pady=15)
    root.mainloop()
    root.destroy()
    
    # 1. Pipeline ve Engine Kurulumu
    pipeline = MotionPipeline()
    drop_compensator = FrameDropCompensator(max_drop_frames=3)
    smoother = AdaptiveSmoothingFilter(min_alpha=0.4, max_alpha=0.8) # v2.8 Pro
    stabilizer = MotionStabilizer(lock_threshold=0.003) # v2.8 FootLock
    hierarchy = SkeletonHierarchy()
    
    # Kalibrasyon Verisini Yükle
    calibration_path = 'data/calibration_v2.json'
    if os.path.exists(calibration_path):
        with open(calibration_path, 'r') as f:
            cal_data = json.load(f)
            hierarchy.set_lengths_from_calibration(cal_data)
            engine_logger.info("Context: Loaded latest calibration.")

    # 2. Kamera Kurulumu (v2.8 Multi-Source)
    cap = None
    if source_type == CameraSourceType.MOBILE_WIFI:
        cap = MobileCameraManager.connect_wifi(source_info)
    elif source_type == CameraSourceType.MOBILE_USB:
        cap = MobileCameraManager.connect_usb(preferred_index=1)
        
    if cap is None and source_type != CameraSourceType.MOBILE_WIFI:
        engine_logger.info("Falling back to default USB camera search...")
        for idx in [0, 1, 2]:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                ret, tmp_frame = cap.read()
                if ret:
                    engine_logger.info(f"Successfully selected fallback camera index {idx}")
                    break
                cap.release()
    
    if not cap or not cap.isOpened():
        engine_logger.error("No active camera found!")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    is_recording = False
    recorded_frames = []
    video_writer = None
    world_log_done = False

    # Pre-compute Gamma Table for Auto-Exposure to save CPU cycles
    gamma = 1.3
    invGamma = 1.0 / gamma
    gamma_table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")

    with mp_holistic.Holistic(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=1, # v2.7 standard for balanced performance
        refine_face_landmarks=True # [RESTORED] Full face mesh accuracy
    ) as holistic:
        
        while cap.isOpened():
            success, image = cap.read()
            if not success: break
            
            # [v2.8] Auto-Exposure Compensation
            avg_brightness = np.mean(image)
            if 0 < avg_brightness < 50:
                image = cv2.LUT(image, gamma_table)

            # [RESTORED] Dark Screen Diagnostic
            if avg_brightness < 10:
                cv2.putText(image, "CAMERA COVERED OR TOO DARK?", (10, 450), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            image = cv2.resize(image, (640, 480))
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = holistic.process(image_rgb)

            # 3. Pipeline İşlemi
            frame = pipeline.process_frame(results)
            
            # MediaPipe Verilerini Doldur
            if results.pose_landmarks:
                for i, lm in enumerate(results.pose_landmarks.landmark):
                    name = mp_holistic.PoseLandmark(i).name
                    frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
            
            if results.pose_world_landmarks:
                for i, lm in enumerate(results.pose_world_landmarks.landmark):
                    name = mp_holistic.PoseLandmark(i).name
                    frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                if not world_log_done: 
                    engine_logger.info("WORLD LANDMARKS ACTIVE (v2.7 NEXUS)")
                    world_log_done = True
            
            # v2.8 Pro Stages
            frame.joints = drop_compensator.process(frame.joints) # Try to save skipped frames
            frame.joints = smoother.process(frame.joints)
            frame.joints = stabilizer.process(frame.joints)
            frame.source = source_type

            # Visual Feedback
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    image, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                )
            # [RESTORED] Face and Hand Meshes
            if hasattr(results, 'left_hand_landmarks') and results.left_hand_landmarks:
                mp_drawing.draw_landmarks(image, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if hasattr(results, 'right_hand_landmarks') and results.right_hand_landmarks:
                mp_drawing.draw_landmarks(image, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if hasattr(results, 'face_landmarks') and results.face_landmarks:
                mp_drawing.draw_landmarks(image, results.face_landmarks, mp_holistic.FACEMESH_CONTOURS,
                                         connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style())

            display_image = cv2.flip(image, 1)
            h, w, _ = display_image.shape
            
            # [v2.8] Advanced Debug Overlay
            cv2.putText(display_image, f"v2.8 PRO | SRC: {source_type.upper()}", (10, 25), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 204), 2)
            cv2.putText(display_image, f"Time: {frame.timestamp:.2f}s | Confidence: {frame.confidence_avg:.2f}", (10, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            if is_recording:
                cv2.putText(display_image, "● RECORDING", (w-130, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                if frame.is_valid():
                    recorded_frames.append(frame)
                if video_writer: video_writer.write(image)

            cv2.imshow('MotionForge Engine - Capture v2.7', display_image)
            
            key = cv2.waitKey(10) & 0xFF
            if key == ord('r') and not is_recording:
                is_recording = True
                recorded_frames = []
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_filename = f"data/raw_video_{timestamp_str}.mp4"
                video_writer = cv2.VideoWriter(video_filename, cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (w, h))
                pipeline.reset()
                engine_logger.info("Recording STARTED.")
            elif key == ord('s') and is_recording:
                is_recording = False
                if video_writer: video_writer.release()
                out_path = f"data/motion_engine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                UnifiedExporter.save_recording(recorded_frames, out_path)
                engine_logger.info(f"Recording SAVED to {out_path}")
            elif key == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
