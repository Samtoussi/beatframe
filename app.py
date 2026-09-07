import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QProgressBar,
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
        percent = int(progress * 100)
        self.progress.emit(percent)


class BeatFrame(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BeatFrame")
        self.resize(600, 400)
        self.setAcceptDrops(True)

        self.label = QLabel("Drop your artwork + beat here")
        self.label.setAlignment(Qt.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)

        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)

        self.thread = None
        self.worker = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
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
            self.label.setText("Drop one WAV + one JPG/PNG")
            return

        self.label.setText(
            f"✓ Audio: {audio.name}\n\n"
            f"✓ Artwork: {artwork.name}\n\n"
            "Rendering..."
        )

        self.progress_bar.setValue(0)
        self.progress_bar.show()

        output_dir = str(Path.home() / "Desktop")

        self.start_render(
            image_path=str(artwork),
            audio_path=str(audio),
            output_dir=output_dir,
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

        self.worker.progress.connect(self.update_progress)

        self.worker.finished.connect(self.render_finished)
        self.worker.failed.connect(self.render_failed)

        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def update_progress(self, percent: int):
        self.progress_bar.setValue(percent)

    def render_finished(self, output_path: str):
        self.progress_bar.setValue(100)

        self.label.setText(
            f"✓ Done\n\n"
            f"{Path(output_path).name}\n\n"
            "Saved to Desktop"
        )

    def render_failed(self, error: str):
        self.progress_bar.hide()

        self.label.setText(
            f"Render failed:\n\n{error}"
        )


app = QApplication(sys.argv)

window = BeatFrame()
window.show()

sys.exit(app.exec())