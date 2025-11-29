# cuby/widgets.py
from __future__ import annotations

import os
from typing import List, Any

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Signal, Slot

from .constants import CUBY_ACCENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def elide_middle(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    half = max_len // 2 - 2
    return text[:half] + "…" + text[-half:]


def last_snippet(messages: List[Any], max_chars: int = 40) -> str:
    """
    Try to extract a short snippet from the last non-empty message.
    Works with objects having .text or dicts with ["text"].
    """
    if not messages:
        return ""
    for m in reversed(messages):
        txt = ""
        if hasattr(m, "text"):
            txt = getattr(m, "text", "") or ""
        elif isinstance(m, dict):
            txt = m.get("text", "") or ""
        txt = txt.strip()
        if txt:
            return (txt[: max_chars - 1] + "…") if len(txt) > max_chars else txt
    return ""


# ---------------------------------------------------------------------------
# CardFrame: glassy rounded card
# ---------------------------------------------------------------------------

class CardFrame(QtWidgets.QFrame):
    def __init__(self, dark: bool = True, parent=None):
        super().__init__(parent)
        self._dark = dark
        self.setObjectName("CubyCard")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.apply_style(dark)

    def apply_style(self, dark: bool):
        self._dark = dark
        if dark:
            bg = "rgba(15,23,42,0.80)"
            border = "rgba(148,163,184,0.35)"
        else:
            bg = "rgba(255,255,255,0.85)"
            border = "rgba(148,163,184,0.40)"

        self.setStyleSheet(
            f"""
            #CubyCard {{
                background: {bg};
                border-radius: 18px;
                border: 1px solid {border};
            }}
        """
        )


# ---------------------------------------------------------------------------
# SidebarItemWidget: conversation item with hover + delete button
# ---------------------------------------------------------------------------

class SidebarItemWidget(QtWidgets.QWidget):
    """
    One row in the conversations list:
      - icon
      - title
      - subtitle (last message snippet)
      - delete button (visible on hover)
    """

    deleteRequested = Signal()  # window.py وصل می‌شه و conv_id رو می‌دونه

    def __init__(self, title: str, subtitle: str, active: bool, dark: bool, parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._active = active
        self._dark = dark
        self._hovered = False

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(6)

        # icon
        self.icon_label = QtWidgets.QLabel("💬")
        self.icon_label.setFixedWidth(20)
        self.icon_label.setAlignment(QtCore.Qt.AlignCenter)

        # text column
        text_col = QtWidgets.QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self.title_label = QtWidgets.QLabel(self._title or "New Chat")
        self.title_label.setObjectName("ConvTitle")
        self.title_label.setWordWrap(False)

        self.subtitle_label = QtWidgets.QLabel(self._subtitle or "")
        self.subtitle_label.setObjectName("ConvSubtitle")
        self.subtitle_label.setWordWrap(False)
        self.subtitle_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.subtitle_label.setStyleSheet("font-size: 11px;")

        text_col.addWidget(self.title_label)
        text_col.addWidget(self.subtitle_label)

        # delete button (hidden by default)
        self.delete_btn = QtWidgets.QToolButton()
        self.delete_btn.setText("✕")
        self.delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.delete_btn.setAutoRaise(True)
        self.delete_btn.setFixedSize(18, 18)
        self.delete_btn.setToolTip("Delete conversation")

        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.hide()

        root.addWidget(self.icon_label)
        root.addLayout(text_col, 1)
        root.addWidget(self.delete_btn, 0, QtCore.Qt.AlignTop)

        self._update_style()

    # ---- public setters ----

    def set_title(self, title: str):
        self._title = title or "New Chat"
        self.title_label.setText(self._title)

    def set_subtitle(self, subtitle: str):
        self._subtitle = subtitle or ""
        self.subtitle_label.setText(self._subtitle)

    def set_active(self, active: bool):
        self._active = bool(active)
        self._update_style()

    def set_dark(self, dark: bool):
        self._dark = bool(dark)
        self._update_style()

    def set_icon_from_messages(self, messages: List[Any]):
        """
        Simple heuristic: if there's assistant messages → 🤖,
        user messages → 🧑, otherwise 💬.
        """
        has_assistant = False
        has_user = False
        for m in messages:
            role = ""
            if hasattr(m, "role"):
                role = getattr(m, "role", "") or ""
            elif isinstance(m, dict):
                role = m.get("role", "") or ""
            role = role.lower()
            if role == "assistant":
                has_assistant = True
            elif role == "user":
                has_user = True

        if has_assistant and has_user:
            icon = "💬"
        elif has_assistant:
            icon = "🤖"
        elif has_user:
            icon = "🧑"
        else:
            icon = "💬"

        self.icon_label.setText(icon)

    # ---- style & hover handling ----

    def _update_style(self):
        if self._dark:
            base_bg = "transparent"
            hover_bg = "rgba(148,163,184,0.12)"
            active_bg = "rgba(129,140,248,0.28)"
            title_fg = "#e5e7eb"
            subtitle_fg = "rgba(148,163,184,0.95)"
        else:
            base_bg = "transparent"
            hover_bg = "rgba(148,163,184,0.12)"
            active_bg = "rgba(79,70,229,0.10)"
            title_fg = "#111827"
            subtitle_fg = "rgba(75,85,99,0.95)"

        if self._active:
            bg = active_bg
        elif self._hovered:
            bg = hover_bg
        else:
            bg = base_bg

        self.setStyleSheet(
            f"""
            QWidget {{
                background: {bg};
                border-radius: 10px;
            }}
            QLabel#ConvTitle {{
                font-weight: 600;
                font-size: 13px;
                color: {title_fg};
            }}
            QLabel#ConvSubtitle {{
                font-size: 11px;
                color: {subtitle_fg};
            }}
        """
        )

    def enterEvent(self, event: QtCore.QEnterEvent):
        self._hovered = True
        self._update_style()
        self.delete_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent):
        self._hovered = False
        self._update_style()
        self.delete_btn.hide()
        super().leaveEvent(event)

    @Slot()
    def _on_delete_clicked(self):
        self.deleteRequested.emit()


# ---------------------------------------------------------------------------
# TogglePill: mic/speaker pill-style toggle button
# ---------------------------------------------------------------------------

class TogglePill(QtWidgets.QPushButton):
    def __init__(self, text_on: str, text_off: str, checked: bool = True, parent=None):
        super().__init__(parent)
        self._text_on = text_on
        self._text_off = text_off
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(30)
        self._update_appearance()
        self.toggled.connect(self._on_toggled)

    @Slot(bool)
    def _on_toggled(self, checked: bool):
        self._update_appearance()

    def _update_appearance(self):
        if self.isChecked():
            txt = self._text_on
            bg = "rgba(34,197,94,0.18)"
            fg = "#22c55e"
            border = "rgba(34,197,94,0.8)"
        else:
            txt = self._text_off
            bg = "rgba(248,113,113,0.12)"
            fg = "#f97373"
            border = "rgba(248,113,113,0.8)"

        self.setText(txt)
        self.setStyleSheet(
            f"""
            QPushButton {{
                border-radius: 999px;
                padding: 6px 14px;
                border: 1px solid {border};
                background: {bg};
                color: {fg};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:pressed {{
                background: rgba(0,0,0,0.08);
            }}
        """
        )


# ---------------------------------------------------------------------------
# SettingsDialog
# ---------------------------------------------------------------------------

class SettingsDialog(QtWidgets.QDialog):
    """
    Tabbed settings dialog:
      - General: instructions, voice, dark mode
      - Realtime: VAD threshold, silence, API key
      - Company Knowledge: enable, file list, add/remove, rebuild flag
    """

    def __init__(
        self,
        parent=None,
        initial_instructions: str = "",
        initial_voice: str = "alloy",
        dark_mode: bool = True,
        initial_vad_threshold: float = 0.95,
        initial_vad_silence_ms: int = 1600,
        initial_api_key: str = "",
        initial_knowledge_files: list[str] | None = None,
        initial_knowledge_enabled: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(640, 520)

        self._initial_instructions = initial_instructions or ""
        self._initial_voice = initial_voice or "alloy"
        self._initial_dark = bool(dark_mode)
        self._initial_vad_threshold = float(initial_vad_threshold)
        self._initial_vad_silence_ms = int(initial_vad_silence_ms)
        self._initial_api_key = initial_api_key or ""
        self._initial_knowledge_files = list(initial_knowledge_files or [])
        self._initial_knowledge_enabled = bool(initial_knowledge_enabled)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._build_tab_general()
        self._build_tab_realtime()
        self._build_tab_company_knowledge()

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ---- tabs ----

    def _build_tab_general(self):
        tab = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Instructions
        lbl_instr = QtWidgets.QLabel("System Instructions")
        lbl_instr.setStyleSheet("font-weight:600;")
        self.txt_instructions = QtWidgets.QPlainTextEdit()
        self.txt_instructions.setPlainText(self._initial_instructions)
        self.txt_instructions.setMinimumHeight(140)

        # Voice
        voice_row = QtWidgets.QHBoxLayout()
        lbl_voice = QtWidgets.QLabel("Voice")
        lbl_voice.setStyleSheet("font-weight:600;")
        self.combo_voice = QtWidgets.QComboBox()
        # چند گزینه رایج؛ در صورت پشتیبانی بیشتر می‌تونی اضافه کنی
        self.combo_voice.addItems(
            ["alloy", "ash", "ballad", "verse", "sage"]
        )
        idx = self.combo_voice.findText(self._initial_voice)
        if idx >= 0:
            self.combo_voice.setCurrentIndex(idx)

        voice_row.addWidget(lbl_voice)
        voice_row.addWidget(self.combo_voice, 1)

        # Theme toggle
        self.chk_dark = QtWidgets.QCheckBox("Enable dark mode")
        self.chk_dark.setChecked(self._initial_dark)

        lay.addWidget(lbl_instr)
        lay.addWidget(self.txt_instructions)
        lay.addLayout(voice_row)
        lay.addWidget(self.chk_dark)
        lay.addStretch(1)

        self.tabs.addTab(tab, "General")

    def _build_tab_realtime(self):
        tab = QtWidgets.QWidget()
        lay = QtWidgets.QFormLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # VAD threshold
        self.spin_vad_threshold = QtWidgets.QDoubleSpinBox()
        self.spin_vad_threshold.setRange(0.0, 1.0)
        self.spin_vad_threshold.setSingleStep(0.01)
        self.spin_vad_threshold.setValue(self._initial_vad_threshold)
        self.spin_vad_threshold.setDecimals(2)

        lbl_vad_th = QtWidgets.QLabel("VAD threshold")
        lbl_vad_th_help = QtWidgets.QLabel(
            "Higher threshold = the model is less sensitive and "
            "ignores quieter background noise."
        )
        lbl_vad_th_help.setWordWrap(True)
        lbl_vad_th_help.setStyleSheet("font-size:11px; color:gray;")

        # Silence duration
        self.spin_vad_silence = QtWidgets.QSpinBox()
        self.spin_vad_silence.setRange(100, 6000)
        self.spin_vad_silence.setSingleStep(100)
        self.spin_vad_silence.setValue(self._initial_vad_silence_ms)

        lbl_vad_sil = QtWidgets.QLabel("Silence duration (ms)")
        lbl_vad_sil_help = QtWidgets.QLabel(
            "Longer silence = Cuby waits more before ending your turn."
        )
        lbl_vad_sil_help.setWordWrap(True)
        lbl_vad_sil_help.setStyleSheet("font-size:11px; color:gray;")

        # API key
        self.edit_api_key = QtWidgets.QLineEdit()
        self.edit_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.edit_api_key.setText(self._initial_api_key)
        self.edit_api_key.setPlaceholderText("OpenAI API key")

        lay.addRow(lbl_vad_th, self.spin_vad_threshold)
        lay.addRow("", lbl_vad_th_help)
        lay.addRow(lbl_vad_sil, self.spin_vad_silence)
        lay.addRow("", lbl_vad_sil_help)
        lay.addRow(QtWidgets.QLabel("OpenAI API key"), self.edit_api_key)

        self.tabs.addTab(tab, "Realtime")

    def _build_tab_company_knowledge(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        self.chk_enable_knowledge = QtWidgets.QCheckBox(
            "Enable company knowledge (RAG)"
        )
        self.chk_enable_knowledge.setChecked(self._initial_knowledge_enabled)

        info = QtWidgets.QLabel(
            "Upload internal documents (docx, pdf, txt, …).\n"
            "Cuby will use them to answer company-related questions.\n"
            "Rebuilding may take time depending on file size."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size:11px; color:gray;")

        self.list_files = QtWidgets.QListWidget()
        self.list_files.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        for p in self._initial_knowledge_files:
            self.list_files.addItem(p)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add_files = QtWidgets.QPushButton("Add files…")
        self.btn_remove_files = QtWidgets.QPushButton("Remove selected")
        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_remove_files)
        btn_row.addStretch(1)

        self.chk_rebuild = QtWidgets.QCheckBox("Rebuild knowledge now")
        self.chk_rebuild.setToolTip(
            "If checked, embeddings will be rebuilt from selected files "
            "after you close Settings with OK."
        )

        v.addWidget(self.chk_enable_knowledge)
        v.addWidget(info)
        v.addWidget(self.list_files, 1)
        v.addLayout(btn_row)
        v.addWidget(self.chk_rebuild)

        self.btn_add_files.clicked.connect(self._add_files_clicked)
        self.btn_remove_files.clicked.connect(self._remove_files_clicked)

        self.tabs.addTab(tab, "Company Knowledge")

    # ---- Company knowledge file handlers ----

    @Slot()
    def _add_files_clicked(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select documents",
            "",
            "Documents (*.txt *.md *.docx *.pdf);;All files (*.*)",
        )
        if not paths:
            return
        existing = {self.list_files.item(i).text() for i in range(self.list_files.count())}
        for p in paths:
            if p not in existing:
                self.list_files.addItem(p)

    @Slot()
    def _remove_files_clicked(self):
        for item in self.list_files.selectedItems():
            row = self.list_files.row(item)
            self.list_files.takeItem(row)

    # ---- Values ----

    def values(self) -> dict:
        knowledge_files = [
            self.list_files.item(i).text()
            for i in range(self.list_files.count())
        ]

        return {
            "instructions": self.txt_instructions.toPlainText(),
            "voice": self.combo_voice.currentText(),
            "dark": self.chk_dark.isChecked(),
            "vad_threshold": float(self.spin_vad_threshold.value()),
            "vad_silence_ms": int(self.spin_vad_silence.value()),
            "api_key": self.edit_api_key.text().strip(),
            "knowledge_files": knowledge_files,
            "knowledge_enabled": self.chk_enable_knowledge.isChecked(),
            "knowledge_rebuild": self.chk_rebuild.isChecked(),
        }
