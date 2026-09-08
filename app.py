import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from renderer import render_video


AUDIO_EXTENSIONS = {".wav"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class RenderWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        image_path: str,
        audio_path: str,
        output_dir: str,
        intro_path: Optional[str],
    ):
        super().__init__()

        self.image_path = image_path
        self.audio_path = audio_path
        self.output_dir = output_dir
        self.intro_path = intro_path

    def run(self):
        try:
            output_path = render_video(
                image_path=self.image_path,
                audio_path=self.audio_path,
                output_dir=self.output_dir,
                intro_path=self.intro_path,
                progress_callback=self.report_progress,
            )

            self.finished.emit(str(output_path))

        except Exception as error:
            self.failed.emit(str(error))

    def report_progress(self, progress: float):
        self.progress.emit(int(progress * 100))


class BeatFrame(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BeatFrame")
        self.resize(760, 620)
        self.setMinimumSize(680, 560)
        self.setAcceptDrops(True)

        self.settings = QSettings("BeatFrame", "BeatFrame")

        default_output = str(Path.home() / "Desktop")

        self.output_dir = self.settings.value(
            "output_dir",
            default_output,
        )

        self.intro_path = self.settings.value(
            "intro_path",
            "",
        )

        self.thread = None
        self.worker = None
        self.is_rendering = False

        self.build_ui()
        self.apply_styles()
        self.update_intro_label()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(36, 30, 36, 30)
        main_layout.setSpacing(18)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        title = QLabel("BeatFrame")
        title.setObjectName("title")

        subtitle = QLabel("Artwork + audio → YouTube-ready video")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        main_layout.addLayout(header_layout)

        self.drop_frame = QFrame()
        self.drop_frame.setObjectName("dropFrame")
        self.drop_frame.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setContentsMargins(40, 40, 40, 40)
        drop_layout.setSpacing(10)
        drop_layout.setAlignment(Qt.AlignCenter)

        self.status_icon = QLabel("＋")
        self.status_icon.setObjectName("statusIcon")
        self.status_icon.setAlignment(Qt.AlignCenter)

        self.main_label = QLabel("Drop your artwork + beat here")
        self.main_label.setObjectName("mainLabel")
        self.main_label.setAlignment(Qt.AlignCenter)

        self.detail_label = QLabel("WAV + JPG / PNG")
        self.detail_label.setObjectName("detailLabel")
        self.detail_label.setAlignment(Qt.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()

        drop_layout.addStretch()
        drop_layout.addWidget(self.status_icon)
        drop_layout.addWidget(self.main_label)
        drop_layout.addWidget(self.detail_label)
        drop_layout.addSpacing(14)
        drop_layout.addWidget(self.progress_bar)
        drop_layout.addStretch()

        main_layout.addWidget(self.drop_frame, 1)

        output_section = QFrame()
        output_section.setObjectName("settingsSection")

        output_layout = QHBoxLayout(output_section)
        output_layout.setContentsMargins(18, 14, 18, 14)
        output_layout.setSpacing(16)

        output_text_layout = QVBoxLayout()
        output_text_layout.setSpacing(2)

        output_title = QLabel("Output folder")
        output_title.setObjectName("sectionTitle")

        self.output_label = QLabel(self.output_dir)
        self.output_label.setObjectName("sectionValue")

        output_text_layout.addWidget(output_title)
        output_text_layout.addWidget(self.output_label)

        self.output_button = QPushButton("Change")
        self.output_button.setObjectName("settingsButton")
        self.output_button.clicked.connect(
            self.choose_output_folder
        )

        output_layout.addLayout(output_text_layout, 1)
        output_layout.addWidget(self.output_button)

        main_layout.addWidget(output_section)

        intro_section = QFrame()
        intro_section.setObjectName("settingsSection")

        intro_layout = QHBoxLayout(intro_section)
        intro_layout.setContentsMargins(18, 14, 18, 14)
        intro_layout.setSpacing(16)

        intro_text_layout = QVBoxLayout()
        intro_text_layout.setSpacing(2)

        intro_title = QLabel("Intro")
        intro_title.setObjectName("sectionTitle")

        self.intro_label = QLabel()
        self.intro_label.setObjectName("sectionValue")

        intro_text_layout.addWidget(intro_title)
        intro_text_layout.addWidget(self.intro_label)

        self.intro_button = QPushButton("Choose")
        self.intro_button.setObjectName("settingsButton")
        self.intro_button.clicked.connect(
            self.choose_intro
        )

        self.clear_intro_button = QPushButton("Remove")
        self.clear_intro_button.setObjectName("secondaryButton")
        self.clear_intro_button.clicked.connect(
            self.clear_intro
        )

        intro_layout.addLayout(intro_text_layout, 1)
        intro_layout.addWidget(self.clear_intro_button)
        intro_layout.addWidget(self.intro_button)

        main_layout.addWidget(intro_section)

    def apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #111214;
            }

            QWidget {
                color: #f3f3f3;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 14px;
            }

            QLabel#title {
                font-size: 30px;
                font-weight: 700;
                color: #ffffff;
            }

            QLabel#subtitle {
                font-size: 14px;
                color: #8f939b;
            }

            QFrame#dropFrame {
                background-color: #181a1e;
                border: 2px dashed #3a3d44;
                border-radius: 18px;
            }

            QLabel#statusIcon {
                font-size: 34px;
                font-weight: 300;
                color: #7f8490;
                padding-bottom: 4px;
            }

            QLabel#mainLabel {
                font-size: 20px;
                font-weight: 600;
                color: #ffffff;
            }

            QLabel#detailLabel {
                font-size: 13px;
                color: #7f8490;
            }

            QProgressBar#progressBar {
                min-height: 12px;
                max-height: 12px;
                border: none;
                border-radius: 6px;
                background-color: #2a2d33;
                text-align: center;
                color: transparent;
            }

            QProgressBar#progressBar::chunk {
                border-radius: 6px;
                background-color: #ffffff;
            }

            QFrame#settingsSection {
                background-color: #181a1e;
                border: 1px solid #26292f;
                border-radius: 14px;
            }

            QLabel#sectionTitle {
                font-size: 13px;
                font-weight: 600;
                color: #ffffff;
            }

            QLabel#sectionValue {
                font-size: 12px;
                color: #7f8490;
            }

            QPushButton#settingsButton,
            QPushButton#secondaryButton {
                border-radius: 9px;
                padding: 8px 16px;
                font-weight: 600;
            }

            QPushButton#settingsButton {
                background-color: #25282e;
                border: 1px solid #343840;
                color: #f3f3f3;
            }

            QPushButton#settingsButton:hover {
                background-color: #2e3239;
            }

            QPushButton#secondaryButton {
                background-color: transparent;
                border: 1px solid #2b2e34;
                color: #8f939b;
            }

            QPushButton#secondaryButton:hover {
                background-color: #202329;
                color: #f3f3f3;
            }

            QPushButton:disabled {
                color: #5f636c;
                background-color: #1d1f23;
                border-color: #25282e;
            }
            """
        )

    def choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose output folder",
            self.output_dir,
        )

        if not folder:
            return

        self.output_dir = folder
        self.settings.setValue("output_dir", self.output_dir)
        self.output_label.setText(self.output_dir)

    def choose_intro(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose intro video",
            str(Path.home()),
            "Video files (*.mp4)",
        )

        if not file_path:
            return

        self.intro_path = file_path
        self.settings.setValue("intro_path", self.intro_path)
        self.update_intro_label()

    def clear_intro(self):
        self.intro_path = ""
        self.settings.remove("intro_path")
        self.update_intro_label()

    def update_intro_label(self):
        if self.intro_path:
            self.intro_label.setText(
                Path(self.intro_path).name
            )
            self.clear_intro_button.setEnabled(True)
        else:
            self.intro_label.setText("None")
            self.clear_intro_button.setEnabled(False)

    def set_controls_enabled(self, enabled: bool):
        self.output_button.setEnabled(enabled)
        self.intro_button.setEnabled(enabled)

        if enabled:
            self.update_intro_label()
        else:
            self.clear_intro_button.setEnabled(False)

    def dragEnterEvent(self, event):
        if self.is_rendering:
            return

        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.is_rendering:
            return

        files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]

        audio = next(
            (
                file
                for file in files
                if file.suffix.lower() in AUDIO_EXTENSIONS
            ),
            None,
        )

        artwork = next(
            (
                file
                for file in files
                if file.suffix.lower() in IMAGE_EXTENSIONS
            ),
            None,
        )

        if not audio or not artwork:
            self.status_icon.setText("!")
            self.main_label.setText("I need one WAV + one image")
            self.detail_label.setText(
                "Supported: WAV, JPG, JPEG, PNG"
            )
            return

        self.is_rendering = True
        self.set_controls_enabled(False)

        self.status_icon.setText("●")
        self.main_label.setText(audio.stem)
        self.detail_label.setText(
            f"{audio.name}  +  {artwork.name}"
        )

        self.progress_bar.setValue(0)
        self.progress_bar.show()

        intro_path = self.intro_path or None

        self.start_render(
            image_path=str(artwork),
            audio_path=str(audio),
            output_dir=self.output_dir,
            intro_path=intro_path,
        )

    def start_render(
        self,
        image_path: str,
        audio_path: str,
        output_dir: str,
        intro_path: Optional[str],
    ):
        self.thread = QThread()

        self.worker = RenderWorker(
            image_path=image_path,
            audio_path=audio_path,
            output_dir=output_dir,
            intro_path=intro_path,
        )

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.progress.connect(
            self.update_progress
        )

        self.worker.finished.connect(
            self.render_finished
        )

        self.worker.failed.connect(
            self.render_failed
        )

        self.worker.finished.connect(
            self.thread.quit
        )

        self.worker.failed.connect(
            self.thread.quit
        )

        self.thread.finished.connect(
            self.worker.deleteLater
        )

        self.thread.finished.connect(
            self.thread.deleteLater
        )

        self.thread.start()

    def update_progress(self, percent: int):
        self.progress_bar.setValue(percent)
        self.detail_label.setText(
            f"Rendering... {percent}%"
        )

    def render_finished(self, output_path: str):
        self.progress_bar.setValue(100)

        self.status_icon.setText("✓")
        self.main_label.setText("Ready")
        self.detail_label.setText(
            Path(output_path).name
        )

        self.is_rendering = False
        self.set_controls_enabled(True)

    def render_failed(self, error: str):
        self.progress_bar.hide()

        self.status_icon.setText("!")
        self.main_label.setText("Render failed")
        self.detail_label.setText(error)

        self.is_rendering = False
        self.set_controls_enabled(True)


app = QApplication(sys.argv)

window = BeatFrame()
window.show()

sys.exit(app.exec())