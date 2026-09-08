import sys
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QObject,
    QSettings,
    QSize,
    QTimer,
    QPointF,
    QPropertyAnimation,
    QEasingCurve,
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
    QGraphicsOpacityEffect,
    QScrollArea,
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


class WindowsTaskbarProgress:
    """Native Windows taskbar progress. No-op on macOS/Linux."""

    TBPF_NOPROGRESS = 0x0
    TBPF_INDETERMINATE = 0x1
    TBPF_NORMAL = 0x2
    TBPF_ERROR = 0x4
    TBPF_PAUSED = 0x8

    def __init__(self, window):
        self._window = window
        self._taskbar = None

        if sys.platform != "win32":
            return

        try:
            import ctypes
            from ctypes import wintypes

            HRESULT = ctypes.c_long
            ULONG = ctypes.c_ulong
            ULONGLONG = ctypes.c_ulonglong
            HWND = wintypes.HWND

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            def guid(value):
                import uuid

                raw = uuid.UUID(value).bytes_le
                result = GUID()
                ctypes.memmove(
                    ctypes.byref(result),
                    raw,
                    ctypes.sizeof(result),
                )
                return result

            class ITaskbarList3:
                def __init__(self, pointer):
                    self.pointer = pointer
                    vtable = ctypes.cast(
                        pointer,
                        ctypes.POINTER(
                            ctypes.POINTER(ctypes.c_void_p)
                        ),
                    ).contents

                    self.Release = ctypes.WINFUNCTYPE(
                        ULONG,
                        ctypes.c_void_p,
                    )(vtable[2])

                    self.HrInit = ctypes.WINFUNCTYPE(
                        HRESULT,
                        ctypes.c_void_p,
                    )(vtable[3])

                    self.SetProgressValue = ctypes.WINFUNCTYPE(
                        HRESULT,
                        ctypes.c_void_p,
                        HWND,
                        ULONGLONG,
                        ULONGLONG,
                    )(vtable[9])

                    self.SetProgressState = ctypes.WINFUNCTYPE(
                        HRESULT,
                        ctypes.c_void_p,
                        HWND,
                        ctypes.c_int,
                    )(vtable[10])

            CLSID_TaskbarList = guid(
                "56FDF344-FD6D-11D0-958A-006097C9A090"
            )
            IID_ITaskbarList3 = guid(
                "EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84"
            )

            pointer = ctypes.c_void_p()
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)

            result = ole32.CoCreateInstance(
                ctypes.byref(CLSID_TaskbarList),
                None,
                1,
                ctypes.byref(IID_ITaskbarList3),
                ctypes.byref(pointer),
            )

            if result != 0 or not pointer.value:
                return

            taskbar = ITaskbarList3(pointer)
            if taskbar.HrInit(pointer) != 0:
                taskbar.Release(pointer)
                return

            self._taskbar = taskbar
            self._pointer = pointer

        except Exception:
            self._taskbar = None

    def _hwnd(self):
        return int(self._window.winId())

    def set_progress(self, percent: int):
        if self._taskbar is None:
            return

        try:
            percent = max(0, min(100, int(percent)))
            self._taskbar.SetProgressState(
                self._pointer,
                self._hwnd(),
                self.TBPF_NORMAL,
            )
            self._taskbar.SetProgressValue(
                self._pointer,
                self._hwnd(),
                percent,
                100,
            )
        except Exception:
            pass

    def set_error(self):
        if self._taskbar is None:
            return

        try:
            self._taskbar.SetProgressState(
                self._pointer,
                self._hwnd(),
                self.TBPF_ERROR,
            )
            self._taskbar.SetProgressValue(
                self._pointer,
                self._hwnd(),
                100,
                100,
            )
        except Exception:
            pass

    def clear(self):
        if self._taskbar is None:
            return

        try:
            self._taskbar.SetProgressState(
                self._pointer,
                self._hwnd(),
                self.TBPF_NOPROGRESS,
            )
        except Exception:
            pass


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


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)


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



