import cv2
import mediapipe as mp
import numpy as np
import os
import json
from datetime import datetime
from core.logger import engine_logger
from core.frame_model import MocapFrame, Joint, UnifiedExporter
from core.motion_pipeline import MotionPipeline
from core.constraints import SmoothingFilter, MotionStabilizer
from core.skeleton import SkeletonHierarchy

# Global MediaPipe References
mp_holistic = mp.solutions.holistic
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

def main():
    engine_logger.info("Starting MotionForge Mocap Engine (Capture)...")
    
    # 1. Pipeline ve Engine Kurulumu
    pipeline = MotionPipeline()
    smoother = SmoothingFilter(alpha=0.6)
    stabilizer = MotionStabilizer(still_threshold=0.005) # Hassas stabilizasyon
    hierarchy = SkeletonHierarchy()
    
    # Pipeline'a aşamaları ekle (Örnek: Smoothing)
    # pipeline.add_stage(lambda frame, raw: ...) # İleride detaylanacak
    
    # Kalibrasyon Verisini Yükle
    calibration_path = 'data/calibration_v1.json'
    if os.path.exists(calibration_path):
        with open(calibration_path, 'r') as f:
            cal_data = json.load(f)
            hierarchy.set_lengths_from_calibration(cal_data)
            engine_logger.info("Calibration loaded into skeleton.")

    # 2. Kamera Kurulumu (D SHOW + Çoklu Index Kontrolü)
    cap = None
    for idx in [0, 1, 2]:
        engine_logger.info(f"Trying camera index {idx}...")
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            # Check if we can actually read a frame
            ret, tmp_frame = cap.read()
            if ret:
                engine_logger.info(f"Successfully selected camera index {idx}")
                break
            cap.release()
    
    if not cap or not cap.isOpened():
        engine_logger.error("No active camera found on indices 0, 1, or 2!")
        return

    # Kamera özelliklerini zorla
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    # ...
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    is_recording = False
    recorded_frames = []
    video_writer = None

    with mp_holistic.Holistic(
        min_detection_confidence=0.3, # Slightly more lenient
        min_tracking_confidence=0.3,
        model_complexity=0 # 0 is much faster for real-time on i5 4th gen
    ) as holistic:
        
        while cap.isOpened():
            success, image = cap.read()
            if not success:
                engine_logger.error("Failed to read from camera. Restarting...")
                break

            # Dark Screen Diagnostic
            avg_brightness = np.mean(image)
            if avg_brightness < 10:
                cv2.putText(image, "CAMERA DISCONNECTED OR COVERED?", (10, 450), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            image = cv2.resize(image, (640, 480))
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = holistic.process(image_rgb)

            # 3. Pipeline İşlemi
            frame = pipeline.process_frame(results)
            
            # MediaPipe sonuçlarını doldur (Standard + World)
            if results.pose_landmarks:
                for i, lm in enumerate(results.pose_landmarks.landmark):
                    name = mp_holistic.PoseLandmark(i).name
                    frame.joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
            
            if results.pose_world_landmarks:
                for i, lm in enumerate(results.pose_world_landmarks.landmark):
                    name = mp_holistic.PoseLandmark(i).name
                    frame.world_joints[name] = Joint(x=lm.x, y=lm.y, z=lm.z, confidence=lm.visibility)
                if not hasattr(self, '_world_log_done'): 
                    engine_logger.info("WORLD LANDMARKS DETECTED (METERS MODE ACTIVE)")
                    self._world_log_done = True
            else:
                if not hasattr(self, '_world_log_done'):
                    engine_logger.warning("WORLD LANDMARKS MISSING (FALLBACK TO NORMALIZED)")
                    self._world_log_done = True
            
            # 1. Smoothing uygula
            frame.joints = smoother.process(frame.joints)
            
            # 2. Motion Stabilization (Foot Lock / Velocity Filter)
            frame.joints = stabilizer.process(frame.joints)

            # --- Visual Feedback (Drawing) ---
            # İsteğe bağlı: Filtrelenmiş veya ham veriyi çiz
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    image, results.pose_landmarks, mp_holistic.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                )
            if results.left_hand_landmarks:
                mp_drawing.draw_landmarks(image, results.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if results.right_hand_landmarks:
                mp_drawing.draw_landmarks(image, results.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
            if results.face_landmarks:
                mp_drawing.draw_landmarks(image, results.face_landmarks, mp_holistic.FACEMESH_CONTOURS,
                                         connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style())

            display_image = cv2.flip(image, 1)
            h, w, _ = display_image.shape
            
            # Basit çizim (Geliştirilecek)
            cv2.putText(display_image, f"Engine Clock: {frame.timestamp:.2f}s", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 204), 2)

            if is_recording:
                cv2.putText(display_image, "● REC", (w-100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                # Sadece geçerli (poz yakalanmış) kareleri kaydet
                if frame.is_valid():
                    recorded_frames.append(frame)
                if video_writer: video_writer.write(image)

            cv2.imshow('MotionForge Engine - Capture', display_image)
            
            # waitKey değeri çok düşükse (örn 1-5ms) Windows pencereyi güncelleyemeyebilir
            key = cv2.waitKey(15) & 0xFF
            if key == ord('r') and not is_recording:
                is_recording = True
                recorded_frames = []
                # Video kaydını başlat
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_filename = f"data/raw_video_{timestamp_str}.mp4"
                video_writer = cv2.VideoWriter(video_filename, cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (w, h))
                pipeline.reset()
                engine_logger.info("Recording STARTED.")
            elif key == ord('s') and is_recording:
                is_recording = False
                if video_writer: video_writer.release()
                
                # Unified Exporter ile Kaydet
                out_path = f"data/motion_engine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                UnifiedExporter.save_recording(recorded_frames, out_path)
                engine_logger.info(f"Recording SAVED to {out_path}")
                
            elif key == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
