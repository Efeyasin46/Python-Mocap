import os
import sys
import subprocess

def main():
    print("Starting PyInstaller build for MotionForge Nexus v3...")
    
    # Try to find mediapipe to include its assets
    try:
        import mediapipe
        mp_path = os.path.dirname(mediapipe.__file__)
        print(f"Found MediaPipe at: {mp_path}")
        add_data = f"--add-data={mp_path};mediapipe"
    except ImportError:
        print("Error: mediapipe not found!")
        sys.exit(1)
        
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "MotionForge_Nexus_v3",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        add_data,
        
        "--hidden-import=mediapipe",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=pyqtgraph",
        "--hidden-import=PyQt5",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtGui",
        "--hidden-import=PyQt5.QtWidgets",
        
        "--hidden-import=capture",
        "--hidden-import=bake",
        "--hidden-import=viewer",
        "--hidden-import=ui.style",
        "--hidden-import=ui.components",
        "--hidden-import=core",
        
        "src/nexus.py"
    ]
    
    print(f"\nRunning command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n[SUCCESS] --- NEXUS v3 BUILD COMPLETE ---")
        print("Path: dist/MotionForge_Nexus_v3/MotionForge_Nexus_v3.exe")
    else:
        print("\n[ERROR] --- BUILD FAILED ---")

if __name__ == "__main__":
    main()
