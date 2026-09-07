import sys
from pathlib import Path

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

    def __init__(self, image_path: str, audio_path: str, output_dir: str):
        super().__init__()
        self.image_path = image_path
        self.audio_path = audio_path
        self.output_dir = output_dir

    def run(self):
        try:
            output_path = render_video(
                image_path=self.image_path,
                audio_path=self.audio_path,
                output_dir=self.output_dir,
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
        self.resize(760, 560)
        self.setMinimumSize(680, 500)
        self.setAcceptDrops(True)

        self.settings = QSettings("BeatFrame", "BeatFrame")

        default_output = str(Path.home() / "Desktop")
        self.output_dir = self.settings.value(
            "output_dir",
            default_output,
        )

        self.thread = None
        self.worker = None
        self.is_rendering = False

        self.build_ui()
        self.apply_styles()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(36, 30, 36, 30)
        main_layout.setSpacing(24)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        title = QLabel("BeatFrame")
        title.setObjectName("title")

        subtitle = QLabel("Artwork + audio → YouTube-ready video")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        main_layout.addLayout(header_layout)

        # Drop zone
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

        # Output section
        output_section = QFrame()
        output_section.setObjectName("outputSection")

        output_layout = QHBoxLayout(output_section)
        output_layout.setContentsMargins(18, 14, 18, 14)
        output_layout.setSpacing(16)

        output_text_layout = QVBoxLayout()
        output_text_layout.setSpacing(2)

        output_title = QLabel("Output folder")
        output_title.setObjectName("outputTitle")

        self.output_label = QLabel(self.output_dir)
        self.output_label.setObjectName("outputPath")
        self.output_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        output_text_layout.addWidget(output_title)
        output_text_layout.addWidget(self.output_label)

        self.output_button = QPushButton("Change")
        self.output_button.setObjectName("outputButton")
        self.output_button.clicked.connect(
            self.choose_output_folder
        )

        output_layout.addLayout(output_text_layout, 1)
        output_layout.addWidget(self.output_button)

        main_layout.addWidget(output_section)

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

            QFrame#outputSection {
                background-color: #181a1e;
                border: 1px solid #26292f;
                border-radius: 14px;
            }

            QLabel#outputTitle {
                font-size: 13px;
                font-weight: 600;
                color: #ffffff;
            }

            QLabel#outputPath {
                font-size: 12px;
                color: #7f8490;
            }

            QPushButton#outputButton {
                background-color: #25282e;
                border: 1px solid #343840;
                border-radius: 9px;
                padding: 8px 16px;
                color: #f3f3f3;
                font-weight: 600;
            }

            QPushButton#outputButton:hover {
                background-color: #2e3239;
            }

            QPushButton#outputButton:pressed {
                background-color: #202329;
            }

            QPushButton#outputButton:disabled {
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
        self.settings.setValue(
            "output_dir",
            self.output_dir,
        )

        self.output_label.setText(self.output_dir)

    def dragEnterEvent(self, event):
        if self.is_rendering:
            return

        if event.mimeData().hasUrls():
            self.drop_frame.setStyleSheet(
                """
                QFrame#dropFrame {
                    background-color: #1d2025;
                    border: 2px dashed #8a8f98;
                    border-radius: 18px;
                }
                """
            )
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_frame.setStyleSheet("")

    def dropEvent(self, event):
        self.drop_frame.setStyleSheet("")

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
            self.detail_label.setText("Supported: WAV, JPG, JPEG, PNG")
            return

        self.is_rendering = True
        self.output_button.setEnabled(False)

        self.status_icon.setText("●")
        self.main_label.setText(audio.stem)
        self.detail_label.setText(
            f"{audio.name}  +  {artwork.name}"
        )

        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.start_render(
            image_path=str(artwork),
            audio_path=str(audio),
            output_dir=self.output_dir,
        )

    def start_render(
        self,
        image_path: str,
        audio_path: str,
        output_dir: str,
    ):
        self.thread = QThread()

        self.worker = RenderWorker(
            image_path=image_path,
            audio_path=audio_path,
            output_dir=output_dir,
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

        self.output_button.setEnabled(True)
        self.is_rendering = False

    def render_failed(self, error: str):
        self.progress_bar.hide()

        self.status_icon.setText("!")
        self.main_label.setText("Render failed")
        self.detail_label.setText(error)

        self.output_button.setEnabled(True)
        self.is_rendering = False


app = QApplication(sys.argv)

window = BeatFrame()
window.show()

sys.exit(app.exec())