"""MotionForge visual tokens and application-wide Qt stylesheet."""


class NexusStyle:
    BG = "#090b11"
    PANEL = "#10141d"
    CARD = "#141a25"
    BORDER = "#283244"
    TEXT = "#f3f5fa"
    MUTED = "#a4aec0"
    ACCENT = "#b6f36b"
    ACCENT_HOVER = "#caf995"
    RED = "#ff6e78"

    QSS = f"""
        * {{ font-family: 'Segoe UI Variable'; font-size: 13px; color: {TEXT}; outline: none; }}
        QMainWindow {{ background: {BG}; }}
        QWidget {{ background: transparent; }}
        QFrame#NavigationRail {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
        QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
        QLabel#Brand {{ font-size: 21px; font-weight: 800; letter-spacing: 1px; color: {TEXT}; }}
        QLabel#PageTitle {{ font-size: 28px; font-weight: 750; }}
        QLabel#Muted {{ color: {MUTED}; background: transparent; }}
        QLabel#LiveStatus {{ color: {ACCENT}; font-weight: 700; letter-spacing: 1px; padding: 4px 8px; }}
        QLabel#MetricValue {{ color: {ACCENT}; font-weight: 700; }}
        QLabel#FieldLabel {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; }}
        QLabel#EmptyState {{ color: {MUTED}; background: transparent; border: 1px dashed {BORDER}; border-radius: 10px; padding: 16px; }}
        QLabel#CameraPreview {{ background: #080b10; border: 1px dashed #3a4658; border-radius: 10px; color: {MUTED}; }}
        QFrame#Divider {{ color: {BORDER}; max-height: 1px; }}
        QPushButton {{ background: #202635; border: 1px solid {BORDER}; border-radius: 9px; padding: 10px 14px; min-height: 20px; font-weight: 600; }}
        QPushButton:hover {{ background: #2a3243; border-color: #526078; }}
        QPushButton:pressed {{ background: #353f52; }}
        QPushButton:focus {{ border: 2px solid {ACCENT}; }}
        QPushButton:disabled {{ color: #858fa0; background: #171c26; border-color: #252d3b; }}
        QPushButton#NavButton {{ text-align: left; background: transparent; border: 0; border-left: 3px solid transparent; padding: 12px; color: {MUTED}; }}
        QPushButton#NavButton:hover, QPushButton#NavButton:checked {{ background: #202c36; color: {TEXT}; border-left: 3px solid {ACCENT}; }}
        QPushButton#PrimaryButton {{ background: {ACCENT}; color: #11170c; border: 0; }}
        QPushButton#PrimaryButton:hover {{ background: {ACCENT_HOVER}; }}
        QPushButton#RecordButton {{ color: #ffb2b8; border-color: #85434b; background: #2a171d; }}
        QPushButton#RecordButton:hover {{ background: #3a1d25; border-color: {RED}; }}
        QPushButton#RecordButton[recording="true"] {{ color: white; background: {RED}; border-color: {RED}; }}
        QComboBox, QLineEdit, QTableWidget, QSpinBox {{ background: #0e151c; border: 1px solid {BORDER}; border-radius: 7px; padding: 9px; selection-background-color: #24564e; }}
        QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QTableWidget:focus {{ border: 2px solid {ACCENT}; }}
        QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: #24564e; border: 1px solid {BORDER}; }}
        QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: 0; border-bottom: 1px solid {BORDER}; padding: 11px; font-weight: 650; }}
        QTableWidget {{ gridline-color: {BORDER}; }}
        QTableWidget::item {{ padding: 7px; border-bottom: 1px solid {BORDER}; }}
        QTableWidget::item:selected {{ background: #21433f; color: {TEXT}; }}
        QProgressBar {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; min-height: 14px; }}
        QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
        QSlider::groove:horizontal {{ background: {BORDER}; height: 4px; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -5px 0; border-radius: 7px; }}
        QCheckBox {{ spacing: 8px; }}
        QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
        QScrollBar:vertical {{ background: transparent; width: 9px; }}
        QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
    """
