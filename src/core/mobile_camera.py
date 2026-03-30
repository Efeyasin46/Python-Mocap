import cv2
import urllib.request
import urllib.error
from core.logger import engine_logger

class CameraSourceType:
    WEBCAM = "webcam"
    MOBILE_WIFI = "mobile_wifi"
    MOBILE_USB = "mobile_usb"

class MobileCameraManager:
    """
    v2.8 Mobile Integration
    Manages connections to remote or virtual mobile cameras.
    """
    
    @staticmethod
    def connect_wifi(ip_address: str, port: str = "8080") -> cv2.VideoCapture:
        """
        Connects to a mobile IP webcam stream (e.g., 'IP Webcam' app).
        Uses a fast fail-check to avoid OpenCV's long blocking timeouts.
        """
        # Strip prefixes if user accidentally added them
        ip_address = ip_address.replace("http://", "").replace("https://", "").split("/")[0]
        if ":" in ip_address:
            ip_address, port = ip_address.split(":")[:2]
            
        url = f"http://{ip_address}:{port}/video"
        engine_logger.info(f"Attempting WiFi Camera connection: {url}")
        
        # Fast fail check
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=2.0) as response:
                if response.status == 200:
                    engine_logger.info("WiFi Stream valid. Handing over to OpenCV...")
                    return cv2.VideoCapture(url)
                else:
                    engine_logger.error(f"WiFi Camera returned HTTP {response.status}")
                    return None
        except Exception as e:
            engine_logger.error(f"WiFi Camera Connection Failed: {e}")
            return None

    @staticmethod
    def connect_usb(preferred_index: int = 1) -> cv2.VideoCapture:
        """
        Connects to a USB Virtual Camera (e.g., DroidCam, EpocCam)
        Assumes it runs on index 1 or 2 since 0 is usually the integrated webcam.
        """
        engine_logger.info(f"Scanning for USB Virtual Camera (Start index {preferred_index})...")
        search_indices = [preferred_index, 0, 2, 3] # Prioritize requested index
        
        for idx in search_indices:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    engine_logger.info(f"Successfully connected to USB camera at index {idx}")
                    return cap
            cap.release()
            
        engine_logger.error("No valid USB/Virtual camera detected.")
        return None
