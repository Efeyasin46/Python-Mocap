import sys
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
print("PyQt5 Diagnostic Start")
try:
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("DIAGNOSTIC TEST")
    label = QLabel("IF YOU SEE THIS, PYQT5 IS WORKING")
    win.setCentralWidget(label)
    win.show()
    print("Window show() called")
    # Auto-quit after 3 seconds for test
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(3000, app.quit)
    sys.exit(app.exec_())
except Exception as e:
    print(f"Error: {e}")
