import cv2
import sys

def test_camera():
    print("Testing Camera Index 0...")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Camera 0 failed, trying Index 1...")
        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print("CRITICAL: No camera detected on Index 0 or 1.")
        return

    print("Camera active. Press 'Q' to exit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break
        
        cv2.imshow("Camera Debug", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_camera()
