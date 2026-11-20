"""MotionForge desktop studio: capture, review, processing, and export."""
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows no longer searches a Python extension's folder for dependent DLLs
# automatically. MediaPipe ships OpenCV/native dependencies alongside this
# directory, so keep its DLL-directory handle alive before importing capture.
_DLL_DIRECTORY_HANDLES = []
if os.name == "nt" and hasattr(os, "add_dll_directory"):
    for search_root in sys.path:
        mediapipe_dll_dir = os.path.join(search_root, "mediapipe", "python")
        if os.path.isdir(mediapipe_dll_dir):
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(mediapipe_dll_dir))

# Load MediaPipe's native bindings before Qt loads its own bundled DLLs. On
# some Windows installations the two DLL search contexts otherwise conflict.
import mediapipe as _mediapipe  # noqa: E402

import cv2
from PyQt5 import QtCore, QtGui, QtSvg, QtWidgets

from bake import BakeThread
from capture import CaptureThread
from core.frame_model import UnifiedExporter
from core.logger import engine_logger
from core.mobile_camera import CameraSourceType
from export_blender import BlenderExporter
from ui.style import NexusStyle
from viewer import NexusViewport


class MotionForgeNexus(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MotionForge | Hareket Yakalama Stüdyosu")
        self.resize(1440, 900)
        self.setMinimumSize(980, 640)
        self.setStyleSheet(NexusStyle.QSS)
        self.preferences = QtCore.QSettings("Efeyasin46", "MotionForge")
        self.capture_thread = None
        self.bake_thread = None
        self.countdown_remaining = 0
        self.review_frames = []
        self.review_index = 0
        self.play_timer = QtCore.QTimer(self)
        self.play_timer.setInterval(33)
        self.play_timer.timeout.connect(self.advance_review)
        self.record_countdown_timer = QtCore.QTimer(self)
        self.record_countdown_timer.setInterval(1000)
        self.record_countdown_timer.timeout.connect(self.advance_recording_countdown)
        self._build_shell()
        self.refresh_library()
        engine_logger.info("MotionForge Studio initialized")

    def _build_shell(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav = QtWidgets.QFrame()
        nav.setObjectName("NavigationRail")
        nav.setFixedWidth(184)
        nav_layout = QtWidgets.QVBoxLayout(nav)
        nav_layout.setContentsMargins(16, 22, 16, 18)
        nav_layout.setSpacing(8)
        brand_row = QtWidgets.QWidget()
        brand_layout = QtWidgets.QHBoxLayout(brand_row)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(9)
        brand_icon = QtWidgets.QLabel()
        brand_icon.setFixedSize(36, 36)
        logo_path = self._asset_path("option-a-icon.svg")
        renderer = QtSvg.QSvgRenderer(str(logo_path))
        logo_pixmap = QtGui.QPixmap(36, 36)
        logo_pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(logo_pixmap)
        renderer.render(painter)
        painter.end()
        brand_icon.setPixmap(logo_pixmap)
        brand_icon.setAccessibleName("MotionForge Orbit M logosu")
        brand = QtWidgets.QLabel("MOTION\nFORGE")
        brand.setObjectName("Brand")
        brand_layout.addWidget(brand_icon)
        brand_layout.addWidget(brand)
        nav_layout.addWidget(brand_row)
        subtitle = QtWidgets.QLabel("MOCAP WORKSPACE")
        subtitle.setObjectName("Muted")
        nav_layout.addWidget(subtitle)
        nav_layout.addSpacing(30)

        self.pages = QtWidgets.QStackedWidget()
        self.nav_buttons = []
        for index, (label, builder) in enumerate([
            ("01  Kayıt stüdyosu", self._build_studio),
            ("02  Kayıtlarım", self._build_library),
            ("03  Dışa aktar", self._build_export),
            ("04  Ayarlar", self._build_settings),
        ]):
            button = QtWidgets.QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.open_page(i))
            nav_layout.addWidget(button)
            self.nav_buttons.append(button)
            self.pages.addWidget(builder())
        nav_layout.addStretch()
        version = QtWidgets.QLabel("MOTIONFORGE  •  LOCAL")
        version.setObjectName("Muted")
        nav_layout.addWidget(version)
        layout.addWidget(nav)
        layout.addWidget(self.pages, 1)
        self.open_page(0)

        self.statusBar().showMessage("Hazır  •  Kamerayı bağla veya kayıtlarını aç")

    def _page(self, title, description):
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(26, 22, 26, 24)
        outer.setSpacing(18)
        header = QtWidgets.QHBoxLayout()
        texts = QtWidgets.QVBoxLayout()
        heading = QtWidgets.QLabel(title)
        heading.setObjectName("PageTitle")
        detail = QtWidgets.QLabel(description)
        detail.setObjectName("Muted")
        texts.addWidget(heading)
        texts.addWidget(detail)
        header.addLayout(texts)
        header.addStretch()
        outer.addLayout(header)
        return page, outer

    def _build_studio(self):
        page, outer = self._page("Kayıt stüdyosu", "Takip modunu seç, kadrajı ayarla ve çekimini kaydet")

        source_bar = self._card("SETUP")
        setup = QtWidgets.QHBoxLayout(source_bar)
        setup.setContentsMargins(18, 14, 18, 14)
        setup.setSpacing(12)
        self.setup_summary = QtWidgets.QLabel("Webcam 0  ·  Tam vücut")
        self.setup_summary.setObjectName("Muted")
        setup.addWidget(self.setup_summary)
        setup.addStretch(1)
        self.btn_connect = QtWidgets.QPushButton("Kamerayı bağla")
        self.btn_connect.setObjectName("PrimaryButton")
        self.btn_connect.clicked.connect(self.toggle_engine)
        setup.addWidget(self.btn_connect)
        outer.addWidget(source_bar)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(14)
        viewport_card = self._card("KAMERA ÖNİZLEMESİ")
        viewport_layout = QtWidgets.QVBoxLayout(viewport_card)
        viewport_layout.setContentsMargins(12, 12, 12, 12)
        self.reference_preview = QtWidgets.QLabel("KAMERA GÖRÜNTÜSÜ\nKamerayı bağla")
        self.reference_preview.setObjectName("CameraPreview")
        self.reference_preview.setAlignment(QtCore.Qt.AlignCenter)
        self.reference_preview.setMinimumSize(250, 180)
        self.reference_preview.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        viewport_layout.addWidget(self.reference_preview, 1)
        self.status_label = QtWidgets.QLabel("KAMERA BAĞLI DEĞİL")
        self.status_label.setObjectName("LiveStatus")
        viewport_layout.addWidget(self.status_label)
        body.addWidget(viewport_card, 1)

        self.viewport = NexusViewport()
        self.viewport.setMinimumWidth(340)
        stage_card = self._card("CANLI 3D SAHNE")
        stage_layout = QtWidgets.QVBoxLayout(stage_card)
        stage_layout.setContentsMargins(12, 12, 12, 12)
        stage_layout.addWidget(self.viewport, 1)
        body.addWidget(stage_card, 1)

        inspector = self._card("ÇEKİM AYARLARI")
        inspector.setMinimumWidth(205)
        inspector.setMaximumWidth(250)
        controls = QtWidgets.QVBoxLayout(inspector)
        controls.setContentsMargins(18, 18, 18, 18)
        controls.setSpacing(12)
        self.btn_record = QtWidgets.QPushButton("Kaydı başlat")
        self.btn_record.setObjectName("RecordButton")
        self.btn_record.setEnabled(False)
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_record.setMinimumHeight(48)
        controls.addWidget(self.btn_record)
        self.capture_hint = QtWidgets.QLabel("Başlamak için web kameranı bağla. Kayıt sonunda adını ve konumunu seçebilirsin.")
        self.capture_hint.setObjectName("Muted")
        self.capture_hint.setWordWrap(True)
        controls.addWidget(self.capture_hint)
        divider = QtWidgets.QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QtWidgets.QFrame.HLine)
        controls.addWidget(divider)
        controls.addWidget(self._label("MEVCUT DOSYAYI İŞLE"))
        self.btn_bake = QtWidgets.QPushButton("Video / JSON işle…")
        self.btn_bake.clicked.connect(self.run_bake)
        controls.addWidget(self.btn_bake)
        self.bake_progress = QtWidgets.QProgressBar()
        self.bake_progress.setRange(0, 100)
        self.bake_progress.setVisible(False)
        controls.addWidget(self.bake_progress)
        reset = QtWidgets.QPushButton("Görünümü sıfırla")
        reset.clicked.connect(self.viewport.reset_view)
        controls.addWidget(reset)
        controls.addStretch(1)
        body.addWidget(inspector)
        outer.addLayout(body, 1)
        return page

    def _build_settings(self):
        page, outer = self._page(
            "Ayarlar", "Kamera, takip, kayıt ve dışa aktarım tercihlerini burada yönet"
        )
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 8)
        content_layout.setSpacing(14)

        capture_card = self._card("KAMERA VE KAYIT")
        capture_form = QtWidgets.QGridLayout(capture_card)
        capture_form.setContentsMargins(20, 18, 20, 18)
        capture_form.setHorizontalSpacing(18)
        capture_form.setVerticalSpacing(14)
        self.camera_index = QtWidgets.QSpinBox()
        self.camera_index.setRange(0, 9)
        self.camera_index.setToolTip("Windows kamera numarası; varsayılan webcam genellikle 0'dır")
        self.record_delay = QtWidgets.QSpinBox()
        self.record_delay.setRange(0, 30)
        self.record_delay.setSuffix(" sn")
        self.record_delay.setToolTip("Kayda başlamadan önceki geri sayım; 0 anında başlatır")
        self.capture_mode_combo = QtWidgets.QComboBox()
        self.capture_mode_combo.addItems(["Tam vücut", "Yüz ağı"])
        self.capture_mode_combo.setToolTip("Webcam görüntüsünde takip edilecek landmark türü")
        capture_rows = [
            ("Webcam numarası", self.camera_index),
            ("Takip modu", self.capture_mode_combo),
            ("Kayıt geri sayımı", self.record_delay),
        ]
        for row, (title, widget) in enumerate(capture_rows):
            label = self._label(title)
            label.setBuddy(widget)
            capture_form.addWidget(label, row, 0)
            capture_form.addWidget(widget, row, 1)
        capture_form.setColumnStretch(1, 1)
        content_layout.addWidget(capture_card)

        tracking_card = self._card("TAKİP VE GÖRÜNÜM")
        tracking_form = QtWidgets.QGridLayout(tracking_card)
        tracking_form.setContentsMargins(20, 18, 20, 18)
        tracking_form.setHorizontalSpacing(18)
        tracking_form.setVerticalSpacing(14)
        self.conf_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.conf_slider.setRange(30, 90)
        self.conf_slider.setToolTip("Bu değerin altındaki landmark güvenlerini kayda alma")
        self.conf_value = QtWidgets.QLabel("65%")
        self.conf_value.setObjectName("MetricValue")
        confidence_row = QtWidgets.QHBoxLayout()
        confidence_row.addWidget(self.conf_slider, 1)
        confidence_row.addWidget(self.conf_value)
        self.chk_ghost = QtWidgets.QCheckBox("3D sahnede hareket izlerini göster")
        self.chk_ghost.setToolTip("Önceki kareleri kısa bir iz olarak göster")
        for row, (title, widget) in enumerate([
            ("Minimum takip güveni", confidence_row),
            ("Sahne görünümü", self.chk_ghost),
        ]):
            label = self._label(title)
            if isinstance(widget, QtWidgets.QWidget):
                label.setBuddy(widget)
            tracking_form.addWidget(label, row, 0)
            if isinstance(widget, QtWidgets.QLayout):
                tracking_form.addLayout(widget, row, 1)
            else:
                tracking_form.addWidget(widget, row, 1)
        tracking_form.setColumnStretch(1, 1)
        content_layout.addWidget(tracking_card)

        export_card = self._card("DIŞA AKTARIM")
        export_form = QtWidgets.QGridLayout(export_card)
        export_form.setContentsMargins(20, 18, 20, 18)
        export_form.setHorizontalSpacing(18)
        export_form.setVerticalSpacing(14)
        self.default_export_target = QtWidgets.QComboBox()
        self.default_export_target.addItems([
            "Blender • BVH + JSON + Unity JSON",
            "Unity • nokta animasyonu JSON",
        ])
        self.default_export_target.setToolTip("Dışa aktar sayfasındaki varsayılan hedef biçim")
        label = self._label("Varsayılan hedef format")
        label.setBuddy(self.default_export_target)
        export_form.addWidget(label, 0, 0)
        export_form.addWidget(self.default_export_target, 0, 1)
        export_form.setColumnStretch(1, 1)
        content_layout.addWidget(export_card)

        actions = QtWidgets.QHBoxLayout()
        reset = QtWidgets.QPushButton("Varsayılanlara dön")
        reset.clicked.connect(self.reset_preferences)
        self.settings_status = QtWidgets.QLabel("Değişiklikler otomatik kaydedilir.")
        self.settings_status.setObjectName("Muted")
        actions.addWidget(reset)
        actions.addStretch()
        actions.addWidget(self.settings_status)
        content_layout.addLayout(actions)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self._load_preferences()
        self.camera_index.valueChanged.connect(self.save_preferences)
        self.capture_mode_combo.currentIndexChanged.connect(self.save_preferences)
        self.record_delay.valueChanged.connect(self.save_preferences)
        self.conf_slider.valueChanged.connect(self.on_confidence_changed)
        self.conf_slider.valueChanged.connect(self.save_preferences)
        self.chk_ghost.toggled.connect(self.save_preferences)
        self.default_export_target.currentIndexChanged.connect(self.save_preferences)
        return page

    @staticmethod
    def _asset_path(name):
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        return root / "assets" / "logos" / name

    def _load_preferences(self):
        self.camera_index.setValue(self.preferences.value("camera/index", 0, type=int))
        self.capture_mode_combo.setCurrentIndex(
            self.preferences.value("capture/mode", 0, type=int)
        )
        self.record_delay.setValue(self.preferences.value("record/countdown", 0, type=int))
        self.conf_slider.setValue(self.preferences.value("tracking/min_confidence", 65, type=int))
        self.chk_ghost.setChecked(self.preferences.value("view/show_ghost", False, type=bool))
        self.default_export_target.setCurrentIndex(
            self.preferences.value("export/default_target", 0, type=int)
        )
        self.conf_value.setText(f"{self.conf_slider.value()}%")
        self.viewport.show_ghost = self.chk_ghost.isChecked()
        self._update_setup_summary()

    def save_preferences(self, *_):
        self.preferences.setValue("camera/index", self.camera_index.value())
        self.preferences.setValue("capture/mode", self.capture_mode_combo.currentIndex())
        self.preferences.setValue("record/countdown", self.record_delay.value())
        self.preferences.setValue("tracking/min_confidence", self.conf_slider.value())
        self.preferences.setValue("view/show_ghost", self.chk_ghost.isChecked())
        self.preferences.setValue("export/default_target", self.default_export_target.currentIndex())
        self.preferences.sync()
        self._update_setup_summary()
        self.settings_status.setText("Ayarlar kaydedildi")

    def _update_setup_summary(self):
        if hasattr(self, "setup_summary"):
            mode = "Yüz ağı" if self.capture_mode_combo.currentIndex() == 1 else "Tam vücut"
            self.setup_summary.setText(f"Webcam {self.camera_index.value()}  ·  {mode}")

    def reset_preferences(self):
        for widget in (
            self.camera_index,
            self.capture_mode_combo,
            self.record_delay,
            self.conf_slider,
            self.chk_ghost,
            self.default_export_target,
        ):
            widget.blockSignals(True)
        self.camera_index.setValue(0)
        self.capture_mode_combo.setCurrentIndex(0)
        self.record_delay.setValue(0)
        self.conf_slider.setValue(65)
        self.chk_ghost.setChecked(False)
        self.default_export_target.setCurrentIndex(0)
        for widget in (
            self.camera_index,
            self.capture_mode_combo,
            self.record_delay,
            self.conf_slider,
            self.chk_ghost,
            self.default_export_target,
        ):
            widget.blockSignals(False)
        self.conf_value.setText("65%")
        self.save_preferences()

    def _build_library(self):
        page, outer = self._page("Kayıt arşivi", "Çekimlerini gözden geçir, oynat ve dışa aktarmaya hazırla")
        toolbar = QtWidgets.QHBoxLayout()
        self.library_count = QtWidgets.QLabel("0 kayıt")
        self.library_count.setObjectName("MetricValue")
        toolbar.addWidget(self.library_count)
        toolbar.addSpacing(18)
        self.library_search = QtWidgets.QLineEdit()
        self.library_search.setPlaceholderText("Kayıtlarda ara…")
        self.library_search.setMaximumWidth(300)
        self.library_search.textChanged.connect(self.filter_library)
        toolbar.addWidget(self.library_search)
        toolbar.addStretch()
        refresh = QtWidgets.QPushButton("Yenile")
        refresh.clicked.connect(self.refresh_library)
        toolbar.addWidget(refresh)
        outer.addLayout(toolbar)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(16)
        list_card = self._card("ÇEKİMLER")
        list_layout = QtWidgets.QVBoxLayout(list_card)
        list_layout.setContentsMargins(14, 14, 14, 14)
        self.library_table = QtWidgets.QTableWidget(0, 3)
        self.library_table.setHorizontalHeaderLabels(["Kayıt adı", "Kare", "Süre"])
        self.library_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.library_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.library_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.library_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.library_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.library_table.setAlternatingRowColors(True)
        self.library_table.verticalHeader().hide()
        self.library_table.setShowGrid(False)
        self.library_table.setMinimumWidth(360)
        self.library_table.itemSelectionChanged.connect(self.select_library_take)
        list_layout.addWidget(self.library_table)
        self.library_empty = QtWidgets.QLabel("Henüz burada kayıt yok. Stüdyo ekranında kayıt al veya JSON dosyası aç.")
        self.library_empty.setObjectName("EmptyState")
        self.library_empty.setWordWrap(True)
        list_layout.addWidget(self.library_empty)
        buttons = QtWidgets.QHBoxLayout()
        open_button = QtWidgets.QPushButton("JSON aç…")
        open_button.clicked.connect(self.open_json)
        buttons.addWidget(open_button)
        self.review_play = QtWidgets.QPushButton("Oynat")
        self.review_play.clicked.connect(self.toggle_review)
        buttons.addWidget(self.review_play)
        list_layout.addLayout(buttons)
        body.addWidget(list_card, 1)

        preview = self._card("ÖNİZLEME")
        preview_layout = QtWidgets.QVBoxLayout(preview)
        self.library_viewport = NexusViewport()
        preview_layout.addWidget(self.library_viewport, 1)
        self.review_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.review_slider.setRange(0, 0)
        self.review_slider.valueChanged.connect(self.scrub_review)
        preview_layout.addWidget(self.review_slider)
        self.review_info = QtWidgets.QLabel("Önizlemek için bir kayıt seç")
        self.review_info.setObjectName("Muted")
        preview_layout.addWidget(self.review_info)
        body.addWidget(preview, 1)
        outer.addLayout(body, 1)
        self.recording_paths = []
        return page

    def _build_export(self):
        page, outer = self._page("Dışa aktar", "Kayıtlarını Blender veya Unity için dosyaya dönüştür")
        card = self._card("DIŞA AKTARIM AKIŞI")
        form = QtWidgets.QGridLayout(card)
        form.setContentsMargins(24, 24, 24, 24)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(16)
        form.addWidget(self._label("KAYNAK KAYIT"), 0, 0)
        self.export_source = QtWidgets.QLineEdit()
        self.export_source.setPlaceholderText("Arşivden seç veya bir JSON kaydı aç")
        form.addWidget(self.export_source, 0, 1)
        browse = QtWidgets.QPushButton("Gözat…")
        browse.clicked.connect(self.choose_export_source)
        form.addWidget(browse, 0, 2)
        form.addWidget(self._label("HEDEF FORMAT"), 1, 0)
        self.export_target = QtWidgets.QComboBox()
        self.export_target.addItems(["Blender • BVH + JSON + Unity JSON", "Unity • nokta animasyonu JSON"])
        form.addWidget(self.export_target, 1, 1, 1, 2)
        form.addWidget(self._label("DOSYA ADI VE KONUMU"), 2, 0)
        self.export_path = QtWidgets.QLineEdit()
        self.export_path.setPlaceholderText("Dosya adını ve kaydedilecek klasörü seç")
        form.addWidget(self.export_path, 2, 1)
        choose_file = QtWidgets.QPushButton("Dosya seç…")
        choose_file.clicked.connect(self.choose_export_path)
        form.addWidget(choose_file, 2, 2)
        self.export_button = QtWidgets.QPushButton("Dışa aktar")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self.run_export)
        form.addWidget(self.export_button, 3, 1)
        self.export_result = QtWidgets.QLabel("Önce bir kaynak kayıt seç. Blender hedefi birden fazla ilişkili dosya oluşturur.")
        self.export_result.setObjectName("Muted")
        self.export_result.setWordWrap(True)
        form.addWidget(self.export_result, 4, 1, 1, 2)
        outer.addWidget(card)
        outer.addStretch()
        return page

    def _card(self, title):
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setProperty("cardTitle", title)
        return frame

    @staticmethod
    def _label(text):
        label = QtWidgets.QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def open_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index == 1:
            self.refresh_library()
        if index == 2:
            self.export_target.setCurrentIndex(self.default_export_target.currentIndex())

    def toggle_engine(self):
        if self.capture_thread and self.capture_thread.isRunning():
            self.stop_engine()
            return
        source_type, source_info = CameraSourceType.WEBCAM, self.camera_index.value()
        self.capture_thread = CaptureThread(
            source_type,
            source_info,
            min_confidence=self.conf_slider.value() / 100.0,
            capture_mode="face" if self.capture_mode_combo.currentIndex() == 1 else "full_body",
        )
        self.capture_thread.frame_ready.connect(self.viewport.render_frame)
        self.capture_thread.image_ready.connect(self.on_reference_image)
        self.capture_thread.status_msg.connect(self.on_capture_status)
        self.capture_thread.start()
        self.btn_connect.setText("Bağlantıyı kes")
        self.btn_record.setEnabled(True)
        self.status_label.setText("BAĞLANIYOR")

    def on_reference_image(self, image):
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width, channels = image.shape
        rgb = QtGui.QImage(image.data, width, height, channels * width, QtGui.QImage.Format_RGB888).copy()
        self.reference_preview.setPixmap(QtGui.QPixmap.fromImage(rgb).scaled(
            self.reference_preview.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def on_capture_status(self, text):
        self.status_label.setText(text.upper())
        self.statusBar().showMessage(text)
        if text.startswith("ERROR:"):
            self.cancel_recording_countdown(show_message=False)
            self.btn_connect.setText("Kamerayı bağla")
            self.btn_record.setEnabled(False)
            self.status_label.setText("KAMERA AÇILAMADI")
            self.capture_hint.setText(self.camera_error_details(text))
            self.notify_error(
                "Kamera kullanılamıyor" if "camera" in text.lower() else "Yakalama hatası",
                self.camera_error_details(text),
            )
        if "SAVED:" in text:
            self.record_delay.setEnabled(True)
            self.btn_record.setText("Kaydı başlat")
            self.status_label.setText("KAYIT KAYDEDİLDİ")
            self.statusBar().showMessage(f"Kayıt kaydedildi: {text.split('SAVED:', 1)[1].strip()}", 8000)
            self.btn_record.setProperty("recording", False)
            self.btn_record.style().unpolish(self.btn_record)
            self.btn_record.style().polish(self.btn_record)
            self.refresh_library()

    def stop_engine(self):
        self.cancel_recording_countdown(show_message=False)
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread = None
        self.btn_connect.setText("Kamerayı bağla")
        self.btn_record.setEnabled(False)
        self.status_label.setText("HAZIR")

    def toggle_recording(self):
        if not self.capture_thread:
            return
        if self.record_countdown_timer.isActive():
            self.cancel_recording_countdown()
            return
        if self.capture_thread.is_recording:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            suggested_name = os.path.abspath(
                os.path.join("data", f"MotionForge_{timestamp}.json")
            )
            output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Hareket kaydını kaydet",
                suggested_name,
                "MotionForge kaydı (*.json)",
            )
            if not output_path:
                self.statusBar().showMessage("Kaydetme iptal edildi; kayıt devam ediyor", 5000)
                return
            if not output_path.lower().endswith(".json"):
                output_path += ".json"
            try:
                self.capture_thread.stop_recording(output_path)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Kayıt kaydedilemedi", str(exc))
                return
            self.record_delay.setEnabled(True)
            self.btn_record.setText("Kaydı başlat")
            self.btn_record.setProperty("recording", False)
            self.btn_record.style().unpolish(self.btn_record)
            self.btn_record.style().polish(self.btn_record)
            self.status_label.setText("KAYDEDİLİYOR")
            return

        delay = self.record_delay.value()
        if delay <= 0:
            self.start_recording_now()
            return
        self.countdown_remaining = delay
        self.record_delay.setEnabled(False)
        self.btn_record.setText("Geri sayımı iptal et")
        self.status_label.setText(f"{delay} SN SONRA BAŞLIYOR")
        self.statusBar().showMessage(
            f"Kayıt {delay} saniye içinde başlayacak. İptal etmek için düğmeye bas."
        )
        self.capture_hint.setText("Kadrajda yerini al; geri sayım bitince kayıt başlayacak.")
        self.record_countdown_timer.start()

    def advance_recording_countdown(self):
        self.countdown_remaining -= 1
        if self.countdown_remaining <= 0:
            self.record_countdown_timer.stop()
            self.start_recording_now()
            return
        self.status_label.setText(f"{self.countdown_remaining} SN SONRA BAŞLIYOR")
        self.statusBar().showMessage(
            f"Kayıt {self.countdown_remaining} saniye içinde başlayacak. İptal etmek için düğmeye bas."
        )

    def cancel_recording_countdown(self, show_message=True):
        if not self.record_countdown_timer.isActive():
            return
        self.record_countdown_timer.stop()
        self.countdown_remaining = 0
        self.record_delay.setEnabled(True)
        self.btn_record.setText("Kaydı başlat")
        self.status_label.setText("BAĞLI" if self.capture_thread else "HAZIR")
        if show_message:
            self.statusBar().showMessage("Geri sayım iptal edildi", 5000)

    def start_recording_now(self):
        if not self.capture_thread or not self.capture_thread.isRunning():
            self.cancel_recording_countdown(show_message=False)
            self.btn_record.setText("Kaydı başlat")
            self.record_delay.setEnabled(True)
            self.status_label.setText("KAMERA BAĞLI DEĞİL")
            self.statusBar().showMessage("Kayıt için önce kamerayı bağla", 5000)
            return
        self.capture_thread.start_recording()
        self.record_delay.setEnabled(False)
        self.btn_record.setText("Durdur ve kaydet")
        self.btn_record.setProperty("recording", True)
        self.btn_record.style().unpolish(self.btn_record)
        self.btn_record.style().polish(self.btn_record)
        self.status_label.setText("KAYIT ALINIYOR")
        self.statusBar().showMessage("Kayıt başladı")

    def on_confidence_changed(self, value):
        self.conf_value.setText(f"{value}%")
        if self.capture_thread:
            self.capture_thread.min_confidence = value / 100.0

    def run_bake(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "İşlenecek video veya hareket kaydını seç", "data",
            "MotionForge ve video (*.json *.mp4 *.mov *.avi *.mkv)"
        )
        if not path:
            return
        self.stop_engine()
        self.bake_thread = BakeThread(path)
        self.bake_thread.progress.connect(self.bake_progress.setValue)
        self.bake_thread.status.connect(self.on_bake_status)
        self.bake_thread.bake_done.connect(self.on_bake_finished)
        self.bake_progress.setVisible(True)
        self.bake_progress.setValue(0)
        self.bake_thread.start()

    def on_bake_status(self, text):
        self.statusBar().showMessage(text)
        if text.startswith("ERROR:"):
            detail = text.removeprefix("ERROR:").strip()
            friendly = {
                "Invalid Input": "Seçilen dosya bulunamadı. Dosya yolunu kontrol edip yeniden seç.",
                "Could not open video": "Video açılamadı. Dosyanın bozuk olmadığını kontrol et.",
            }.get(detail, detail)
            self.statusBar().showMessage(f"İşleme hatası: {friendly}")
            self.notify_error("İşleme başarısız", friendly)

    def notify_error(self, title, message):
        """Show actionable errors in a dialog as well as the status bar."""
        QtWidgets.QMessageBox.warning(self, title, message)

    @staticmethod
    def camera_error_details(error):
        message = error.removeprefix("ERROR:").strip()
        if "no camera found" in message.lower():
            return (
                "Web kamerası açılamadı. Bağlantısını kontrol et, kamerayı kullanan diğer "
                "uygulamaları kapat ve Windows Ayarları'ndan kamera erişimine izin ver."
            )
        return message

    def on_bake_finished(self, output_path):
        self.bake_progress.setVisible(False)
        self.refresh_library()
        self.statusBar().showMessage(f"İşlem tamamlandı • {output_path}", 10000)
        QtWidgets.QMessageBox.information(
            self, "İşlem tamamlandı", f"İşlenmiş kayıt kaydedildi:\n{output_path}"
        )

    def refresh_library(self):
        if not hasattr(self, "library_table"):
            return
        os.makedirs("data", exist_ok=True)
        paths = sorted((os.path.join("data", name) for name in os.listdir("data")
                        if name.lower().endswith(".json") and not name.endswith(("_unity.json", "_blender.json", "_debug_report.json"))),
                       key=os.path.getmtime, reverse=True)
        self.recording_paths = []
        self.library_table.setRowCount(0)
        for path in paths:
            try:
                frames = UnifiedExporter.load_recording(path)
                duration = frames[-1].timestamp - frames[0].timestamp if len(frames) > 1 else 0
                row = self.library_table.rowCount()
                self.library_table.insertRow(row)
                self.library_table.setItem(row, 0, QtWidgets.QTableWidgetItem(os.path.basename(path)))
                self.library_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(len(frames))))
                self.library_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{duration:.1f} s"))
                self.recording_paths.append(path)
            except Exception:
                continue
        count = self.library_table.rowCount()
        self.library_count.setText(f"{count} kayıt")
        self.library_empty.setVisible(count == 0)
        self.filter_library()

    def filter_library(self):
        if not hasattr(self, "library_table"):
            return
        query = self.library_search.text().strip().casefold()
        for row in range(self.library_table.rowCount()):
            item = self.library_table.item(row, 0)
            self.library_table.setRowHidden(
                row, bool(query and query not in item.text().casefold())
            )

    def select_library_take(self):
        row = self.library_table.currentRow()
        if row < 0 or row >= len(self.recording_paths):
            return
        path = self.recording_paths[row]
        try:
            self.review_frames = UnifiedExporter.load_recording(path)
            self.review_index = 0
            self.review_slider.setMaximum(max(0, len(self.review_frames) - 1))
            self.review_info.setText(f"{os.path.basename(path)} • {len(self.review_frames)} frames")
            self.render_review_frame()
            self.export_source.setText(os.path.abspath(path))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Kayıt açılamadı", str(exc))

    def open_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open motion recording", "data", "JSON (*.json)")
        if path:
            self.load_review_path(path)

    def load_review_path(self, path):
        for row, candidate in enumerate(self.recording_paths):
            if os.path.abspath(candidate) == os.path.abspath(path):
                self.library_table.selectRow(row)
                return
        try:
            self.review_frames = UnifiedExporter.load_recording(path)
            self.review_index = 0
            self.review_slider.setMaximum(max(0, len(self.review_frames) - 1))
            self.review_info.setText(f"{os.path.basename(path)} • {len(self.review_frames)} frames")
            self.render_review_frame()
            self.export_source.setText(os.path.abspath(path))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Kayıt açılamadı", str(exc))

    def toggle_review(self):
        if not self.review_frames:
            return
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.review_play.setText("Oynat")
        else:
            self.play_timer.start()
            self.review_play.setText("Duraklat")

    def advance_review(self):
        if not self.review_frames:
            self.play_timer.stop()
            return
        self.review_index = (self.review_index + 1) % len(self.review_frames)
        self.review_slider.blockSignals(True)
        self.review_slider.setValue(self.review_index)
        self.review_slider.blockSignals(False)
        self.render_review_frame()

    def scrub_review(self, frame_index):
        if self.review_frames:
            self.review_index = min(frame_index, len(self.review_frames) - 1)
            self.render_review_frame()

    def render_review_frame(self):
        if self.review_frames:
            self.library_viewport.render_frame(self.review_frames[self.review_index], offset_z=False)

    def choose_export_source(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose recording", "data", "JSON (*.json)")
        if path:
            self.export_source.setText(os.path.abspath(path))

    def choose_export_path(self):
        source = self.export_source.text().strip()
        base = os.path.splitext(os.path.basename(source))[0] or "MotionForge_export"
        target = "unity" if self.export_target.currentIndex() == 1 else "blender"
        current = self.export_path.text().strip()
        if not current:
            current = os.path.abspath(os.path.join("data", f"{base}_{target}.json"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Choose export file name and location",
            current,
            "JSON file (*.json)",
        )
        if path:
            if not path.lower().endswith(".json"):
                path += ".json"
            self.export_path.setText(os.path.abspath(path))

    def run_export(self):
        source = self.export_source.text().strip()
        output = self.export_path.text().strip()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.warning(self, "Kayıt seç", "Önce geçerli bir MotionForge JSON kaydı seç.")
            return
        if not output:
            self.choose_export_path()
            output = self.export_path.text().strip()
        if not output:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
            frames = UnifiedExporter.load_recording(source)
            if frames and frames[0].meta.get("capture_mode") == "face":
                if self.export_target.currentIndex() == 0:
                    self.notify_error(
                        "Yüz ağı dışa aktarımı",
                        "Yüz kayıtları gövde iskeleti içermez. Bu noktaları dışa aktarmak için "
                        "Unity nokta animasyonu JSON biçimini seç.",
                    )
                    return
            exporter = BlenderExporter(source)
            if self.export_target.currentIndex() == 1:
                exporter.export_unity(output)
                files = [output]
            else:
                stem = os.path.splitext(output)[0]
                report = f"{stem}_report.json"
                files = list(exporter.export(output, report))
            self.export_result.setText("Oluşturulan dosyalar:\n" + "\n".join(files))
            self.statusBar().showMessage("Dışa aktarım tamamlandı", 8000)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Dışa aktarım başarısız", str(exc))

    def closeEvent(self, event):
        self.play_timer.stop()
        self.record_countdown_timer.stop()
        if self.capture_thread and self.capture_thread.isRunning():
            self.stop_engine()
        if self.bake_thread and self.bake_thread.isRunning():
            self.bake_thread.requestInterruption()
            self.bake_thread.wait(3000)
        event.accept()


def main():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Segoe UI Variable", 10))
    window = MotionForgeNexus()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
