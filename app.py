import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QDoubleSpinBox,
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
        fade_duration: float,
        intro_path: Optional[str],
    ):
        super().__init__()

        self.image_path = image_path
        self.audio_path = audio_path
        self.output_dir = output_dir
        self.fade_duration = fade_duration
        self.intro_path = intro_path

    def run(self):
        try:
            output_path = render_video(
                image_path=self.image_path,
                audio_path=self.audio_path,
                output_dir=self.output_dir,
                fade_duration=self.fade_duration,
                intro_path=self.intro_path,
                progress_callback=self.report_progress,
            )

            self.finished.emit(str(output_path))

        except Exception as error:
            self.failed.emit(str(error))

    def report_progress(self, progress: float):
        self.progress.emit(int(progress * 100))


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent,
        settings: QSettings,
    ):
        super().__init__(parent)

        self.settings = settings

        self.setWindowTitle("BeatFrame Settings")
        self.setModal(True)
        self.resize(520, 320)

        self.build_ui()
        self.load_settings()
        self.apply_styles()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(18)

        title = QLabel("Settings")
        title.setObjectName("settingsTitle")

        subtitle = QLabel(
            "Configure BeatFrame once, then forget about it."
        )
        subtitle.setObjectName("settingsSubtitle")

        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(16)

        self.output_button = QPushButton()
        self.output_button.clicked.connect(
            self.choose_output_folder
        )

        self.intro_enabled = QCheckBox(
            "Use intro video"
        )
        self.intro_enabled.stateChanged.connect(
            self.update_intro_controls
        )

        intro_row = QWidget()
        intro_row_layout = QHBoxLayout(intro_row)
        intro_row_layout.setContentsMargins(0, 0, 0, 0)
        intro_row_layout.setSpacing(8)

        self.intro_button = QPushButton()
        self.intro_button.clicked.connect(
            self.choose_intro
        )

        self.clear_intro_button = QPushButton(
            "Remove"
        )
        self.clear_intro_button.clicked.connect(
            self.clear_intro
        )

        intro_row_layout.addWidget(
            self.intro_button,
            1,
        )
        intro_row_layout.addWidget(
            self.clear_intro_button
        )

        self.fade_spinbox = QDoubleSpinBox()
        self.fade_spinbox.setRange(0.0, 30.0)
        self.fade_spinbox.setDecimals(1)
        self.fade_spinbox.setSingleStep(0.5)
        self.fade_spinbox.setSuffix(" s")

        form.addRow(
            "Output folder",
            self.output_button,
        )

        form.addRow(
            "Intro",
            self.intro_enabled,
        )

        form.addRow(
            "Intro file",
            intro_row,
        )

        form.addRow(
            "Visual fade",
            self.fade_spinbox,
        )

        main_layout.addLayout(form)
        main_layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName(
            "secondaryButton"
        )
        cancel_button.clicked.connect(
            self.reject
        )

        save_button = QPushButton("Save")
        save_button.setObjectName(
            "primaryButton"
        )
        save_button.clicked.connect(
            self.save_settings
        )

        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        main_layout.addLayout(button_row)

    def load_settings(self):
        default_output = str(
            Path.home() / "Desktop"
        )

        self.output_dir = self.settings.value(
            "output_dir",
            default_output,
        )

        self.intro_path = self.settings.value(
            "intro_path",
            "",
        )

        intro_enabled_value = (
            self.settings.value(
                "intro_enabled",
                bool(self.intro_path),
                type=bool,
            )
        )

        fade_duration = self.settings.value(
            "fade_duration",
            6.5,
            type=float,
        )

        self.output_button.setText(
            self.output_dir
        )

        self.intro_enabled.setChecked(
            intro_enabled_value
        )

        self.fade_spinbox.setValue(
            fade_duration
        )

        self.update_intro_button_text()
        self.update_intro_controls()

    def choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose output folder",
            self.output_dir,
        )

        if not folder:
            return

        self.output_dir = folder
        self.output_button.setText(
            self.output_dir
        )

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
        self.update_intro_button_text()
        self.update_intro_controls()

    def clear_intro(self):
        self.intro_path = ""
        self.update_intro_button_text()
        self.update_intro_controls()

    def update_intro_button_text(self):
        if self.intro_path:
            self.intro_button.setText(
                Path(self.intro_path).name
            )
        else:
            self.intro_button.setText(
                "Choose MP4"
            )

    def update_intro_controls(self):
        enabled = (
            self.intro_enabled.isChecked()
        )

        self.intro_button.setEnabled(enabled)

        self.clear_intro_button.setEnabled(
            enabled and bool(self.intro_path)
        )

    def save_settings(self):
        self.settings.setValue(
            "output_dir",
            self.output_dir,
        )

        self.settings.setValue(
            "intro_enabled",
            self.intro_enabled.isChecked(),
        )

        if self.intro_path:
            self.settings.setValue(
                "intro_path",
                self.intro_path,
            )
        else:
            self.settings.remove(
                "intro_path"
            )

        self.settings.setValue(
            "fade_duration",
            self.fade_spinbox.value(),
        )

        self.accept()

    def apply_styles(self):
        self.setStyleSheet(
            """
            QDialog {
                background-color: #111214;
            }

            QWidget {
                color: #f3f3f3;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 14px;
            }

            QLabel#settingsTitle {
                font-size: 26px;
                font-weight: 700;
                color: #ffffff;
            }

            QLabel#settingsSubtitle {
                color: #8f939b;
                margin-bottom: 8px;
            }

            QPushButton,
            QDoubleSpinBox {
                background-color: #1b1d21;
                border: 1px solid #30343b;
                border-radius: 8px;
                padding: 8px 10px;
            }

            QPushButton:hover {
                background-color: #25282e;
            }

            QPushButton#primaryButton {
                background-color: #ffffff;
                color: #111214;
                font-weight: 700;
                padding: 8px 18px;
            }

            QPushButton#secondaryButton {
                background-color: transparent;
                color: #a2a6ae;
                padding: 8px 18px;
            }

            QCheckBox {
                spacing: 8px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            """
        )


