@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe uv venv --python 3.11 .venv
call .venv\Scripts\activate.bat
uv pip install -e ".[dev]" pyinstaller
python build.py
if errorlevel 1 exit /b 1
echo Build complete: dist\MotionForge\MotionForge.exe
pause
