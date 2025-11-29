# cuby/visuals.py
from PySide6 import QtCore, QtGui, QtWidgets
import random


class WaveformBars(QtWidgets.QWidget):
    """
    Simple animated audio visualizer made of vertical bars.

    - Call set_amplitude(amp: float) with values between 0.0 and 1.0.
    - The widget smooths the amplitude and animates a set of bars.
    - Used while the assistant is speaking to give a "voice assistant" feel.
    """

    def __init__(self, bars: int = 16, parent=None):
        super().__init__(parent)
        self._bars = bars
        self._levels = [0.0] * bars  # current height of each bar (0..1)
        self._target_amp = 0.0       # target amplitude from audio RMS
        self._smooth_amp = 0.0       # smoothed amplitude

        # Timer to drive the animation
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 FPS

    @QtCore.Slot(float)
    def set_amplitude(self, amp: float):
        """
        Update the target amplitude (0..1). This can be called from
        another thread via QMetaObject.invokeMethod.
        """
        self._target_amp = max(0.0, min(1.0, amp))

    def sizeHint(self):
        return QtCore.QSize(320, 80)

    def _tick(self):
        """Animation tick: smooth amplitude and update bar levels."""
        # Smoothly approach the target amplitude
        self._smooth_amp += (self._target_amp - self._smooth_amp) * 0.2

        # Slight random jitter per bar to make it look alive
        for i in range(self._bars):
            jitter = (random.random() - 0.5) * 0.15
            lvl = max(0.0, min(1.0, self._smooth_amp + jitter))
            # Smooth transition toward the new level
            self._levels[i] += (lvl - self._levels[i]) * 0.3

        self.update()

    def paintEvent(self, event):
        """Custom painting of the vertical bars."""
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)

        # Geometry
        bar_w = rect.width() / (self._bars * 1.5)
        gap = bar_w * 0.5
        x = rect.left()

        # Use the palette's highlight color (adapts to dark/light theme)
        color = self.palette().highlight().color()
        pen = QtGui.QPen(QtGui.QColor(color))
        pen.setWidthF(1.0)
        brush = QtGui.QBrush(QtGui.QColor(color))
        p.setPen(pen)
        p.setBrush(brush)

        base_y = rect.center().y()
        max_h = rect.height() / 2

        for lvl in self._levels:
            h = max_h * lvl
            r = QtCore.QRectF(x, base_y - h, bar_w, h * 2)
            # tighten vertical margins for nicer look
            r.adjust(0, 2, 0, -2)

            path = QtGui.QPainterPath()
            path.addRoundedRect(r, bar_w * 0.3, bar_w * 0.3)
            p.drawPath(path)

            x += bar_w + gap