class QueueCard(QFrame):
    remove_requested = Signal(int)

    def __init__(self, job_id: int, title: str, artwork_name: str, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.setObjectName("queueCard")
        self.setFixedHeight(72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        self.title_label = ElidedLabel(title)
        self.title_label.setObjectName("queueCardTitle")

        self.status_label = QLabel("Queued")
        self.status_label.setObjectName("queueCardStatus")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setFixedWidth(58)

        self.remove_button = QPushButton("×")
        self.remove_button.setObjectName("queueRemoveButton")
        self.remove_button.setFixedSize(24, 24)
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setToolTip("Remove from queue")
        self.remove_button.clicked.connect(
            lambda: self.remove_requested.emit(self.job_id)
        )

        top.addWidget(self.title_label, 1)
        top.addWidget(self.status_label)
        top.addWidget(self.remove_button)

        self.detail_label = ElidedLabel(artwork_name)
        self.detail_label.setObjectName("queueCardDetail")

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("queueCardProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()

        layout.addLayout(top)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.progress_bar)

        self.setStyleSheet(
            """
            QFrame#queueCard {
                background-color: rgba(255, 255, 255, 7);
                border: 1px solid rgba(162, 171, 255, 38);
                border-radius: 12px;
            }
            QLabel#queueCardTitle {
                color: #F4F5FF;
                font-size: 12px;
                font-weight: 650;
            }
            QLabel#queueCardStatus {
                color: #8792B3;
                font-size: 10px;
                font-weight: 600;
            }
            QLabel#queueCardDetail {
                color: #74809F;
                font-size: 10px;
            }

            QPushButton#queueRemoveButton {
                background: transparent;
                border: none;
                color: #7883A4;
                font-size: 17px;
                font-weight: 500;
                padding: 0px;
            }

            QPushButton#queueRemoveButton:hover {
                color: #E798E4;
                background-color: rgba(224, 82, 207, 14);
                border-radius: 12px;
            }

            QProgressBar#queueCardProgress {
                min-height: 5px;
                max-height: 5px;
                border: none;
                border-radius: 2px;
                background-color: rgba(255, 255, 255, 10);
            }
            QProgressBar#queueCardProgress::chunk {
                border-radius: 2px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4E8DFF,
                    stop: 0.52 #7474FF,
                    stop: 1 #E052CF
                );
            }
            """
        )

    def set_queued(self):
        self.status_label.setText("Queued")
        self.status_label.setStyleSheet("color: #8792B3;")
        self.remove_button.show()
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

    def set_rendering(self, percent: int = 0):
        percent = max(0, min(100, int(percent)))
        self.status_label.setText(f"{percent}%")
        self.status_label.setStyleSheet("color: #BFA8FF;")
        self.remove_button.hide()
        self.progress_bar.setValue(percent)
        self.progress_bar.show()

    def set_failed(self):
        self.status_label.setText("Failed")
        self.status_label.setStyleSheet("color: #E798E4;")
        self.remove_button.hide()
        self.progress_bar.hide()


class SuccessToast(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("successToast")
        self.setFixedSize(310, 76)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        check = QLabel("✓")
        check.setObjectName("toastCheck")
        check.setFixedWidth(24)
        check.setAlignment(Qt.AlignCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.title_label = ElidedLabel()
        self.title_label.setObjectName("toastTitle")

        subtitle = QLabel("Rendered successfully")
        subtitle.setObjectName("toastSubtitle")

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(subtitle)

        layout.addWidget(check)
        layout.addLayout(text_layout, 1)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.fade_in = QPropertyAnimation(
            self.opacity_effect,
            b"opacity",
            self,
        )
        self.fade_in.setDuration(180)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self.fade_out = QPropertyAnimation(
            self.opacity_effect,
            b"opacity",
            self,
        )
        self.fade_out.setDuration(280)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out.finished.connect(self.hide)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._begin_fade_out)

        self.setStyleSheet(
            """
            QFrame#successToast {
                background-color: rgba(12, 18, 42, 245);
                border: 1px solid rgba(135, 214, 177, 105);
                border-radius: 15px;
            }

            QLabel#toastCheck {
                color: #8FE0B7;
                font-size: 22px;
                font-weight: 700;
            }

            QLabel#toastTitle {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 650;
            }

            QLabel#toastSubtitle {
                color: #9EABC9;
                font-size: 11px;
            }
            """
        )

    def show_message(self, title: str):
        self.hide_timer.stop()
        self.fade_in.stop()
        self.fade_out.stop()

        self.title_label.setText(title)
        self.opacity_effect.setOpacity(0.0)
        self.show()
        self.raise_()
        self.fade_in.start()
        self.hide_timer.start(2500)

    def _begin_fade_out(self):
        self.fade_in.stop()
        self.fade_out.stop()
        self.fade_out.setStartValue(
            self.opacity_effect.opacity()
        )
        self.fade_out.start()


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
        self.fade_spinbox.setButtonSymbols(
            QDoubleSpinBox.NoButtons
        )

        fade_row = QWidget()
        fade_row_layout = QHBoxLayout(fade_row)
        fade_row_layout.setContentsMargins(0, 0, 0, 0)
        fade_row_layout.setSpacing(6)

        fade_buttons = QWidget()
        fade_buttons.setFixedWidth(30)
        fade_buttons_layout = QVBoxLayout(fade_buttons)
        fade_buttons_layout.setContentsMargins(0, 0, 0, 0)
        fade_buttons_layout.setSpacing(2)

        self.fade_up_button = QPushButton("▲")
        self.fade_up_button.setObjectName("spinArrowButton")
        self.fade_up_button.setFixedSize(30, 20)
        self.fade_up_button.setCursor(Qt.PointingHandCursor)
        self.fade_up_button.clicked.connect(
            self.fade_spinbox.stepUp
        )

        self.fade_down_button = QPushButton("▼")
        self.fade_down_button.setObjectName("spinArrowButton")
        self.fade_down_button.setFixedSize(30, 20)
        self.fade_down_button.setCursor(Qt.PointingHandCursor)
        self.fade_down_button.clicked.connect(
            self.fade_spinbox.stepDown
        )

        fade_buttons_layout.addWidget(self.fade_up_button)
        fade_buttons_layout.addWidget(self.fade_down_button)

        fade_row_layout.addWidget(self.fade_spinbox, 1)
        fade_row_layout.addWidget(fade_buttons)

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
            fade_row,
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

            QPushButton#spinArrowButton {
                background: transparent;
                border: none;
                color: #BFA8FF;
                font-size: 9px;
                padding: 0px;
            }

            QPushButton#spinArrowButton:hover {
                background-color: rgba(255, 255, 255, 8);
                border: none;
                color: #FFFFFF;
            }

            QPushButton#spinArrowButton:pressed {
                background-color: rgba(191, 168, 255, 22);
            }
            """
        )


@dataclass
class RenderJob:
    audio_path: Path
    artwork_path: Path
    output_dir: str
    fade_duration: float
    intro_path: Optional[str]
    job_id: int = 0


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

        self.active_job = None
        self.render_queue = []
        self.queue_paused = False
        self._next_job_id = 1
        self.queue_cards = {}
        self._close_requested = False

        self.pending_audio = None
        self.pending_artwork = None

        self.build_ui()
        self.apply_styles()

        self.success_toast = SuccessToast(
            self.centralWidget()
        )
        self._position_success_toast()

        self.taskbar_progress = WindowsTaskbarProgress(self)

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

        self.main_browse_plus = ClickableLabel(
            "",
            self.status_container,
        )
        self.main_browse_plus.setObjectName("mainBrowsePlus")
        self.main_browse_plus.setFixedSize(84, 84)
        self.main_browse_plus.move(
            (112 - self.main_browse_plus.width()) // 2,
            (112 - self.main_browse_plus.height()) // 2,
        )
        self.main_browse_plus.setToolTip(
            "Browse for audio + artwork"
        )
        self.main_browse_plus.clicked.connect(
            self.browse_for_pair
        )
        self.main_browse_plus.raise_()

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

        self.content_row = QHBoxLayout()
        self.content_row.setContentsMargins(0, 0, 0, 0)
        self.content_row.setSpacing(16)
        self.content_row.addWidget(self.drop_frame, 1)

        self.queue_panel = GlassFrame()
        self.queue_panel.setObjectName("queuePanel")
        self.queue_panel.setFixedWidth(238)
        self.queue_panel.hide()

        queue_shadow = QGraphicsDropShadowEffect(self.queue_panel)
        queue_shadow.setBlurRadius(42)
        queue_shadow.setOffset(0, 10)
        queue_shadow.setColor(QColor(64, 48, 155, 78))
        self.queue_panel.setGraphicsEffect(queue_shadow)

        queue_layout = QVBoxLayout(self.queue_panel)
        queue_layout.setContentsMargins(14, 14, 14, 14)
        queue_layout.setSpacing(10)

        queue_header = QHBoxLayout()
        queue_title = QLabel("Queue")
        queue_title.setObjectName("queueTitle")
        self.queue_count_label = QLabel("")
        self.queue_count_label.setObjectName("queueCount")
        self.queue_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        queue_header.addWidget(self.queue_count_label)
        queue_layout.addLayout(queue_header)

        queue_divider = QFrame()
        queue_divider.setObjectName("queueDivider")
        queue_divider.setFixedHeight(1)
        queue_layout.addWidget(queue_divider)

        self.queue_empty_state = QWidget()
        empty_layout = QVBoxLayout(self.queue_empty_state)
        empty_layout.setContentsMargins(8, 22, 8, 22)
        empty_layout.setSpacing(7)
        empty_layout.setAlignment(Qt.AlignCenter)

        self.queue_empty_plus = ClickableLabel("＋")
        self.queue_empty_plus.setObjectName("queueEmptyPlus")
        self.queue_empty_plus.setAlignment(Qt.AlignCenter)
        self.queue_empty_plus.setToolTip(
            "Browse for audio + artwork"
        )
        self.queue_empty_plus.clicked.connect(
            self.browse_for_pair
        )

        self.queue_empty_title = QLabel("Add to queue")
        self.queue_empty_title.setObjectName("queueEmptyTitle")
        self.queue_empty_title.setAlignment(Qt.AlignCenter)
        self.queue_empty_title.setWordWrap(True)

        self.queue_empty_detail = QLabel("1 audio + 1 artwork")
        self.queue_empty_detail.setObjectName("queueEmptyDetail")
        self.queue_empty_detail.setAlignment(Qt.AlignCenter)

        empty_layout.addStretch()
        empty_layout.addWidget(self.queue_empty_plus)
        empty_layout.addWidget(self.queue_empty_title)
        empty_layout.addWidget(self.queue_empty_detail)
        empty_layout.addStretch()

        queue_layout.addWidget(self.queue_empty_state, 1)

        self.queue_scroll = QScrollArea()
        self.queue_scroll.setObjectName("queueScroll")
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.queue_scroll.setFrameShape(QFrame.NoFrame)

        self.queue_list_widget = QWidget()
        self.queue_list_widget.setObjectName("queueListWidget")
        self.queue_list_layout = QVBoxLayout(self.queue_list_widget)
        self.queue_list_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_list_layout.setSpacing(8)
        self.queue_list_layout.addStretch()

        self.queue_scroll.setWidget(self.queue_list_widget)
        queue_layout.addWidget(self.queue_scroll, 1)
        self.content_row.addWidget(self.queue_panel)

        main_layout.addLayout(self.content_row, 1)

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

    def closeEvent(self, event):
        if self.is_rendering or self.thread is not None:
            self._close_requested = True
            self.queue_paused = True
            self.render_queue.clear()

            for job_id in list(self.queue_cards.keys()):
                if self.active_job is None or job_id != self.active_job.job_id:
                    self._remove_queue_card(job_id)

            self.settings_button.setEnabled(False)
            self.cancel_button.setText("Closing...")
            self.cancel_button.setEnabled(False)

            if self.worker is not None:
                self.worker.cancel()

            print(
                "[BeatFrame] Closing: cancelling active render "
                "and clearing queue..."
            )
            event.ignore()
            return

        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "success_toast"):
            self._position_success_toast()

    def _position_success_toast(self):
        if not hasattr(self, "success_toast"):
            return

        root = self.centralWidget()
        if root is None:
            return

        margin = 28
        x = max(
            margin,
            root.width()
            - self.success_toast.width()
            - margin,
        )
        y = max(
            margin,
            root.height()
            - self.success_toast.height()
            - 48,
        )
        self.success_toast.move(x, y)

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

            QFrame#queuePanel {
                background: transparent;
                border: none;
            }
            QLabel#queueTitle {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#queueCount {
                color: #8E9ABD;
                font-size: 10px;
                font-weight: 600;
            }
            QLabel#queueEmptyPlus {
                color: #BFA8FF;
                font-size: 28px;
            }
            QLabel#queueEmptyPlus:hover {
                color: #FFFFFF;
            }
            QLabel#queueEmptyTitle {
                color: #E7E9F7;
                font-size: 12px;
                font-weight: 650;
            }
            QLabel#queueEmptyDetail {
                color: #74809F;
                font-size: 10px;
            }
            QFrame#queueDivider {
                background-color: rgba(255, 255, 255, 16);
                border: none;
            }
            QScrollArea#queueScroll,
            QWidget#queueListWidget {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 7px;
                margin: 2px 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(151, 157, 205, 58);
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(170, 176, 225, 90);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                height: 0px;
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
        result = dialog.exec()

        if (
            result == QDialog.Accepted
            and self.queue_paused
            and self.render_queue
            and self.thread is None
        ):
            self.queue_paused = False
            self._start_next_queued_job()

    def dragEnterEvent(self, event):
        auto_render = self.settings.value(
            "auto_render",
            True,
            type=bool,
        )

        # Queueing is automatic in the normal auto-render workflow.
        # Manual mode keeps the old one-pair-at-a-time behavior until
        # we design its queue UX explicitly.
        if self.is_rendering and not auto_render:
            return

        if event.mimeData().hasUrls():
            if self.is_rendering:
                self.queue_panel.set_drag_active(True)
            else:
                self.drop_frame.set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_frame.set_drag_active(False)
        self.queue_panel.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_frame.set_drag_active(False)
        self.queue_panel.set_drag_active(False)

        files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]

        self._handle_input_files(files)
        event.acceptProposedAction()

    def browse_for_pair(self):
        auto_render = self.settings.value(
            "auto_render",
            True,
            type=bool,
        )

        if self.is_rendering and not auto_render:
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose audio + artwork",
            str(Path.home()),
            (
                "BeatFrame media "
                "(*.wav *.mp3 *.jpg *.jpeg *.png)"
            ),
        )

        if not file_paths:
            return

        self._handle_input_files(
            [Path(path) for path in file_paths]
        )

    def _handle_input_files(self, files):
        auto_render = self.settings.value(
            "auto_render",
            True,
            type=bool,
        )

        if self.is_rendering and not auto_render:
            return

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
            self._show_drop_error(
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
            self._show_drop_error(
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
            len(files) != 2
            or len(audio_files) != 1
            or len(image_files) != 1
        ):
            self._show_drop_error(
                "Choose exactly one audio file + one image",
                "Audio: WAV or MP3  •  Image: JPG, JPEG or PNG",
            )
            return

        audio = audio_files[0]
        artwork = image_files[0]

        if auto_render:
            job = self._create_render_job(
                audio,
                artwork,
            )
            self._submit_job(job)
        else:
            self.clear_error_action()
            self.pending_audio = audio
            self.pending_artwork = artwork
            self.show_files_ready()

    def _show_drop_error(
        self,
        title: str,
        detail: str,
    ):
        # A bad second drop must not replace the progress UI of the
        # render that is already running. Queue cards will give this
        # its own visual feedback in the next UX pass.
        if self.is_rendering:
            print(
                f"[BeatFrame] Drop rejected: {title} — {detail}"
            )
            return

        self.show_input_error(
            title,
            detail,
        )

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

    def _create_render_job(
        self,
        audio: Path,
        artwork: Path,
    ):
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

        job = RenderJob(
            audio_path=audio,
            artwork_path=artwork,
            output_dir=output_dir,
            fade_duration=fade_duration,
            intro_path=active_intro,
            job_id=self._next_job_id,
        )
        self._next_job_id += 1
        return job

    def _add_queue_card(self, job: RenderJob):
        if job.job_id in self.queue_cards:
            return

        card = QueueCard(
            job.job_id,
            job.audio_path.stem,
            job.artwork_path.name,
        )
        card.remove_requested.connect(
            self.remove_queued_job
        )

        index = max(0, self.queue_list_layout.count() - 1)
        self.queue_list_layout.insertWidget(index, card)
        self.queue_cards[job.job_id] = card
        self._refresh_queue_panel()

    def _remove_queue_card(self, job_id: int):
        card = self.queue_cards.pop(job_id, None)
        if card is not None:
            self.queue_list_layout.removeWidget(card)
            card.deleteLater()
        self._refresh_queue_panel()

    def remove_queued_job(self, job_id: int):
        job_to_remove = next(
            (
                job
                for job in self.render_queue
                if job.job_id == job_id
            ),
            None,
        )

        if job_to_remove is None:
            return

        self.render_queue = [
            job
            for job in self.render_queue
            if job.job_id != job_id
        ]

        self._remove_queue_card(job_id)

        print(
            f"[BeatFrame] Removed from queue: "
            f"{job_to_remove.audio_path.name} "
            f"({len(self.render_queue)} queued)"
        )

        self._refresh_queue_panel()

    def _refresh_queue_panel(self):
        waiting = len(self.render_queue)
        has_active = (
            self.active_job is not None
            and self.is_rendering
        )

        should_show = has_active or waiting > 0
        self.queue_panel.setVisible(should_show)

        if not should_show:
            return

        self.queue_count_label.setText(
            f"{waiting} waiting" if waiting else ""
        )
        self.queue_empty_state.setVisible(waiting == 0)
        self.queue_scroll.setVisible(waiting > 0)

    def _mark_active_progress(self, percent: int):
        if self.active_job is None:
            return
        card = self.queue_cards.get(self.active_job.job_id)
        if card is not None:
            card.set_rendering(percent)

    def _submit_job(
        self,
        job: RenderJob,
    ):
        self.render_queue.append(job)
        self._add_queue_card(job)

        print(
            f"[BeatFrame] Added: {job.audio_path.name} "
            f"(queue: {len(self.render_queue)})"
        )

        if (
            not self.is_rendering
            and self.thread is None
            and not self.queue_paused
        ):
            self._start_next_queued_job()

    def _start_next_queued_job(self):
        if (
            self._close_requested
            or self.is_rendering
            or self.thread is not None
            or self.queue_paused
            or not self.render_queue
        ):
            return

        job = self.render_queue.pop(0)
        self._refresh_queue_panel()
        self._start_job(job)

    def render_pending_files(self):
        if (
            self.pending_audio is None
            or self.pending_artwork is None
        ):
            return

        job = self._create_render_job(
            self.pending_audio,
            self.pending_artwork,
        )

        self.pending_audio = None
        self.pending_artwork = None
        self.render_button.hide()

        self._submit_job(job)

    def _start_job(
        self,
        job: RenderJob,
    ):
        self.active_job = job
        self.is_rendering = True
        self.main_browse_plus.setEnabled(False)
        self.main_browse_plus.setCursor(Qt.ArrowCursor)

        self.settings_button.setEnabled(False)
        self.render_button.hide()
        self.clear_error_action()

        self.status_icon.setLoading(False)
        self.status_icon.setText("")
        self.status_icon.setLoading(True)

        self.main_label.setText(job.audio_path.stem)
        self.detail_label.setText("Rendering... 0%")

        self.progress_bar.setRange(0, 100)
        self.progress_bar.reset()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.taskbar_progress.set_progress(0)

        self.cancel_button.setText("Cancel")
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()

        card = self.queue_cards.get(job.job_id)
        if card is not None:
            card.set_rendering(0)
        self._refresh_queue_panel()

        print(
            f"[BeatFrame] Rendering: {job.audio_path.name} "
            f"({len(self.render_queue)} queued)"
        )

        self.start_render(
            image_path=str(job.artwork_path),
            audio_path=str(job.audio_path),
            output_dir=job.output_dir,
            fade_duration=job.fade_duration,
            intro_path=job.intro_path,
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
            self._render_thread_finished
        )
        self.thread.finished.connect(
            self.thread.deleteLater
        )

        self.thread.start()

    def update_progress(
        self,
        percent: int,
    ):
        percent = max(0, min(100, int(percent)))
        self.progress_bar.setValue(percent)
        self.detail_label.setText(
            f"Rendering... {percent}%"
        )
        self._mark_active_progress(percent)
        self.taskbar_progress.set_progress(percent)

    def render_finished(
        self,
        output_path: str,
    ):
        finished_job = self.active_job
        finished_name = (
            finished_job.audio_path.name
            if finished_job is not None
            else Path(output_path).name
        )

        self.progress_bar.setValue(100)
        self.taskbar_progress.set_progress(100)
        self.cancel_button.hide()
        has_queued_jobs = bool(self.render_queue)

        if has_queued_jobs:
            self.success_toast.show_message(
                Path(output_path).stem
            )
        else:
            self.status_icon.playSuccess()
            self.main_label.setText("Ready")
            self.detail_label.setText(
                Path(output_path).name
            )

        self.is_rendering = False
        self.active_job = None

        if finished_job is not None:
            self._remove_queue_card(finished_job.job_id)

        print(
            f"[BeatFrame] Finished: {finished_name} "
            f"({len(self.render_queue)} queued)"
        )

        self._refresh_queue_panel()

        if not has_queued_jobs:
            self.settings_button.setEnabled(True)
            QTimer.singleShot(
                3200,
                self.reset_idle_state,
            )

    def _render_thread_finished(self):
        self.worker = None
        self.thread = None

        if self._close_requested:
            self.is_rendering = False
            self.active_job = None
            QTimer.singleShot(
                0,
                self.close,
            )
            return

        if (
            self.render_queue
            and not self.queue_paused
        ):
            self._start_next_queued_job()
        elif not self.is_rendering:
            self.settings_button.setEnabled(True)
            self._refresh_queue_panel()

    def reset_idle_state(self):
        self.main_browse_plus.setEnabled(True)
        self.main_browse_plus.setCursor(Qt.PointingHandCursor)
        if (
            self.is_rendering
            or self.thread is not None
            or self.render_queue
            or self.pending_audio is not None
            or self.pending_artwork is not None
        ):
            return

        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.taskbar_progress.clear()
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
        self._refresh_queue_panel()

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
        cancelled_job = self.active_job
        cancelled_name = (
            cancelled_job.audio_path.name
            if cancelled_job is not None
            else "current render"
        )

        self.status_icon.setLoading(False)
        self.status_icon.setText("×")
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.taskbar_progress.clear()
        self.cancel_button.hide()
        self.cancel_button.setText("Cancel")
        self.cancel_button.setEnabled(True)

        self.active_job = None
        self.is_rendering = False

        if cancelled_job is not None:
            self._remove_queue_card(cancelled_job.job_id)

        self.main_label.setText("Cancelled")
        self.detail_label.setText(
            "Current render cancelled."
        )

        print(
            f"[BeatFrame] Cancelled: {cancelled_name} "
            f"({len(self.render_queue)} queued)"
        )

        self._refresh_queue_panel()

        if self._close_requested:
            return

        if not self.render_queue:
            self.settings_button.setEnabled(True)
            QTimer.singleShot(
                1400,
                self.reset_idle_state,
            )

    def render_failed(
        self,
        error_type: str,
        message: str,
    ):
        failed_job = self.active_job
        failed_name = (
            failed_job.audio_path.name
            if failed_job is not None
            else "current render"
        )

        self.status_icon.setLoading(False)
        self.progress_bar.setVisible(False)
        self.taskbar_progress.set_error()
        self.cancel_button.hide()
        self.clear_error_action()

        self.active_job = None
        self.is_rendering = False

        if failed_job is not None:
            card = self.queue_cards.get(failed_job.job_id)
            if card is not None:
                card.set_failed()
            QTimer.singleShot(
                1800,
                lambda job_id=failed_job.job_id:
                    self._remove_queue_card(job_id),
            )

        if error_type == "missing_intro":
            self.queue_paused = True
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
            self.queue_paused = True
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
                "Skipping this job."
            )

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
                "Skipping this job."
            )

        elif error_type == "render_error":
            self.status_icon.setText("!")
            self.main_label.setText(
                "Render failed"
            )
            self.detail_label.setText(
                "BeatFrame couldn't complete the render. "
                "Skipping this job."
            )

        else:
            self.status_icon.setText("!")
            self.main_label.setText(
                "Something went wrong"
            )
            self.detail_label.setText(
                message
            )

        print(
            f"[BeatFrame] Failed: {failed_name} "
            f"[{error_type}] ({len(self.render_queue)} queued)"
        )

        self._refresh_queue_panel()

        if self._close_requested:
            return

        if not self.render_queue:
            self.settings_button.setEnabled(True)

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