class BeatFrame(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BeatFrame")
        self.resize(760, 540)
        self.setMinimumSize(680, 500)
        self.setAcceptDrops(True)

        self.settings = QSettings(
            "BeatFrame",
            "BeatFrame",
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
        main_layout.setContentsMargins(
            36,
            30,
            36,
            30,
        )
        main_layout.setSpacing(18)

        header_row = QHBoxLayout()

        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        title = QLabel("BeatFrame")
        title.setObjectName("title")

        subtitle = QLabel(
            "Artwork + audio → YouTube-ready video"
        )
        subtitle.setObjectName("subtitle")

        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName(
            "settingsButton"
        )
        self.settings_button.setFixedSize(
            42,
            42,
        )
        self.settings_button.clicked.connect(
            self.open_settings
        )

        header_row.addLayout(header_text)
        header_row.addStretch()
        header_row.addWidget(
            self.settings_button
        )

        main_layout.addLayout(header_row)

        self.drop_frame = QFrame()
        self.drop_frame.setObjectName(
            "dropFrame"
        )
        self.drop_frame.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        drop_layout = QVBoxLayout(
            self.drop_frame
        )
        drop_layout.setContentsMargins(
            40,
            40,
            40,
            40,
        )
        drop_layout.setSpacing(10)
        drop_layout.setAlignment(
            Qt.AlignCenter
        )

        self.status_icon = QLabel("＋")
        self.status_icon.setObjectName(
            "statusIcon"
        )
        self.status_icon.setAlignment(
            Qt.AlignCenter
        )

        self.main_label = QLabel(
            "Drop your artwork + beat here"
        )
        self.main_label.setObjectName(
            "mainLabel"
        )
        self.main_label.setAlignment(
            Qt.AlignCenter
        )

        self.detail_label = QLabel(
            "WAV + JPG / PNG"
        )
        self.detail_label.setObjectName(
            "detailLabel"
        )
        self.detail_label.setAlignment(
            Qt.AlignCenter
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName(
            "progressBar"
        )
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()

        drop_layout.addStretch()
        drop_layout.addWidget(
            self.status_icon
        )
        drop_layout.addWidget(
            self.main_label
        )
        drop_layout.addWidget(
            self.detail_label
        )
        drop_layout.addSpacing(14)
        drop_layout.addWidget(
            self.progress_bar
        )
        drop_layout.addStretch()

        main_layout.addWidget(
            self.drop_frame,
            1,
        )

        footer = QLabel(
            "BeatFrame handles the rest."
        )
        footer.setObjectName("footer")
        footer.setAlignment(
            Qt.AlignCenter
        )

        main_layout.addWidget(footer)

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

            QLabel#footer {
                color: #5f636c;
                font-size: 12px;
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

            QPushButton#settingsButton {
                background-color: #181a1e;
                border: 1px solid #2c2f35;
                border-radius: 12px;
                color: #d7d9de;
                font-size: 18px;
            }

            QPushButton#settingsButton:hover {
                background-color: #23262c;
            }

            QPushButton:disabled {
                color: #5f636c;
                background-color: #1d1f23;
                border-color: #25282e;
            }
            """
        )

    def open_settings(self):
        if self.is_rendering:
            return

        dialog = SettingsDialog(
            self,
            self.settings,
        )

        dialog.exec()

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

        audio_files = [
            file
            for file in files
            if file.suffix.lower()
            in AUDIO_EXTENSIONS
        ]

        image_files = [
            file
            for file in files
            if file.suffix.lower()
            in IMAGE_EXTENSIONS
        ]

        if (
            len(audio_files) != 1
            or len(image_files) != 1
        ):
            self.status_icon.setText("!")
            self.main_label.setText(
                "Drop exactly one WAV + one image"
            )
            self.detail_label.setText(
                "Supported: WAV, JPG, JPEG, PNG"
            )
            return

        audio = audio_files[0]
        artwork = image_files[0]

        default_output = str(
            Path.home() / "Desktop"
        )

        output_dir = self.settings.value(
            "output_dir",
            default_output,
        )

        fade_duration = self.settings.value(
            "fade_duration",
            6.5,
            type=float,
        )

        intro_enabled = self.settings.value(
            "intro_enabled",
            False,
            type=bool,
        )

        intro_path = self.settings.value(
            "intro_path",
            "",
        )

        if (
            intro_enabled
            and intro_path
        ):
            active_intro = intro_path
        else:
            active_intro = None

        self.is_rendering = True
        self.settings_button.setEnabled(False)

        self.status_icon.setText("●")
        self.main_label.setText(
            audio.stem
        )
        self.detail_label.setText(
            f"{audio.name}  +  {artwork.name}"
        )

        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.start_render(
            image_path=str(artwork),
            audio_path=str(audio),
            output_dir=output_dir,
            fade_duration=fade_duration,
            intro_path=active_intro,
        )

    def start_render(
        self,
        image_path: str,
        audio_path: str,
        output_dir: str,
        fade_duration: float,
        intro_path: Optional[str],
    ):
        self.thread = QThread()

        self.worker = RenderWorker(
            image_path=image_path,
            audio_path=audio_path,
            output_dir=output_dir,
            fade_duration=fade_duration,
            intro_path=intro_path,
        )

        self.worker.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.worker.run
        )

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

    def update_progress(
        self,
        percent: int,
    ):
        self.progress_bar.setValue(
            percent
        )

        self.detail_label.setText(
            f"Rendering... {percent}%"
        )

    def render_finished(
        self,
        output_path: str,
    ):
        self.progress_bar.setValue(100)

        self.status_icon.setText("✓")
        self.main_label.setText("Ready")
        self.detail_label.setText(
            Path(output_path).name
        )

        self.is_rendering = False
        self.settings_button.setEnabled(
            True
        )

    def render_failed(
        self,
        error: str,
    ):
        self.progress_bar.hide()

        self.status_icon.setText("!")
        self.main_label.setText(
            "Render failed"
        )
        self.detail_label.setText(
            error
        )

        self.is_rendering = False
        self.settings_button.setEnabled(
            True
        )


app = QApplication(sys.argv)

window = BeatFrame()
window.show()

sys.exit(app.exec())