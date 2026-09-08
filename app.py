import sys
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QObject,
    QSettings,
    QSize,
    QTimer,
    QPointF,
)
from PySide6.QtGui import (
    QIcon,
    QPixmap,
    QPainter,
    QColor,
    QLinearGradient,
    QRadialGradient,
    QPen,
    QPainterPath,
    QFont,
)
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
    QGraphicsDropShadowEffect,
    QGraphicsBlurEffect,
)

import renderer as renderer_module

from renderer import (
    MediaReadError,
    RenderError,
    render_video,
)


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"


AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
}

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
}

KNOWN_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".wma",
}

KNOWN_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif",
}


def apply_windows_dark_title_bar(window):
    """Ask Windows to render BeatFrame's native title bar in dark mode."""
    if sys.platform != "win32":
        return

    try:
        import ctypes

        hwnd = int(window.winId())
        value = ctypes.c_int(1)

        # Windows 11 / newer Windows 10.
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        # Older Windows 10 builds used attribute 19.
        if result != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                19,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        # Cosmetic only. BeatFrame should still launch if Windows rejects it.
        pass


class GradientBackground(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()

        base = QLinearGradient(
            0,
            0,
            rect.width(),
            rect.height(),
        )

        # Dark foundation — larger dark center
        base.setColorAt(0.0, QColor("#120D28"))
        base.setColorAt(0.28, QColor("#090D1B"))
        base.setColorAt(0.72, QColor("#070C18"))
        base.setColorAt(1.0, QColor("#081127"))

        painter.fillRect(rect, base)


        # Purple / magenta glow — concentrated in top-left
        purple = QRadialGradient(
            rect.width() * -0.08,
            rect.height() * -0.04,
            rect.width() * 0.52,
        )

        purple.setColorAt(
            0.0,
            QColor(205, 35, 255, 205),
        )

        purple.setColorAt(
            0.18,
            QColor(157, 38, 235, 150),
        )

        purple.setColorAt(
            0.42,
            QColor(105, 35, 190, 70),
        )

        purple.setColorAt(
            0.72,
            QColor(72, 27, 135, 18),
        )

        purple.setColorAt(
            1.0,
            QColor(72, 27, 135, 0),
        )

        painter.fillRect(rect, purple)


        # Blue glow — concentrated in bottom-right
        blue = QRadialGradient(
            rect.width() * 1.08,
            rect.height() * 0.88,
            rect.width() * 0.55,
        )

        blue.setColorAt(
            0.0,
            QColor(38, 63, 255, 210),
        )

        blue.setColorAt(
            0.18,
            QColor(36, 61, 235, 155),
        )

        blue.setColorAt(
            0.42,
            QColor(29, 53, 190, 75),
        )

        blue.setColorAt(
            0.72,
            QColor(20, 39, 120, 18),
        )

        blue.setColorAt(
            1.0,
            QColor(20, 39, 120, 0),
        )

        painter.fillRect(rect, blue)


        # Magenta edge glow in lower-right
        magenta = QRadialGradient(
            rect.width() * 1.02,
            rect.height() * 1.08,
            rect.width() * 0.38,
        )

        magenta.setColorAt(
            0.0,
            QColor(205, 40, 225, 125),
        )

        magenta.setColorAt(
            0.45,
            QColor(170, 34, 210, 45),
        )

        magenta.setColorAt(
            1.0,
            QColor(170, 34, 210, 0),
        )

        painter.fillRect(rect, magenta)


class GlassFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_active = False
        self.setAttribute(Qt.WA_StyledBackground, False)

    def set_drag_active(self, active: bool):
        if self.drag_active == active:
            return

        self.drag_active = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = 26

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        fill = QLinearGradient(0, 0, self.width(), self.height())
        if self.drag_active:
            fill.setColorAt(0.0, QColor(67, 76, 154, 195))
            fill.setColorAt(0.48, QColor(27, 32, 78, 188))
            fill.setColorAt(1.0, QColor(35, 24, 72, 190))
        else:
            fill.setColorAt(0.0, QColor(31, 39, 79, 178))
            fill.setColorAt(0.48, QColor(12, 18, 42, 184))
            fill.setColorAt(1.0, QColor(30, 14, 43, 180))

        painter.fillPath(path, fill)

        top_glass = QLinearGradient(0, 0, 0, self.height() * 0.42)
        top_glass.setColorAt(0.0, QColor(255, 255, 255, 24))
        top_glass.setColorAt(0.55, QColor(255, 255, 255, 7))
        top_glass.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, top_glass)

        if self.drag_active:
            border = QColor(166, 130, 255, 205)
            border_width = 2.0
        else:
            border = QColor(161, 170, 255, 82)
            border_width = 1.2

        painter.setPen(QPen(border, border_width))
        painter.drawPath(path)

        highlight_rect = rect.adjusted(4, 4, -4, -4)
        highlight = QPainterPath()
        highlight.addRoundedRect(highlight_rect, radius - 4, radius - 4)
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
        painter.drawPath(highlight)


class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        QLabel.setText(self, text)

    def setText(self, text):
        self._full_text = str(text)
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        if not self._full_text:
            QLabel.setText(self, "")
            return

        available = max(40, self.width() - 16)
        text = self.fontMetrics().elidedText(
            self._full_text,
            Qt.ElideMiddle,
            available,
        )
        QLabel.setText(self, text)


