class NexusStyle:
    # --- Professional Studio Colors ---
    BG_DARK = "#0b0f14"      # deep dark blue-black
    BG_PANEL = "#121821"     # panel background
    BG_CARD = "#1a212b"      # button/card background
    
    ACCENT_CYAN = "#00ffc3"  # neon cyan
    ACCENT_PINK = "#ff00ff"  # neon magenta
    ACCENT_YELLOW = "#ffff00" # neon yellow
    
    TEXT_MAIN = "#e6edf3"    # off-white
    TEXT_DIM = "#8b949e"     # slate gray
    TEXT_ERROR = "#ff5555"   # warning red

    # --- QSS Professional UI Rendering ---
    QSS = f"""
        QMainWindow {{ 
            background-color: {BG_DARK}; 
        }}

        QWidget {{ 
            background-color: transparent; 
            color: {TEXT_MAIN}; 
            font-family: 'Segoe UI', system-ui; 
            font-size: 13px;
        }}

        /* Panels & Sidebar */
        QFrame#SidePanel {{
            background-color: {BG_PANEL};
            border-right: 1px solid #232d3b;
        }}
        
        QFrame#RightPanel {{
            background-color: {BG_PANEL};
            border-left: 1px solid #232d3b;
        }}

        QFrame#BottomTimeline {{
            background-color: {BG_PANEL};
            border-top: 1px solid #232d3b;
        }}

        /* Buttons (Blender Style) */
        QPushButton {{
            background-color: {BG_CARD};
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
        }}

        QPushButton:hover {{
            background-color: #212830;
            border-color: {ACCENT_CYAN};
        }}

        QPushButton#PrimaryBtn {{
            border: 1px solid {ACCENT_CYAN};
            color: {ACCENT_CYAN};
        }}
        
        QPushButton#PrimaryBtn:hover {{
            background-color: rgba(0, 255, 195, 0.1);
        }}

        QPushButton#RecordBtn {{
            border: 1px solid {TEXT_ERROR};
            color: {TEXT_ERROR};
        }}
        
        QPushButton#RecordBtn:hover {{
            background-color: rgba(255, 85, 85, 0.1);
            color: #ffffff;
        }}

        /* Sliders */
        QSlider::groove:horizontal {{
            border: 1px solid #30363d;
            height: 4px;
            background: #212830;
            margin: 2px 0;
            border-radius: 2px;
        }}
        
        QSlider::handle:horizontal {{
            background: {ACCENT_CYAN};
            border: 1px solid {ACCENT_CYAN};
            width: 14px;
            height: 14px;
            margin: -6px 0;
            border-radius: 7px;
        }}

        /* Progress Bar */
        QProgressBar {{
            border: 1px solid #30363d;
            border-radius: 4px;
            text-align: center;
            background: {BG_DARK};
            height: 8px;
        }}
        
        QProgressBar::chunk {{
            background-color: {ACCENT_CYAN};
        }}

        /* Inputs */
        QLineEdit, QComboBox {{
            background-color: {BG_DARK};
            border: 1px solid #30363d;
            border-radius: 4px;
            padding: 6px;
        }}
        
        QLineEdit:focus {{
            border: 1px solid {ACCENT_CYAN};
        }}

        QLabel#Title {{
            font-size: 20px;
            font-weight: bold;
            color: {ACCENT_CYAN};
            letter-spacing: 1px;
        }}

        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 8px;
        }}
        
        QScrollBar::handle:vertical {{
            background: #30363d;
            min-height: 20px;
            border-radius: 4px;
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
