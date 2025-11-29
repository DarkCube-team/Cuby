from PySide6 import QtCore, QtGui, QtWidgets
from .constants import (
    CUBY_ACCENT,
    GLASS_BG_DARK,
    GLASS_BG_LIGHT,
    BORDER_RADIUS,
)

def apply_app_palette(dark: bool):
    app = QtWidgets.QApplication.instance()
    palette = QtGui.QPalette()
    app.setStyle("Fusion")
    if dark:
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(22, 22, 26))
        palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(15, 15, 18))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(28, 28, 32))
        palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(40, 40, 46))
        palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(120, 107, 255))
        palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)
    else:
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor(245, 246, 250))
        palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.black)
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(255, 255, 255))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(235, 235, 240))
        palette.setColor(QtGui.QPalette.Text, QtCore.Qt.black)
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(240, 240, 244))
        palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.black)
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(120, 107, 255))
        palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)
    app.setPalette(palette)

def bubble_colors(dark: bool):
    """
    Return (user_bg, user_fg, bot_bg, bot_fg, system_fg).
    Tuned so user text stays readable in both themes.
    """
    if dark:
        # Dark theme
        user_bg = "#3b82f6"                         # blue-500
        user_fg = "#ffffff"                         # white
        bot_bg  = "rgba(148,163,184,0.25)"          # slate-300 @ 25%
        bot_fg  = "#e5e7eb"                         # gray-200
        system_fg = "rgba(255,255,255,0.8)"
    else:
        # Light theme — make user text DARK and bubble LIGHT
        user_bg = "#e3f2ff"                         # very light blue
        user_fg = "#111827"                         # gray-900 (readable)
        bot_bg  = "#f3f4f6"                         # gray-100
        bot_fg  = "#111827"                         # gray-900
        system_fg = "rgba(17,24,39,0.6)"
    return user_bg, user_fg, bot_bg, bot_fg, system_fg

class GlassCardMixin:
    """Helper mixin for glass background on QFrame (used by CardFrame)."""
    def apply_glass(self, dark: bool, frame):
        bg = GLASS_BG_DARK if dark else GLASS_BG_LIGHT
        border = "rgba(255,255,255,0.1)" if dark else "rgba(0,0,0,0.08)"
        frame.setStyleSheet(f"""
            QFrame#CardFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {BORDER_RADIUS}px;
            }}
        """)