class ToggleSwitch(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(28)

    def sizeHint(self):
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(54 + text_width, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        enabled = self.isEnabled()
        checked = self.isChecked()

        track_x = 0
        track_y = 3
        track_w = 42
        track_h = 22
        knob_size = 18

        if checked:
            gradient = QLinearGradient(track_x, 0, track_x + track_w, 0)
            gradient.setColorAt(0.0, QColor("#587CFF"))
            gradient.setColorAt(1.0, QColor("#E052CF"))
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor(255, 255, 255, 75), 1))
        else:
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.setPen(QPen(QColor(255, 255, 255, 42), 1))

        if not enabled:
            painter.setOpacity(0.45)

        painter.drawRoundedRect(
            track_x,
            track_y,
            track_w,
            track_h,
            track_h / 2,
            track_h / 2,
        )

        knob_x = 21 if checked else 3
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#F5F3FF"))
        painter.drawEllipse(
            knob_x,
            track_y + 2,
            knob_size,
            knob_size,
        )

        painter.setOpacity(1.0 if enabled else 0.45)
        painter.setPen(QColor("#F2F4FF"))
        painter.drawText(
            54,
            0,
            max(0, self.width() - 54),
            self.height(),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text(),
        )

class StatusGlow(QWidget):
    """Soft blurred glow behind the crisp status circle."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(112, 112)
        self.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(11)
        self.setGraphicsEffect(blur)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        glow_rect = self.rect().adjusted(
            18,
            18,
            -18,
            -18,
        )

        # Soft violet base keeps the blue and magenta blended.
        painter.setPen(
            QPen(
                QColor(132, 86, 255, 105),
                3.4,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.drawEllipse(glow_rect)

        # Electric blue, weighted toward the lower-left.
        painter.setPen(
            QPen(
                QColor(50, 100, 255, 145),
                4.0,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.drawArc(
            glow_rect,
            115 * 16,
            205 * 16,
        )

        # Magenta, weighted toward the upper-right.
        painter.setPen(
            QPen(
                QColor(232, 72, 215, 135),
                4.0,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.drawArc(
            glow_rect,
            -65 * 16,
            190 * 16,
        )


class StatusIcon(QWidget):
    def __init__(self, text="＋", parent=None):
        super().__init__(parent)

        self._text = text
        self._mode = "idle"
        self._rotation = 0.0
        self._success_progress = 0.0
        self._success_rotation = 0.0

        self.setFixedSize(84, 84)

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(16)
        self.animation_timer.timeout.connect(
            self._advance_animation
        )

    def setText(self, text):
        self._text = text

        if self._mode not in {
            "loading",
            "success",
        }:
            self._mode = "idle"

        self.update()

    def setLoading(self, loading):
        if loading:
            self._text = ""
            self._mode = "loading"
            self._rotation = 0.0
            self.animation_timer.start()
        else:
            if self._mode == "loading":
                self._mode = "idle"

            if self._mode != "success":
                self.animation_timer.stop()

        self.update()

    def playSuccess(self):
        # Continue from the loader's current angle so the transition
        # feels like the same ring turning into the completed state.
        self._success_rotation = self._rotation
        self._success_progress = 0.0
        self._text = ""
        self._mode = "success"
        self.animation_timer.start()
        self.update()

    def _advance_animation(self):
        if self._mode == "loading":
            self._rotation = (
                self._rotation + 4.0
            ) % 360.0

        elif self._mode == "success":
            # ~0.55 second success transition at ~60 fps.
            self._success_progress += 0.010

            if self._success_progress >= 1.0:
                self._success_progress = 1.0
                self._mode = "success_done"
                self.animation_timer.stop()

        else:
            self.animation_timer.stop()

        self.update()

    @staticmethod
    def _ease_out_cubic(value):
        value = max(0.0, min(1.0, value))
        return 1.0 - pow(1.0 - value, 3)

    def _draw_check_segment(
        self,
        painter,
        start,
        end,
        progress,
    ):
        progress = max(0.0, min(1.0, progress))

        current = QPointF(
            start.x()
            + (end.x() - start.x()) * progress,
            start.y()
            + (end.y() - start.y()) * progress,
        )

        painter.drawLine(
            start,
            current,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        center = self.rect().center()
        circle_radius = 36

        # Dark glass circle
        circle_fill = QRadialGradient(
            center,
            circle_radius,
        )

        circle_fill.setColorAt(
            0.0,
            QColor(22, 23, 45, 252),
        )

        circle_fill.setColorAt(
            1.0,
            QColor(11, 13, 29, 252),
        )

        painter.setBrush(circle_fill)

        painter.setPen(
            QPen(
                QColor(145, 150, 190, 105),
                1.0,
            )
        )

        painter.drawEllipse(
            center,
            circle_radius,
            circle_radius,
        )

        loader_rect = self.rect().adjusted(
            7,
            7,
            -7,
            -7,
        )

        if self._mode == "loading":
            loader_pen = QPen(
                QColor("#BFA8FF"),
                3.0,
                Qt.SolidLine,
                Qt.RoundCap,
            )

            painter.setPen(loader_pen)
            painter.setBrush(Qt.NoBrush)

            painter.drawArc(
                loader_rect,
                int(self._rotation * 16),
                110 * 16,
            )

            return

        if self._mode in {
            "success",
            "success_done",
        }:
            progress = (
                self._success_progress
                if self._mode == "success"
                else 1.0
            )

            # Stage 1: the spinning arc closes into a full ring.
            ring_progress = self._ease_out_cubic(
                min(progress / 0.46, 1.0)
            )
            ring_span = (
                110.0
                + (250.0 * ring_progress)
            )

            # As the check appears, the completed ring gently fades
            # into the normal circle border.
            ring_fade = 1.0

            if progress > 0.58:
                ring_fade = max(
                    0.0,
                    1.0
                    - (
                        (progress - 0.58)
                        / 0.42
                    ),
                )

            ring_pen = QPen(
                QColor(
                    191,
                    168,
                    255,
                    int(235 * ring_fade),
                ),
                3.0,
                Qt.SolidLine,
                Qt.RoundCap,
            )

            painter.setPen(ring_pen)
            painter.setBrush(Qt.NoBrush)

            painter.drawArc(
                loader_rect,
                int(
                    self._success_rotation
                    * 16
                ),
                int(ring_span * 16),
            )

            # Stage 2: draw the check mark in two strokes.
            check_progress = max(
                0.0,
                min(
                    1.0,
                    (progress - 0.36)
                    / 0.64,
                ),
            )
            check_progress = self._ease_out_cubic(
                check_progress
            )

            check_pen = QPen(
                QColor("#D9C2FF"),
                3.2,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
            painter.setPen(check_pen)

            p1 = QPointF(
                center.x() - 13,
                center.y() + 1,
            )
            p2 = QPointF(
                center.x() - 4,
                center.y() + 10,
            )
            p3 = QPointF(
                center.x() + 15,
                center.y() - 11,
            )

            first_share = 0.34

            if check_progress <= first_share:
                self._draw_check_segment(
                    painter,
                    p1,
                    p2,
                    check_progress
                    / first_share,
                )
            else:
                painter.drawLine(
                    p1,
                    p2,
                )

                self._draw_check_segment(
                    painter,
                    p2,
                    p3,
                    (
                        check_progress
                        - first_share
                    )
                    / (
                        1.0
                        - first_share
                    ),
                )

            return

        # Draw + manually so it is mathematically centered.
        if self._text in ("＋", "+"):
            symbol_pen = QPen(
                QColor("#D9C2FF"),
                3.0,
                Qt.SolidLine,
                Qt.RoundCap,
            )

            painter.setPen(symbol_pen)
            symbol_size = 13

            painter.drawLine(
                center.x() - symbol_size,
                center.y(),
                center.x() + symbol_size,
                center.y(),
            )

            painter.drawLine(
                center.x(),
                center.y() - symbol_size,
                center.x(),
                center.y() + symbol_size,
            )

        else:
            painter.setPen(
                QColor("#E798E4")
            )

            font = painter.font()
            font.setFamily("Segoe UI")
            font.setPointSize(24)
            font.setWeight(QFont.Normal)

            painter.setFont(font)

            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                self._text,
            )


class RenderCancelled(Exception):
    pass


class RenderWorker(QObject):
    finished = Signal(str)
    failed = Signal(str, str)
    cancelled = Signal()
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

        self._cancel_requested = False
        self._current_process = None
        self._existing_outputs = set()

    def cancel(self):
        self._cancel_requested = True

        process = self._current_process

        if (
            process is not None
            and process.poll() is None
        ):
            try:
                process.terminate()
            except Exception:
                pass

    def _cleanup_cancelled_outputs(self):
        output_folder = Path(
            self.output_dir
        )

        stem = Path(
            self.audio_path
        ).stem

        try:
            current_outputs = set(
                output_folder.glob(
                    f"{stem}*.mp4"
                )
            )

            new_outputs = (
                current_outputs
                - self._existing_outputs
            )

            for path in new_outputs:
                try:
                    path.unlink()
                except OSError:
                    pass

        except OSError:
            pass

    def _run_ffmpeg_with_progress(
        self,
        command,
        duration,
        progress_callback=None,
    ):
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        self._current_process = process

        try:
            if process.stdout is None:
                raise RenderError(
                    "FFmpeg progress stream unavailable"
                )

            for line in process.stdout:
                if self._cancel_requested:
                    try:
                        process.terminate()
                    except Exception:
                        pass

                    raise RenderCancelled()

                line = line.strip()

                if line.startswith(
                    "out_time_ms="
                ):
                    try:
                        out_time_ms = int(
                            line.split(
                                "=",
                                1,
                            )[1]
                        )
                    except ValueError:
                        continue

                    if (
                        duration > 0
                        and progress_callback
                        is not None
                    ):
                        current_seconds = (
                            out_time_ms
                            / 1_000_000
                        )

                        progress_callback(
                            min(
                                current_seconds
                                / duration,
                                1.0,
                            )
                        )

            return_code = process.wait()

            if self._cancel_requested:
                raise RenderCancelled()

            if return_code != 0:
                raise RenderError(
                    "FFmpeg couldn't complete the render"
                )

            if progress_callback is not None:
                progress_callback(1.0)

        finally:
            self._current_process = None

    def run(self):
        original_runner = (
            renderer_module
            .run_ffmpeg_with_progress
        )

        output_folder = Path(
            self.output_dir
        )

        stem = Path(
            self.audio_path
        ).stem

        try:
            self._existing_outputs = set(
                output_folder.glob(
                    f"{stem}*.mp4"
                )
            )
        except OSError:
            self._existing_outputs = set()

        # renderer.py resolves this helper at runtime, so replacing it
        # for this one worker gives BeatFrame cancellable FFmpeg jobs
        # without changing the renderer API.
        renderer_module.run_ffmpeg_with_progress = (
            self._run_ffmpeg_with_progress
        )

        try:
            if self._cancel_requested:
                raise RenderCancelled()

            output_path = render_video(
                image_path=self.image_path,
                audio_path=self.audio_path,
                output_dir=self.output_dir,
                fade_duration=self.fade_duration,
                intro_path=self.intro_path,
                progress_callback=self.report_progress,
            )

            if self._cancel_requested:
                raise RenderCancelled()

            self.finished.emit(
                str(output_path)
            )

        except RenderCancelled:
            self._cleanup_cancelled_outputs()
            self.cancelled.emit()

        except MediaReadError as error:
            if error.media_type == "audio":
                self.failed.emit(
                    "invalid_audio",
                    "Audio file couldn't be read",
                )
            elif error.media_type == "image":
                self.failed.emit(
                    "invalid_image",
                    "Image file couldn't be read",
                )
            elif error.media_type == "intro":
                self.failed.emit(
                    "invalid_intro",
                    "Intro video couldn't be read",
                )
            else:
                self.failed.emit(
                    "invalid_media",
                    "Media file couldn't be read",
                )

        except FileNotFoundError as error:
            message = str(error)

            if message.startswith(
                "Intro file not found:"
            ):
                self.failed.emit(
                    "missing_intro",
                    "Intro file not found",
                )
            elif message.startswith(
                "Audio file not found:"
            ):
                self.failed.emit(
                    "missing_audio",
                    "Audio file not found",
                )
            elif message.startswith(
                "Image file not found:"
            ):
                self.failed.emit(
                    "missing_image",
                    "Image file not found",
                )
            else:
                self.failed.emit(
                    "missing_file",
                    "A required file could not be found",
                )

        except RenderError:
            if self._cancel_requested:
                self._cleanup_cancelled_outputs()
                self.cancelled.emit()
            else:
                self.failed.emit(
                    "render_error",
                    "FFmpeg couldn't complete the render",
                )

        except Exception:
            if self._cancel_requested:
                self._cleanup_cancelled_outputs()
                self.cancelled.emit()
            else:
                self.failed.emit(
                    "unknown_error",
                    "Something unexpected went wrong",
                )

        finally:
            renderer_module.run_ffmpeg_with_progress = (
                original_runner
            )

    def report_progress(
        self,
        progress: float,
    ):
        if self._cancel_requested:
            raise RenderCancelled()

        self.progress.emit(
            int(progress * 100)
        )


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
        self.setFixedSize(620, 510)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
        )
        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        self.build_ui()
        self.load_settings()
        self.apply_styles()

    def showEvent(self, event):
        super().showEvent(event)

        parent = self.parentWidget()
        if parent is None:
            return

        parent_center = parent.frameGeometry().center()
        frame = self.frameGeometry()
        frame.moveCenter(parent_center)
        self.move(frame.topLeft())

    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        self.card = QFrame()
        self.card.setObjectName("settingsCard")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(45)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(105, 36, 130, 90))
        self.card.setGraphicsEffect(shadow)

        outer_layout.addWidget(self.card)

        main_layout = QVBoxLayout(self.card)
        main_layout.setContentsMargins(
            32,
            28,
            32,
            28,
        )
        main_layout.setSpacing(15)

        title_row = QHBoxLayout()

        title = QLabel("Settings")
        title.setObjectName("settingsTitle")

        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setFixedSize(34, 34)
        close_button.clicked.connect(self.reject)

        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_button)

        subtitle = QLabel(
            "Configure BeatFrame once, then forget about it."
        )
        subtitle.setObjectName("settingsSubtitle")

        main_layout.addLayout(title_row)
        main_layout.addWidget(subtitle)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        main_layout.addWidget(divider)

        form = QFormLayout()
        form.setHorizontalSpacing(22)
        form.setVerticalSpacing(15)
        form.setLabelAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )

        self.output_button = QPushButton()
        self.output_button.setObjectName("fieldButton")
        self.output_button.clicked.connect(
            self.choose_output_folder
        )

        self.intro_enabled = ToggleSwitch(
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
        self.intro_button.setObjectName("fieldButton")
        self.intro_button.clicked.connect(
            self.choose_intro
        )

        self.clear_intro_button = QPushButton(
            "Remove"
        )
        self.clear_intro_button.setObjectName(
            "secondarySmall"
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
        self.fade_spinbox.setObjectName("fadeSpinbox")
        self.fade_spinbox.setRange(0.0, 30.0)
        self.fade_spinbox.setDecimals(1)
        self.fade_spinbox.setSingleStep(0.1)
        self.fade_spinbox.setSuffix(" s")
        self.fade_spinbox.setAlignment(Qt.AlignCenter)

        self.auto_render_checkbox = ToggleSwitch(
            "Render automatically after drop"
        )

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
        form.addRow(
            "Workflow",
            self.auto_render_checkbox,
        )

        main_layout.addLayout(form)
        main_layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName(
            "secondaryButton"
        )
        cancel_button.clicked.connect(self.reject)

        save_button = QPushButton("Save")
        save_button.setObjectName("primaryButton")
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

        intro_enabled_value = self.settings.value(
            "intro_enabled",
            bool(self.intro_path),
            type=bool,
        )

        fade_duration = self.settings.value(
            "fade_duration",
            6.5,
            type=float,
        )

        auto_render = self.settings.value(
            "auto_render",
            True,
            type=bool,
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
        self.auto_render_checkbox.setChecked(
            auto_render
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
        enabled = self.intro_enabled.isChecked()

        self.intro_button.setEnabled(enabled)
        self.clear_intro_button.setEnabled(
            enabled
            and bool(self.intro_path)
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
            self.settings.remove("intro_path")

        self.settings.setValue(
            "fade_duration",
            self.fade_spinbox.value(),
        )
        self.settings.setValue(
            "auto_render",
            self.auto_render_checkbox.isChecked(),
        )

        self.accept()

    def apply_styles(self):
        self.setStyleSheet(
            """
            QDialog {
                background: transparent;
            }

            QFrame#settingsCard {
                background-color: rgba(8, 12, 29, 246);
                border: 1px solid rgba(167, 157, 255, 65);
                border-radius: 24px;
            }

            QWidget {
                color: #F2F4FF;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 14px;
            }

            QLabel#settingsTitle {
                font-size: 26px;
                font-weight: 700;
                color: #FFFFFF;
            }

            QLabel#settingsSubtitle {
                color: #AEB8D8;
                margin-bottom: 2px;
            }

            QFrame#divider {
                background-color: rgba(255, 255, 255, 22);
                border: none;
            }

            QPushButton#fieldButton,
            QDoubleSpinBox#fadeSpinbox {
                background-color: rgba(255, 255, 255, 9);
                border: 1px solid rgba(171, 184, 255, 60);
                border-radius: 11px;
                padding: 9px 12px;
                min-height: 20px;
                color: #F4F5FF;
            }

            QPushButton#fieldButton:hover,
            QDoubleSpinBox#fadeSpinbox:hover {
                background-color: rgba(255, 255, 255, 15);
                border-color: rgba(184, 159, 255, 115);
            }

            QPushButton#secondarySmall {
                background-color: rgba(255, 255, 255, 8);
                border: 1px solid rgba(171, 184, 255, 55);
                border-radius: 10px;
                padding: 9px 13px;
            }

            QPushButton#secondarySmall:hover {
                background-color: rgba(255, 255, 255, 14);
            }

            QPushButton#primaryButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #587CFF,
                    stop: 1 #E052CF
                );
                border: 1px solid rgba(255, 255, 255, 70);
                border-radius: 11px;
                padding: 9px 21px;
                color: #FFFFFF;
                font-weight: 700;
                min-width: 76px;
            }

            QPushButton#primaryButton:hover {
                border-color: rgba(255, 255, 255, 130);
            }

            QPushButton#secondaryButton {
                background-color: rgba(255, 255, 255, 5);
                border: 1px solid rgba(171, 184, 255, 48);
                border-radius: 11px;
                padding: 9px 19px;
                color: #C6CEE9;
                min-width: 76px;
            }

            QPushButton#secondaryButton:hover {
                background-color: rgba(255, 255, 255, 11);
            }

            QPushButton#closeButton {
                background-color: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 17px;
                color: #AEB8D8;
                font-size: 22px;
                padding: 0px;
            }

            QPushButton#closeButton:hover {
                background-color: rgba(255, 255, 255, 12);
                color: #FFFFFF;
            }

            QPushButton:disabled {
                color: #626B87;
                background-color: rgba(255, 255, 255, 5);
                border-color: rgba(255, 255, 255, 14);
            }

            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {
                width: 22px;
                border: none;
                background-color: rgba(255, 255, 255, 7);
            }

            QDoubleSpinBox::up-button:hover,
            QDoubleSpinBox::down-button:hover {
                background-color: rgba(255, 255, 255, 14);
            }
            """
        )


class BeatFrame(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BeatFrame")
        self.resize(840, 620)
        self.setMinimumSize(720, 540)
        self.setAcceptDrops(True)

        if LOGO_PATH.exists():
            self.setWindowIcon(
                QIcon(str(LOGO_PATH))
            )

        self.settings = QSettings(
            "BeatFrame",
            "BeatFrame",
        )

        self.thread = None
        self.worker = None
        self.is_rendering = False

        self.pending_audio = None
        self.pending_artwork = None

        self.build_ui()
        self.apply_styles()

    def build_ui(self):
        root = GradientBackground()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(
            44,
            34,
            44,
            26,
        )
        main_layout.setSpacing(20)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        header_row.setContentsMargins(
            -30,
            0,
            0,
            0,
)


        if LOGO_PATH.exists():
            logo_label = QLabel()
            logo_label.setObjectName("logo")
            logo_pixmap = QPixmap(
                str(LOGO_PATH)
            )
            logo_label.setPixmap(
                logo_pixmap.scaled(
                    90,
                    90,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            logo_label.setFixedSize(84, 84)
            logo_label.setAlignment(Qt.AlignCenter)
            header_row.addWidget(logo_label)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("BeatFrame")
        title.setObjectName("title")

        subtitle = QLabel(
            "Artwork + audio → YouTube-ready video"
        )
        subtitle.setObjectName("subtitle")

        header_text.addStretch()
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_text.addStretch()

        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName(
            "settingsButton"
        )
        self.settings_button.setFixedSize(48, 48)
        self.settings_button.clicked.connect(
            self.open_settings
        )

        header_row.addLayout(header_text)
        header_row.addStretch()
        header_row.addWidget(
            self.settings_button,
            alignment=Qt.AlignVCenter,
        )

        header_row.addSpacing(10)

        main_layout.addLayout(header_row)

        self.drop_frame = GlassFrame()
        self.drop_frame.setObjectName(
            "dropFrame"
        )
        self.drop_frame.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        shadow = QGraphicsDropShadowEffect(
            self.drop_frame
        )
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 10)
        shadow.setColor(
            QColor(64, 48, 155, 78)
        )
        self.drop_frame.setGraphicsEffect(
            shadow
        )

        drop_layout = QVBoxLayout(
            self.drop_frame
        )
        drop_layout.setContentsMargins(
            46,
            42,
            46,
            42,
        )
        drop_layout.setSpacing(10)
        drop_layout.setAlignment(
            Qt.AlignCenter
        )

        self.status_container = QWidget()
        self.status_container.setFixedSize(
            112,
            112,
        )

        self.status_glow = StatusGlow(
            self.status_container
        )
        self.status_glow.move(0, 0)

        self.status_icon = StatusIcon(
            "＋",
            self.status_container,
        )
        self.status_icon.move(
            (112 - self.status_icon.width()) // 2,
            (112 - self.status_icon.height()) // 2,
        )

        self.main_label = ElidedLabel(
            "Drop your artwork + beat here"
        )
        self.main_label.setObjectName(
            "mainLabel"
        )
        self.main_label.setAlignment(
            Qt.AlignCenter
        )
        self.main_label.setMinimumWidth(420)

        self.detail_label = ElidedLabel(
            "WAV / MP3 + JPG / PNG"
        )
        self.detail_label.setObjectName(
            "detailLabel"
        )
        self.detail_label.setAlignment(
            Qt.AlignCenter
        )
        self.detail_label.setMinimumWidth(420)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName(
            "progressBar"
        )
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(520)
        self.progress_bar.hide()

        self.cancel_button = QPushButton(
            "Cancel"
        )
        self.cancel_button.setObjectName(
            "cancelButton"
        )
        self.cancel_button.clicked.connect(
            self.cancel_render
        )
        self.cancel_button.hide()

        self.render_button = QPushButton(
            "Render"
        )
        self.render_button.setObjectName(
            "renderButton"
        )
        self.render_button.clicked.connect(
            self.render_pending_files
        )
        self.render_button.hide()

        self.error_action_button = QPushButton()
        self.error_action_button.setObjectName(
            "renderButton"
        )
        self.error_action_button.hide()

        drop_layout.addStretch()
        drop_layout.addWidget(
            self.status_container,
            alignment=Qt.AlignCenter,
        )
        drop_layout.addSpacing(8)
        drop_layout.addWidget(
            self.main_label
        )
        drop_layout.addWidget(
            self.detail_label
        )
        drop_layout.addSpacing(16)
        drop_layout.addWidget(
            self.progress_bar,
            alignment=Qt.AlignCenter,
        )
        drop_layout.addWidget(
            self.cancel_button,
            alignment=Qt.AlignCenter,
        )
        drop_layout.addWidget(
            self.render_button,
            alignment=Qt.AlignCenter,
        )
        drop_layout.addWidget(
            self.error_action_button,
            alignment=Qt.AlignCenter,
        )
        drop_layout.addStretch()

        main_layout.addWidget(
            self.drop_frame,
            1,
        )

        footer_row = QHBoxLayout()

        footer = QLabel(
            "BeatFrame handles the rest."
        )
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignCenter)

        version = QLabel("v1.0")
        version.setObjectName("version")
        version.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )

        # Equal space on both sides keeps footer truly centered
        side_width = 70

        left_spacer = QWidget()
        left_spacer.setFixedWidth(side_width)

        version.setFixedWidth(side_width)

        footer_row.addWidget(left_spacer)
        footer_row.addWidget(footer, 1)
        footer_row.addWidget(version)

        main_layout.addLayout(footer_row)

    def apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #080A16;
            }

            QWidget {
                color: #F3F5FF;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 14px;
            }

            QLabel#title {
                font-size: 30px;
                font-weight: 700;
                color: #FFFFFF;
            }

            QLabel#subtitle {
                font-size: 13px;
                color: #AAB5D6;
            }


            QLabel#mainLabel {
                font-size: 21px;
                font-weight: 650;
                color: #FFFFFF;
                padding-top: 4px;
            }

            QLabel#detailLabel {
                font-size: 13px;
                color: #A7B2D2;
            }

            QLabel#footer,
            QLabel#version {
                color: #6F7B9D;
                font-size: 11px;
            }

            QProgressBar#progressBar {
                min-height: 11px;
                max-height: 11px;
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 6px;
                background-color: rgba(255, 255, 255, 9);
            }

            QProgressBar#progressBar::chunk {
                border-radius: 5px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4E8DFF,
                    stop: 0.48 #7474FF,
                    stop: 1 #E052CF
                );
            }

            QPushButton#settingsButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(37, 46, 88, 205),
                    stop: 1 rgba(33, 21, 61, 210)
                );
                border: 1px solid rgba(167, 159, 255, 88);
                border-radius: 15px;
                color: #E8E9FF;
                font-family: "Segoe UI Symbol", "Segoe UI", sans-serif;
                font-size: 22px;
                padding: 0px;
            }

            QPushButton#settingsButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(48, 70, 132, 220),
                    stop: 1 rgba(91, 31, 94, 225)
                );
                border-color: rgba(197, 174, 255, 145);
            }

            QPushButton#renderButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #587CFF,
                    stop: 1 #E052CF
                );
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 72);
                border-radius: 11px;
                padding: 10px 30px;
                font-weight: 700;
                min-width: 110px;
            }

            QPushButton#renderButton:hover {
                border-color: rgba(255, 255, 255, 135);
            }

            QPushButton#cancelButton {
                background-color: rgba(255, 255, 255, 5);
                color: #B9C1DE;
                border: 1px solid rgba(171, 184, 255, 42);
                border-radius: 10px;
                padding: 7px 20px;
                min-width: 84px;
            }

            QPushButton#cancelButton:hover {
                background-color: rgba(224, 82, 207, 18);
                color: #F2D6F0;
                border-color: rgba(224, 82, 207, 90);
            }

            QPushButton:disabled {
                color: #626B87;
                background-color: rgba(255, 255, 255, 7);
                border-color: rgba(255, 255, 255, 15);
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
            self.drop_frame.set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_frame.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_frame.set_drag_active(False)

        if self.is_rendering:
            return

        files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]

        self.clear_error_action()

        unsupported_audio = [
            file
            for file in files
            if (
                file.suffix.lower()
                in KNOWN_AUDIO_EXTENSIONS
                and file.suffix.lower()
                not in AUDIO_EXTENSIONS
            )
        ]

        unsupported_images = [
            file
            for file in files
            if (
                file.suffix.lower()
                in KNOWN_IMAGE_EXTENSIONS
                and file.suffix.lower()
                not in IMAGE_EXTENSIONS
            )
        ]

        if unsupported_audio:
            extension = (
                unsupported_audio[0]
                .suffix
                .upper()
                .lstrip(".")
            )
            self.show_input_error(
                f"{extension} audio isn't supported",
                "Use WAV or MP3.",
            )
            return

        if unsupported_images:
            extension = (
                unsupported_images[0]
                .suffix
                .upper()
                .lstrip(".")
            )
            self.show_input_error(
                f"{extension} images aren't supported",
                "Use JPG, JPEG or PNG.",
            )
            return

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
            self.show_input_error(
                "Drop exactly one audio file + one image",
                "Audio: WAV or MP3  •  Image: JPG, JPEG or PNG",
            )
            return

        self.pending_audio = audio_files[0]
        self.pending_artwork = image_files[0]

        auto_render = self.settings.value(
            "auto_render",
            True,
            type=bool,
        )

        if auto_render:
            self.render_pending_files()
        else:
            self.show_files_ready()

    def show_input_error(
        self,
        title: str,
        detail: str,
    ):
        self.pending_audio = None
        self.pending_artwork = None

        self.progress_bar.hide()
        self.cancel_button.hide()
        self.render_button.hide()
        self.clear_error_action()

        self.status_icon.setText("!")
        self.main_label.setText(title)
        self.detail_label.setText(detail)

    def show_files_ready(self):
        if (
            self.pending_audio is None
            or self.pending_artwork is None
        ):
            return

        self.clear_error_action()
        self.progress_bar.hide()
        self.cancel_button.hide()

        self.status_icon.setText("✓")
        self.main_label.setText("Files ready")
        self.detail_label.setText(
            f"{self.pending_audio.name}"
            f"  +  "
            f"{self.pending_artwork.name}"
        )

        self.render_button.show()

    def render_pending_files(self):
        if (
            self.pending_audio is None
            or self.pending_artwork is None
            or self.is_rendering
        ):
            return

        audio = self.pending_audio
        artwork = self.pending_artwork

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

        if intro_enabled and intro_path:
            active_intro = intro_path
        else:
            active_intro = None

        self.is_rendering = True

        self.settings_button.setEnabled(False)
        self.render_button.hide()
        self.clear_error_action()

        self.status_icon.setLoading(True)
        self.main_label.setText(audio.stem)
        self.detail_label.setText(
            f"{audio.name}"
            f"  +  "
            f"{artwork.name}"
        )

        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.cancel_button.setText(
            "Cancel"
        )
        self.cancel_button.setEnabled(
            True
        )
        self.cancel_button.show()

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
        self.worker.cancelled.connect(
            self.render_cancelled
        )
        self.worker.finished.connect(
            self.thread.quit
        )
        self.worker.failed.connect(
            self.thread.quit
        )
        self.worker.cancelled.connect(
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
        self.progress_bar.setValue(percent)
        self.detail_label.setText(
            f"Rendering... {percent}%"
        )

    def render_finished(

        self,
        output_path: str,
    ):
        self.progress_bar.setValue(100)
        self.cancel_button.hide()

        self.status_icon.playSuccess()
        self.main_label.setText("Ready")
        self.detail_label.setText(
            Path(output_path).name
        )

        self.pending_audio = None
        self.pending_artwork = None
        self.is_rendering = False

        self.settings_button.setEnabled(True)

        QTimer.singleShot(
            3200,
            self.reset_idle_state,
        )

    def reset_idle_state(self):
        if (
            self.is_rendering
            or self.pending_audio is not None
            or self.pending_artwork is not None
        ):
            return

        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.cancel_button.hide()
        self.cancel_button.setText(
            "Cancel"
        )
        self.cancel_button.setEnabled(
            True
        )
        self.render_button.hide()
        self.clear_error_action()

        self.status_icon.setText("＋")
        self.main_label.setText(
            "Drop your artwork + beat here"
        )
        self.detail_label.setText(
            "WAV / MP3 + JPG / PNG"
        )

    def cancel_render(self):
        if (
            not self.is_rendering
            or self.worker is None
        ):
            return

        self.cancel_button.setText(
            "Cancelling..."
        )
        self.cancel_button.setEnabled(
            False
        )
        self.worker.cancel()

    def render_cancelled(self):
        self.status_icon.setLoading(False)
        self.status_icon.setText("×")

        self.progress_bar.hide()
        self.progress_bar.setValue(0)

        self.cancel_button.hide()
        self.cancel_button.setText(
            "Cancel"
        )
        self.cancel_button.setEnabled(
            True
        )

        self.pending_audio = None
        self.pending_artwork = None
        self.is_rendering = False

        self.settings_button.setEnabled(
            True
        )

        self.main_label.setText(
            "Cancelled"
        )
        self.detail_label.setText(
            "Drop another artwork + beat when you're ready."
        )

        QTimer.singleShot(
            1400,
            self.reset_idle_state,
        )

    def render_failed(
        self,
        error_type: str,
        message: str,
    ):
        self.status_icon.setLoading(False)
        self.progress_bar.setVisible(False)

        self.clear_error_action()

        if error_type == "missing_intro":
            self.status_icon.setText("!")
            self.main_label.setText(
                "Intro file not found"
            )
            self.detail_label.setText(
                "Choose a new intro in Settings "
                "or turn off Use intro video."
            )
            self.set_error_action(
                "Open Settings",
                self.open_settings,
            )

        elif error_type == "invalid_intro":
            self.status_icon.setText("!")
            self.main_label.setText(
                "Intro file couldn't be read"
            )
            self.detail_label.setText(
                "Choose another intro in Settings."
            )
            self.set_error_action(
                "Open Settings",
                self.open_settings,
            )

        elif error_type in (
            "missing_audio",
            "invalid_audio",
        ):
            self.status_icon.setText("!")
            self.main_label.setText(
                "Audio file couldn't be read"
            )
            self.detail_label.setText(
                "The audio file may be damaged, "
                "invalid, or unavailable. "
                "Drop another file."
            )
            self.pending_audio = None
            self.pending_artwork = None

        elif error_type in (
            "missing_image",
            "invalid_image",
        ):
            self.status_icon.setText("!")
            self.main_label.setText(
                "Image file couldn't be read"
            )
            self.detail_label.setText(
                "The image may be damaged, "
                "invalid, or unavailable. "
                "Drop another file."
            )
            self.pending_audio = None
            self.pending_artwork = None

        elif error_type == "render_error":
            self.status_icon.setText("!")
            self.main_label.setText(
                "Render failed"
            )
            self.detail_label.setText(
                "BeatFrame couldn't complete the render."
            )

            if (
                self.pending_audio
                and self.pending_artwork
            ):
                self.render_button.setVisible(True)

        else:
            self.status_icon.setText("!")
            self.main_label.setText(
                "Something went wrong"
            )
            self.detail_label.setText(
                message
            )

    def set_error_action(
        self,
        text: str,
        callback,
    ):
        self.clear_error_action()

        self.error_action_button.setText(text)
        self.error_action_button.clicked.connect(
            callback
        )
        self.error_action_button.show()

    def clear_error_action(self):
        try:
            self.error_action_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass

        self.error_action_button.hide()


app = QApplication(sys.argv)
app.setApplicationName("BeatFrame")

if LOGO_PATH.exists():
    app.setWindowIcon(
        QIcon(str(LOGO_PATH))
    )

window = BeatFrame()
window.show()

QTimer.singleShot(
    0,
    lambda: apply_windows_dark_title_bar(window),
)

sys.exit(app.exec())
