import os
import sys
import subprocess

def main():
    print("Starting PyInstaller build for MotionForge v0.1 Alpha...")
    
    # Try to find mediapipe to include its assets
    try:
        import mediapipe
        mp_path = os.path.dirname(mediapipe.__file__)
        print(f"Found MediaPipe at: {mp_path}")
        # Windows formatting for add-data is src;dest
        add_data = f"--add-data={mp_path};mediapipe"
    except ImportError:
        print("Error: mediapipe not found in environment!")
        sys.exit(1)
        
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "MotionForge_v0.1_Alpha",
        "--onedir",            # Directory mode is better for large models (MediaPipe)
        "--noconfirm",         # Overwrite existing dist map
        "--clean",
        add_data,
        
        # Required AI and GUI libraries
        "--hidden-import=mediapipe",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=pyqtgraph",
        "--hidden-import=PyQt5",
        
        # Internal Nexus Modules (so they get compiled even if conditionally imported)
        "--hidden-import=capture",
        "--hidden-import=bake",
        "--hidden-import=viewer",
        "--hidden-import=export_blender",
        "--hidden-import=calibrate",
        "--hidden-import=core",
        
        "src/launcher.py"
    ]
    
    print(f"\nRunning command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n[SUCCESS] --- BUILD COMPLETE ---")
        print("Executable is located in: dist/MotionForge_v0.1_Alpha/MotionForge_v0.1_Alpha.exe")
        print("NOTE: Make sure to run it from a location where 'data' and 'logs' folder can be accessed/created.")
    else:
        print("\n[ERROR] --- BUILD FAILED ---")

if __name__ == "__main__":
    main()
