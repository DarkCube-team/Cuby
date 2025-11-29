# cuby/splash.py
from __future__ import annotations
from PySide6 import QtCore, QtGui, QtWidgets

class CubySplash(QtWidgets.QWidget):
    """
    Custom splash with app logo + title, status line, progress bar,
    and a maker row ("Built by DarkCube") with a small icon.
    """
    def __init__(
        self,
        logo_path: str | None = None,
        maker_logo_path: str | None = None,
        maker_line: str = "Built by DarkCube",
        dark: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.SplashScreen
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._dark = dark
        self._maker_line = maker_line
        self._build_ui(logo_path, maker_logo_path, dark)

    def _build_ui(self, logo_path: str | None, maker_logo_path: str | None, dark: bool):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QtWidgets.QFrame()
        card.setObjectName("SplashCard")
        card.setGraphicsEffect(self._shadow(20, 0.18))
        outer.addWidget(card)

        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        # --- Top: App logo + title
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(10)

        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setFixedSize(40, 40)
        self.logo_label.setAlignment(QtCore.Qt.AlignCenter)

        self._set_pixmap(self.logo_label, logo_path, fallback_text="■", w=40, h=40)

        self.title = QtWidgets.QLabel("Cuby — Less Type, More Talk")
        self.title.setObjectName("title")
        self.title.setStyleSheet("font-weight:800; letter-spacing:.2px;")
        self.title.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

        top.addWidget(self.logo_label, 0)
        top.addWidget(self.title, 1)
        lay.addLayout(top)

        # --- Status text
        self.status = QtWidgets.QLabel("Starting…")
        self.status.setStyleSheet("font-size:12px; opacity:.85;")
        lay.addWidget(self.status)

        # --- Progress
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)

        # --- Maker row (icon + text) — SINGLE source of "Built by DarkCube"
        maker_row = QtWidgets.QHBoxLayout()
        maker_row.setSpacing(8)
        maker_row.setAlignment(QtCore.Qt.AlignCenter)

        self.maker_icon = QtWidgets.QLabel()
        self.maker_icon.setFixedSize(16, 16)
        self.maker_icon.setAlignment(QtCore.Qt.AlignCenter)
        self._set_pixmap(self.maker_icon, maker_logo_path, fallback_text="⬛", w=16, h=16)

        self.maker_label = QtWidgets.QLabel(self._maker_line)
        self.maker_label.setStyleSheet("font-size:11px; opacity:.8;")

        maker_row.addWidget(self.maker_icon)
        maker_row.addWidget(self.maker_label)
        lay.addLayout(maker_row)

        # --- Hint (only the wait text to avoid duplication)
        self.hint = QtWidgets.QLabel("Please wait while Cuby initializes")
        self.hint.setStyleSheet("font-size:11px; opacity:.7;")
        self.hint.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.hint)

        # Apply theme
        self.apply_style(dark)

    def _set_pixmap(self, label: QtWidgets.QLabel, path: str | None, fallback_text: str, w: int, h: int):
        if path:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                label.setPixmap(pix)
                return
        label.setText(fallback_text)

    def _shadow(self, blur: int, opacity: float):
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, 8)
        shadow.setColor(QtGui.QColor(0, 0, 0, int(255 * opacity)))
        return shadow

    def apply_style(self, dark: bool):
        self._dark = dark
        if dark:
            bg = "rgba(15,23,42,0.86)"
            border = "rgba(148,163,184,0.35)"
            fg_title = "#e5e7eb"
            fg_text = "#cbd5e1"
            bar_bg = "rgba(255,255,255,0.12)"
        else:
            bg = "rgba(255,255,255,0.92)"
            border = "rgba(148,163,184,0.40)"
            fg_title = "#111827"
            fg_text = "#374151"
            bar_bg = "rgba(0,0,0,0.08)"

        self.setStyleSheet(
            f"""
            #SplashCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QLabel {{
                color: {fg_text};
            }}
            QLabel#title {{
                color: {fg_title};
            }}
            QProgressBar {{
                height: 10px;
                background: {bar_bg};
                border: 1px solid rgba(148,163,184,0.4);
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(99,102,241,1.0),
                    stop:1 rgba(56,189,248,0.95)
                );
                border-radius: 6px;
            }}
            """
        )

    def center_on_screen(self):
        screen = QtWidgets.QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.resize(460, 210)
        self.move(
            geo.center().x() - self.width() // 2,
            geo.center().y() - self.height() // 2
        )

    # ---- public API ----
    def set_progress(self, percent: int, text: str | None = None):
        self.progress.setValue(max(0, min(100, percent)))
        if text:
            self.status.setText(text)
        QtWidgets.QApplication.processEvents()
