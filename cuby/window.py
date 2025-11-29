# Cuby/window.py
import os
import json
import html
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets

from .constants import (
    APP_NAME,
    LOGO_PATH,
    DATA_DIR,
    LOG_PATH,
    CONV_PATH,
    SETTINGS_PATH,
    KNOWLEDGE_STORE_PATH,
    DEFAULT_INSTRUCTIONS,
    DEFAULT_VAD_THRESHOLD,
    DEFAULT_VAD_SILENCE_MS,
    DEFAULT_VOICE,
    CUBY_ACCENT,
)
from .theme import apply_app_palette, bubble_colors
from .widgets import (
    CardFrame,
    SidebarItemWidget,
    TogglePill,
    SettingsDialog,
    elide_middle,
    last_snippet,
)
from .realtime_client import RealtimeClient
from .visuals import WaveformBars
from .conversations import ConversationManager
from .company_knowledge import CompanyKnowledge


class CubyWindow(QtWidgets.QMainWindow):
    """Main UI window for Cuby."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 700)
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QtGui.QIcon(LOGO_PATH))

        os.makedirs(DATA_DIR, exist_ok=True)
        self.conv_manager = ConversationManager(CONV_PATH)
        self._current_conv_id: str | None = None
        self._sidebar_widgets: dict[str, SidebarItemWidget] = {}

        self._status_mode = "ready"
        self._avatar_pulse_on = False
        self._silence_ticks = 0

        # Sidebar drawer state
        self._sidebar_collapsed = False

        # ---- Load persisted settings (API key + knowledge config) ----
        self._settings = self._load_settings()
        self._api_key = self._settings.get("api_key", "") or os.getenv(
            "OPENAI_API_KEY", ""
        )
        self._knowledge_files = self._settings.get("knowledge_files", [])
        self._knowledge_enabled = bool(self._settings.get("knowledge_enabled", False))

        # Toolbar
        self.toolbar = self.addToolBar("Main")
        self.action_settings = QtGui.QAction("Settings", self)
        self.action_theme = QtGui.QAction("Toggle Theme", self)
        self.toolbar.addAction(self.action_settings)
        self.toolbar.addAction(self.action_theme)

        # Root layout
        root = QtWidgets.QWidget()
        root_lay = QtWidgets.QHBoxLayout(root)
        root_lay.setContentsMargins(12, 12, 12, 12)
        root_lay.setSpacing(12)
        self.setCentralWidget(root)

        # ----- Sidebar (Conversations) -----
        self.sidebar_card = CardFrame(dark=True)
        self.sidebar_card.setMinimumWidth(240)
        side_lay = QtWidgets.QVBoxLayout(self.sidebar_card)
        side_lay.setContentsMargins(10, 10, 10, 10)
        side_lay.setSpacing(8)

        # Header row: "Conversations" + drawer toggle button
        self.sidebar_header_row = QtWidgets.QWidget()
        header_lay = QtWidgets.QHBoxLayout(self.sidebar_header_row)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(4)

        self.conv_header = QtWidgets.QLabel("Conversations")
        self.conv_header.setStyleSheet("font-weight: 800; letter-spacing:.3px;")

        self.btn_sidebar_toggle = QtWidgets.QToolButton()
        self.btn_sidebar_toggle.setText("⟨")
        self.btn_sidebar_toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_sidebar_toggle.setAutoRaise(True)
        self.btn_sidebar_toggle.setToolTip("Collapse/expand sidebar")

        header_lay.addWidget(self.conv_header)
        header_lay.addStretch()
        header_lay.addWidget(self.btn_sidebar_toggle)

        side_lay.addWidget(self.sidebar_header_row)

        # Search bar for conversations
        self.conv_search = QtWidgets.QLineEdit()
        self.conv_search.setPlaceholderText("Search conversations…")
        self.conv_search.setClearButtonEnabled(True)
        self.conv_search.setFixedHeight(28)
        self.conv_search.setStyleSheet(
            """
            QLineEdit {
                border-radius: 10px;
                padding: 4px 8px;
                border: 1px solid rgba(255,255,255,0.15);
                background: rgba(0,0,0,0.10);
                font-size: 11px;
            }
        """
        )
        side_lay.addWidget(self.conv_search)

        self.conv_list = QtWidgets.QListWidget()
        self.conv_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.conv_list.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.conv_list.setSpacing(4)
        self.conv_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        side_lay.addWidget(self.conv_list, 1)

        self.btn_new_chat = QtWidgets.QPushButton("+ New Chat")
        self.btn_new_chat.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_new_chat.setStyleSheet(
            f"""
            QPushButton {{
                background: {CUBY_ACCENT};
                color: #fff;
                border: none;
                border-radius: 10px;
                padding: 10px 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{ filter: brightness(1.07); }}
        """
        )
        side_lay.addWidget(self.btn_new_chat)

        # Collapsed mini-panel (shown only when sidebar is collapsed)
        self.sidebar_collapsed_panel = QtWidgets.QWidget()
        cp_lay = QtWidgets.QVBoxLayout(self.sidebar_collapsed_panel)
        cp_lay.setContentsMargins(0, 4, 0, 0)
        cp_lay.setSpacing(6)
        cp_lay.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)

        self.btn_new_chat_small = QtWidgets.QToolButton()
        self.btn_new_chat_small.setText("+")
        self.btn_new_chat_small.setToolTip("New chat")
        self.btn_new_chat_small.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_new_chat_small.setAutoRaise(True)

        self.btn_search_small = QtWidgets.QToolButton()
        self.btn_search_small.setText("🔍")
        self.btn_search_small.setToolTip("Search conversations")
        self.btn_search_small.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_search_small.setAutoRaise(True)

        cp_lay.addWidget(self.btn_new_chat_small, 0, QtCore.Qt.AlignHCenter)
        cp_lay.addWidget(self.btn_search_small, 0, QtCore.Qt.AlignHCenter)
        side_lay.addWidget(self.sidebar_collapsed_panel)
        self.sidebar_collapsed_panel.hide()

        root_lay.addWidget(self.sidebar_card, 0)

        # ----- Chat card -----
        self.chat_card = CardFrame(dark=True)
        chat_card_lay = QtWidgets.QVBoxLayout(self.chat_card)
        chat_card_lay.setContentsMargins(12, 12, 12, 12)
        chat_card_lay.setSpacing(10)

        header = self._make_header_widget()
        chat_card_lay.addWidget(header)

        self.chat_view = QtWidgets.QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(
            """
            QTextBrowser {
                font-size: 14px;
                border: none;
                padding: 6px;
            }
        """
        )
        self.chat_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        chat_card_lay.addWidget(self.chat_view, 1)

        input_row = QtWidgets.QHBoxLayout()
        self.chat_edit = QtWidgets.QLineEdit()
        self.chat_edit.setPlaceholderText("Type here (or speak)…")
        self.chat_edit.setStyleSheet(
            """
            QLineEdit {
                border-radius: 12px;
                padding: 10px 12px;
                border: 1px solid rgba(255,255,255,0.15);
                background: rgba(0,0,0,0.15);
            }
        """
        )
        self.btn_send = QtWidgets.QPushButton("Send")
        self.btn_send.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_send.setStyleSheet(
            f"""
            QPushButton {{
                background: {CUBY_ACCENT};
                color: #fff;
                border: none;
                border-radius: 12px;
                padding: 10px 18px;
                font-weight: 700;
            }}
            QPushButton:hover {{ filter: brightness(1.07); }}
        """
        )
        input_row.addWidget(self.chat_edit, 1)
        input_row.addWidget(self.btn_send)
        chat_card_lay.addLayout(input_row)

        root_lay.addWidget(self.chat_card, 1)

        # ----- Voice card -----
        self.voice_card = CardFrame(dark=True)
        right_lay = QtWidgets.QVBoxLayout(self.voice_card)
        right_lay.setContentsMargins(12, 12, 12, 12)
        right_lay.setSpacing(10)

        self.lbl_status = QtWidgets.QLabel("Stopped")
        self.lbl_status.setStyleSheet("font-weight: 700;")
        right_lay.addWidget(self.lbl_status)

        # Start/Stop button (big round)
        self.btn_assistant = QtWidgets.QPushButton("▶")
        self.btn_assistant.setCheckable(True)
        self.btn_assistant.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_assistant.setFixedSize(90, 90)
        self.btn_assistant.setStyleSheet(
            f"""
            QPushButton {{
                background: {CUBY_ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 45px;
                font-size: 34px;
                font-weight: 800;
            }}
            QPushButton:checked {{
                background: #d9534f;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                filter: brightness(0.95); }}
        """
        )
        right_lay.addWidget(self.btn_assistant, 0, QtCore.Qt.AlignHCenter)

        # Waveform visualizer
        self.wave = WaveformBars(bars=18)
        right_lay.addWidget(self.wave, 1)

        # Mic hint when OFF
        self.lbl_mic_hint = QtWidgets.QLabel("Mic is OFF")
        self.lbl_mic_hint.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_mic_hint.setStyleSheet(
            """
            QLabel {
                padding: 4px 10px;
                border-radius: 999px;
                background: rgba(220, 53, 69, 0.15);
                color: #ff4d59;
                font-size: 11px;
                font-weight: 600;
            }
        """
        )
        self.lbl_mic_hint.hide()
        right_lay.addWidget(self.lbl_mic_hint, 0, QtCore.Qt.AlignHCenter)

        # Speaker hint when OFF
        self.lbl_speaker_hint = QtWidgets.QLabel("Speaker is OFF")
        self.lbl_speaker_hint.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_speaker_hint.setStyleSheet(
            """
            QLabel {
                padding: 4px 10px;
                border-radius: 999px;
                background: rgba(220, 53, 69, 0.15);
                color: #ff4d59;
                font-size: 11px;
                font-weight: 600;
            }
        """
        )
        self.lbl_speaker_hint.hide()
        right_lay.addWidget(self.lbl_speaker_hint, 0, QtCore.Qt.AlignHCenter)

        # Mic / Speaker toggles (bottom)
        toggles_row = QtWidgets.QHBoxLayout()
        toggles_row.setContentsMargins(0, 0, 0, 0)
        toggles_row.setSpacing(12)
        toggles_row.setAlignment(QtCore.Qt.AlignHCenter)

        self.btn_mic = TogglePill("🎙 Mic: ON", "🎙 Mic: OFF", checked=True)
        self.btn_speaker = TogglePill("🔊 Speaker: ON", "🔊 Speaker: OFF", checked=True)

        self.btn_mic.setMinimumWidth(140)
        self.btn_speaker.setMinimumWidth(140)

        toggles_row.addStretch()
        toggles_row.addWidget(self.btn_mic)
        toggles_row.addWidget(self.btn_speaker)
        toggles_row.addStretch()

        right_lay.addLayout(toggles_row)

        root_lay.addWidget(self.voice_card, 0)

        # ---- Realtime client & params ----
        self._dark = True
        self._base_instructions = DEFAULT_INSTRUCTIONS
        self._instructions = self._base_instructions
        self._voice = DEFAULT_VOICE
        self._vad_threshold = DEFAULT_VAD_THRESHOLD
        self._vad_silence_ms = DEFAULT_VAD_SILENCE_MS

        self.client = RealtimeClient(
            api_key=self._api_key or "",
            model=None,
            instructions=self._instructions,
            voice=self._voice,
            vad_threshold=self._vad_threshold,
            vad_silence_ms=self._vad_silence_ms,
        )
        self.client.on_event_text = self._on_transcript_message
        self.client.on_server_error = self._on_server_error
        self.client.on_status = self._on_status
        self.client.on_ws_state = self._on_ws_state
        self.client.on_audio_level = self._on_audio_level_from_client
        # user voice transcript (for audio RAG)
        self.client.on_user_transcript = self._on_user_transcript_from_client

        # ---- Company knowledge store ----
        self.company_knowledge = CompanyKnowledge(KNOWLEDGE_STORE_PATH)

        self._assistant_running = False
        self._avatar_pulse_timer = QtCore.QTimer(self)
        self._avatar_pulse_timer.setInterval(220)
        self._avatar_pulse_timer.timeout.connect(self._avatar_pulse_step)

        # Wire signals
        self.btn_send.clicked.connect(self._send_typed_message)
        self.chat_edit.returnPressed.connect(self._send_typed_message)
        self.btn_mic.toggled.connect(self._toggle_mic)
        self.btn_speaker.toggled.connect(self._toggle_speaker)
        self.btn_assistant.clicked.connect(self._toggle_assistant)
        self.action_settings.triggered.connect(self._open_settings)
        self.action_theme.triggered.connect(self._toggle_theme)
        self.btn_new_chat.clicked.connect(self._create_new_conversation)
        self.conv_list.currentItemChanged.connect(self._on_conversation_changed)
        self.conv_list.itemDoubleClicked.connect(self._rename_conversation_dialog)
        self.btn_sidebar_toggle.clicked.connect(self._toggle_sidebar_collapsed)
        self.conv_search.textChanged.connect(self._filter_conversations)
        self.btn_new_chat_small.clicked.connect(self._create_new_conversation)
        self.btn_search_small.clicked.connect(self._collapsed_search_clicked)

        # Apply fonts (from global font family set in main.py)
        self._apply_cuby_fonts()

        # Theme + conversations
        self._apply_theme(True)
        self._initialize_conversations()
        self._set_status_mode("ready")

        # If no API key, disable assistant and inform user
        if not self._api_key:
            self.btn_assistant.setEnabled(False)
            self._append_chat_system(
                "No OpenAI API key configured. Open Settings and enter your API key to start using Cuby."
            )
        else:
            self.btn_assistant.setEnabled(True)

    # ---------- Settings persistence ----------

    def _load_settings(self) -> dict:
        try:
            if not os.path.exists(SETTINGS_PATH):
                return {}
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = {
                "api_key": self._api_key or "",
                "knowledge_files": list(self._knowledge_files),
                "knowledge_enabled": bool(self._knowledge_enabled),
            }
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- Fonts ----------

    def _apply_cuby_fonts(self):
        """
        Apply bundled font family with appropriate weights to key widgets.
        Uses the current QApplication font family as base (set in main.py).
        """
        base_font = self.font()
        family = base_font.family()

        # Title (bigger & semibold)
        title_font = QtGui.QFont(family, 14, QtGui.QFont.Weight.DemiBold)
        title_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.header_title.setFont(title_font)

        # Subtitle (regular)
        subtitle_font = QtGui.QFont(family, 11, QtGui.QFont.Weight.Normal)
        subtitle_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.header_subtitle.setFont(subtitle_font)

        # Conversation header (semibold)
        conv_hdr_font = QtGui.QFont(family, 12, QtGui.QFont.Weight.DemiBold)
        conv_hdr_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.conv_header.setFont(conv_hdr_font)

        # Send button (medium)
        send_font = QtGui.QFont(family, 11, QtGui.QFont.Weight.Medium)
        send_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.btn_send.setFont(send_font)

        # Status chip & labels (medium)
        label_font = QtGui.QFont(family, 10, QtGui.QFont.Weight.Medium)
        label_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.status_chip.setFont(label_font)
        self.lbl_status.setFont(label_font)

        # Assistant round button (semibold bigger)
        assistant_font = QtGui.QFont(family, 18, QtGui.QFont.Weight.DemiBold)
        assistant_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.btn_assistant.setFont(assistant_font)

        # Chat view text
        chat_font = QtGui.QFont(family, 12, QtGui.QFont.Weight.Normal)
        chat_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.chat_view.setFont(chat_font)

        # Input line
        edit_font = QtGui.QFont(family, 11, QtGui.QFont.Weight.Normal)
        edit_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.chat_edit.setFont(edit_font)

        # Conversation search
        search_font = QtGui.QFont(family, 9, QtGui.QFont.Weight.Normal)
        self.conv_search.setFont(search_font)

    # ---------- Header & chat rendering ----------

    def _make_header_widget(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.avatar_label = QtWidgets.QLabel()
        self.avatar_label.setFixedSize(32, 32)
        self.avatar_label.setAlignment(QtCore.Qt.AlignCenter)
        if os.path.exists(LOGO_PATH):
            pix = QtGui.QPixmap(LOGO_PATH).scaled(
                32,
                32,
                QtCore.Qt.KeepAspectRatioByExpanding,
                QtCore.Qt.SmoothTransformation,
            )
            self.avatar_label.setPixmap(pix)
        else:
            self.avatar_label.setText("A")

        title_col = QtWidgets.QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(0)
        self.header_title = QtWidgets.QLabel("Cuby — Less Type, More Talk")
        self.header_subtitle = QtWidgets.QLabel("Your bilingual real-time AI companion")
        title_col.addWidget(self.header_title)
        title_col.addWidget(self.header_subtitle)

        lay.addWidget(self.avatar_label)
        lay.addLayout(title_col)
        lay.addStretch()

        self.status_chip = QtWidgets.QLabel("READY")
        self.status_chip.setFixedWidth(100)
        self.status_chip.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.status_chip)
        return w

    def _format_time(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _append_spacer(self):
        self.chat_view.append("<div style='height:10px'></div>")

    @QtCore.Slot(str)
    def _append_chat_user(self, text: str):
        """
        User messages: RIGHT side
        """
        user_bg, user_fg, bot_bg, bot_fg, system_fg = bubble_colors(self._dark)
        esc = html.escape(text).replace("\n", "<br>")
        t = self._format_time()

        bubble = (
            f"<div style='margin:12px 0; text-align:right;'>"
            f"<div style='display:inline-block; padding:10px 13px; "
            f"border-radius:16px; background:{user_bg}; color:{user_fg}; "
            f"max-width:70%; text-align:left;'>"
            f"<b>You</b><br>{esc}</div>"
            f"<div style='font-size:11px; opacity:0.75; margin-top:4px;'>{t}</div>"
            f"</div>"
        )
        self.chat_view.append(bubble)
        self._append_spacer()
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    @QtCore.Slot(str)
    def _append_chat_bot(self, text: str):
        """
        Cuby messages: LEFT side
        """
        user_bg, user_fg, bot_bg, bot_fg, system_fg = bubble_colors(self._dark)
        esc = html.escape(text).replace("\n", "<br>")
        t = self._format_time()

        bubble = (
            f"<div style='margin:12px 0; text-align:left;'>"
            f"<div style='display:inline-block; padding:10px 13px; "
            f"border-radius:16px; background:{bot_bg}; color:{bot_fg}; "
            f"max-width:70%; text-align:left;'>"
            f"<b>Cuby</b><br>{esc}</div>"
            f"<div style='font-size:11px; opacity:0.75; margin-top:4px;'>{t}</div>"
            f"</div>"
        )
        self.chat_view.append(bubble)
        self._append_spacer()
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    @QtCore.Slot(str)
    def _append_chat_system(self, text: str):
        user_bg, user_fg, bot_bg, bot_fg, system_fg = bubble_colors(self._dark)
        esc = html.escape(text).replace("\n", "<br>")
        block = (
            f"<div style='margin:10px 0; text-align:center;'>"
            f"<span style='opacity:0.8; font-size:12px; color:{system_fg};'><i>{esc}</i></span>"
            f"</div>"
        )
        self.chat_view.append(block)
        self._append_spacer()
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    # ---------- Logging ----------

    @QtCore.Slot(str)
    def _log(self, text: str):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

    # ---------- Status chip & avatar ----------

    def _set_status_mode(self, mode: str):
        """Internal: must be called ONLY from the UI thread."""
        self._status_mode = mode
        bg = {
            "ready": CUBY_ACCENT,
            "listening": CUBY_ACCENT,
            "thinking": "#f59e0b",
            "speaking": "#22c55e",
            "stopped": "rgba(148,163,184,0.6)",
        }.get(mode, CUBY_ACCENT)
        txt = mode.upper()
        self.status_chip.setText(txt)
        self.status_chip.setStyleSheet(
            f"""
            QLabel {{
                padding: 4px 10px;
                border-radius: 999px;
                background: {bg};
                color: #fff;
                font-weight:700;
                font-size: 11px;
            }}
        """
        )

        if mode == "speaking":
            if not self._avatar_pulse_timer.isActive():
                self._avatar_pulse_on = False
                self._avatar_pulse_timer.start()
        else:
            if self._avatar_pulse_timer.isActive():
                self._avatar_pulse_timer.stop()
            self._apply_avatar_style()

    def _apply_avatar_style(self):
        if self._dark:
            fg = "#ffffff"
            bg = "rgba(255,255,255,0.06)"
        else:
            fg = "#111827"
            bg = "rgba(0,0,0,0.06)"
        self.avatar_label.setStyleSheet(
            f"""
            QLabel {{
                border-radius: 16px;
                background: {bg};
                color: {fg};
                font-weight: 800;
            }}
        """
        )

    def _avatar_pulse_step(self):
        if self._status_mode != "speaking":
            self._avatar_pulse_timer.stop()
            return
        self._avatar_pulse_on = not self._avatar_pulse_on
        border_alpha = 200 if self._avatar_pulse_on else 80
        if self._dark:
            fg = "#ffffff"
            bg = "rgba(255,255,255,0.06)"
        else:
            fg = "#111827"
            bg = "rgba(0,0,0,0.06)"
        self.avatar_label.setStyleSheet(
            f"""
            QLabel {{
                border-radius: 16px;
                background: {bg};
                color: {fg};
                font-weight: 800;
                border: 2px solid rgba(120,107,255,{border_alpha/255.0});
            }}
        """
        )

    # ---------- Client callbacks (cross-thread adapters) ----------

    def _on_transcript_message(self, message: str):
        QtCore.QMetaObject.invokeMethod(
            self,
            "_append_chat_bot",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, message),
        )
        self._add_message_to_conversation("assistant", message)
        self._ensure_conversation_title_from_text(message)

    def _on_server_error(self, err: str):
        QtCore.QMetaObject.invokeMethod(
            self,
            "_log",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, f"[ServerError] {err}"),
        )

    def _on_status(self, s: str):
        QtCore.QMetaObject.invokeMethod(
            self,
            "_log",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, s),
        )

    def _on_ws_state(self, connected: bool):
        """
        Called from RealtimeClient thread → forward to UI thread.
        """
        QtCore.QMetaObject.invokeMethod(
            self,
            "_handle_ws_state",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(bool, connected),
        )

    @QtCore.Slot(bool)
    def _handle_ws_state(self, connected: bool):
        text = "Connected" if connected and self._assistant_running else "Stopped"
        self.lbl_status.setText(text)
        if self._assistant_running and connected:
            self._set_status_mode("listening")
        else:
            self._set_status_mode("stopped")

    def _on_audio_level_from_client(self, lvl: float):
        """
        Called from RealtimeClient thread → forward to UI thread.
        """
        QtCore.QMetaObject.invokeMethod(
            self,
            "_handle_audio_level",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(float, lvl),
        )

    @QtCore.Slot(float)
    def _handle_audio_level(self, lvl: float):
        """
        Runs on UI thread: safe to touch widgets & QTimer here.
        """
        self.wave.set_amplitude(lvl)
        if not self._assistant_running:
            return
        if lvl > 0.02:
            self._silence_ticks = 0
            if self._status_mode != "speaking":
                self._set_status_mode("speaking")
        else:
            self._silence_ticks += 1
            if self._silence_ticks > 8 and self._status_mode == "speaking":
                self._set_status_mode("listening")

    # ---------- Conversation handling ----------

    def _initialize_conversations(self):
        convs = self.conv_manager.list_conversations()
        if not convs:
            conv = self.conv_manager.create_conversation("New Chat")
            convs = [conv]

        self.conv_list.clear()
        self._sidebar_widgets.clear()

        for conv in convs:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, conv.id)
            item.setSizeHint(QtCore.QSize(220, 56))
            self.conv_list.addItem(item)

            subtitle = last_snippet(conv.messages)
            w = SidebarItemWidget(
                conv.title or "New Chat", subtitle, active=False, dark=self._dark
            )
            w.set_icon_from_messages(conv.messages)

            # hook delete signal (to be implemented in SidebarItemWidget)
            try:
                w.deleteRequested.connect(
                    lambda cid=conv.id: self._request_delete_conversation(cid)
                )
            except AttributeError:
                # اگر هنوز deleteRequested توی SidebarItemWidget نباشه، کرش نکن
                pass

            self.conv_list.setItemWidget(item, w)
            self._sidebar_widgets[conv.id] = w

        if self.conv_list.count() > 0:
            self.conv_list.setCurrentRow(0)
        else:
            self._current_conv_id = None
            self.chat_view.clear()
            self._append_chat_system("No conversations. Create a new one.")

    def _refresh_sidebar_item(self, conv_id: str):
        conv = self.conv_manager.get(conv_id)
        if not conv:
            return
        w = self._sidebar_widgets.get(conv_id)
        if not w:
            return
        w.set_title(conv.title or "New Chat")
        w.set_subtitle(last_snippet(conv.messages))
        w.set_icon_from_messages(conv.messages)
        w.set_dark(self._dark)

    def _mark_active_sidebar(self, conv_id: str):
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            cid = item.data(QtCore.Qt.ItemDataRole.UserRole)
            w = self.conv_list.itemWidget(item)
            if isinstance(w, SidebarItemWidget):
                w.set_active(cid == conv_id)

    def _current_conversation(self):
        if not self._current_conv_id:
            return None
        return self.conv_manager.get(self._current_conv_id)

    def _recompute_instructions_for_current_conv(self):
        """
        Base instructions + conversation memory (no company knowledge).
        Company knowledge برای هر سوال جداگانه (تایپی/صوتی) اضافه می‌شود.
        """
        conv = self._current_conversation()
        if not conv or not conv.messages:
            self._instructions = self._base_instructions
        else:
            memory = self.conv_manager.build_memory_snippet(
                conv.id, max_messages=10
            )
            if memory:
                self._instructions = (
                    self._base_instructions + "\n\nConversation so far:\n" + memory
                )
            else:
                self._instructions = self._base_instructions
        self.client.set_instructions(self._instructions)

    def _load_conversation_into_view(self, conv_id: str):
        self._current_conv_id = conv_id
        self.chat_view.clear()
        conv = self.conv_manager.get(conv_id)
        if not conv:
            self._append_chat_system("Conversation not found.")
            return

        for m in conv.messages:
            if m.role == "user":
                self._append_chat_user(m.text)
            elif m.role == "assistant":
                self._append_chat_bot(m.text)
            else:
                self._append_chat_system(m.text)

        self._recompute_instructions_for_current_conv()
        self._mark_active_sidebar(conv_id)
        self._append_chat_system(f"Loaded conversation: {conv.title}")

    def _add_message_to_conversation(self, role: str, text: str):
        if not self._current_conv_id:
            return
        self.conv_manager.add_message(self._current_conv_id, role, text)
        self._refresh_sidebar_item(self._current_conv_id)

    def _ensure_conversation_title_from_text(self, text: str):
        conv = self._current_conversation()
        if not conv:
            return
        title_now = (conv.title or "").strip()
        if title_now and title_now.lower() != "new chat":
            return
        title = elide_middle(text, 40)
        if not title:
            return
        conv_id = conv.id
        self.conv_manager.rename_conversation(conv_id, title)
        self._refresh_sidebar_item(conv_id)

    @QtCore.Slot()
    def _create_new_conversation(self):
        conv = self.conv_manager.create_conversation("New Chat")
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.ItemDataRole.UserRole, conv.id)
        item.setSizeHint(QtCore.QSize(220, 56))
        self.conv_list.addItem(item)

        w = SidebarItemWidget("New Chat", "", active=False, dark=self._dark)

        try:
            w.deleteRequested.connect(
                lambda cid=conv.id: self._request_delete_conversation(cid)
            )
        except AttributeError:
            pass

        self.conv_list.setItemWidget(item, w)
        self._sidebar_widgets[conv.id] = w
        self.conv_list.setCurrentItem(item)

    @QtCore.Slot(QtWidgets.QListWidgetItem, QtWidgets.QListWidgetItem)
    def _on_conversation_changed(self, current, previous):
        if not current:
            return
        conv_id = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if not conv_id:
            return
        if self._assistant_running:
            self._append_chat_system(
                "Switching chat. Restarting Cuby for new context..."
            )
            self.btn_assistant.setChecked(False)
            self._toggle_assistant()
            QtCore.QTimer.singleShot(
                900,
                lambda: (
                    self.btn_assistant.setChecked(True),
                    self._toggle_assistant(),
                ),
            )
        self._load_conversation_into_view(conv_id)

    @QtCore.Slot(QtWidgets.QListWidgetItem)
    def _rename_conversation_dialog(self, item):
        conv_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not conv_id:
            return
        conv = self.conv_manager.get(conv_id)
        if not conv:
            return
        new_title, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Conversation",
            "Title:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            conv.title or "",
        )
        if not ok:
            return
        new_title = (new_title or "").strip()
        if not new_title:
            return
        self.conv_manager.rename_conversation(conv_id, new_title)
        self._refresh_sidebar_item(conv_id)
        self._append_chat_system(f"Conversation renamed to: {new_title}")

    # ---------- Conversation delete ----------

    def _request_delete_conversation(self, conv_id: str):
        conv = self.conv_manager.get(conv_id)
        if not conv:
            return
        title = conv.title or "this conversation"
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Conversation",
            f'Are you sure you want to delete "{title}"?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        # Delete from manager
        try:
            self.conv_manager.delete_conversation(conv_id)
        except AttributeError:
            # اگر هنوز delete_conversation تو ConversationManager نباشه، فقط از UI حذف کن
            pass

        # Remove from list widget
        row_to_select = 0
        removed_current = self._current_conv_id == conv_id
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            cid = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if cid == conv_id:
                row_to_select = max(0, i - 1)
                self.conv_list.takeItem(i)
                break

        # Remove from sidebar widget map
        self._sidebar_widgets.pop(conv_id, None)

        # If we deleted the active conversation, switch to another or create new
        if removed_current:
            if self.conv_list.count() > 0:
                self.conv_list.setCurrentRow(row_to_select)
            else:
                self._current_conv_id = None
                self.chat_view.clear()
                self._append_chat_system("Conversation deleted.")
                self._create_new_conversation()
        else:
            self._append_chat_system(f'Conversation "{title}" deleted.')

    # ---------- Company knowledge integration ----------

    def _build_company_context(self, question: str) -> str:
        """
        If company knowledge is enabled and store has chunks, build
        a context snippet for the current question.
        """
        if not self._knowledge_enabled:
            return ""
        try:
            ctx = self.company_knowledge.build_context_for_query(question, top_k=5)
        except Exception as e:
            self._append_chat_system(f"Error while using company knowledge: {e}")
            return ""
        return ctx or ""

    def _instructions_for_question(self, question: str) -> str:
        """
        Base + conversation memory + (optionally) company knowledge
        specific to this question (text or voice).
        """
        conv = self._current_conversation()
        memory = ""
        if conv and conv.messages:
            memory = (
                self.conv_manager.build_memory_snippet(conv.id, max_messages=10) or ""
            )

        base = self._base_instructions
        if memory:
            base += "\n\nConversation so far:\n" + memory

        company_ctx = self._build_company_context(question)
        if company_ctx:
            base += (
                "\n\nCompany knowledge (internal docs):\n"
                f"{company_ctx}\n\n"
                "Use only this information to answer questions about the company. "
                "If the answer is not covered in these docs, explicitly say that "
                "you do not know based on the company documents."
            )
        return base

    # ---------- User voice transcript (for audio RAG) ----------

    def _on_user_transcript_from_client(self, text: str):
        """
        This is called from background thread (RealtimeClient).
        Route to UI thread via QMetaObject.
        """
        QtCore.QMetaObject.invokeMethod(
            self,
            "_handle_user_voice_question",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, text),
        )

    @QtCore.Slot(str)
    def _handle_user_voice_question(self, text: str):
        """
        Handle a user query that came from microphone:
          - show in chat as user bubble
          - store in conversation
          - build instructions (memory + RAG)
          - request model response (response.create)
        """
        text = (text or "").strip()
        if not text:
            return
        if not self._assistant_running:
            return

        self._append_chat_user(text)
        self._add_message_to_conversation("user", text)
        self._ensure_conversation_title_from_text(text)

        instructions = self._instructions_for_question(text)
        self.client.set_instructions(instructions)

        self._set_status_mode("thinking")
        self.client.request_response()

    # ---------- Typed messages ----------

    @QtCore.Slot()
    def _send_typed_message(self):
        text = self.chat_edit.text().strip()
        if not text:
            return
        if not self._assistant_running:
            self._append_chat_system(
                "Cuby is stopped. Press Start, then try again."
            )
            return

        self._append_chat_user(text)
        self._add_message_to_conversation("user", text)
        self._ensure_conversation_title_from_text(text)

        instructions = self._instructions_for_question(text)
        self.client.set_instructions(instructions)

        self.client.submit_text(text)
        self.chat_edit.clear()
        self._set_status_mode("thinking")

    # ---------- Mic / Speaker toggles ----------

    @QtCore.Slot(bool)
    def _toggle_mic(self, on: bool):
        self.client.toggle_mic(on)
        self.lbl_mic_hint.setVisible(not on)

    @QtCore.Slot(bool)
    def _toggle_speaker(self, on: bool):
        self.client.toggle_speaker(on)
        self.lbl_speaker_hint.setVisible(not on)

    # ---------- Assistant start/stop ----------

    @QtCore.Slot()
    def _toggle_assistant(self):
        if self.btn_assistant.isChecked():
            # START
            if not self._api_key:
                self._append_chat_system(
                    "No OpenAI API key configured. Open Settings and enter your API key."
                )
                self.btn_assistant.setChecked(False)
                return

            self._assistant_running = True
            self.btn_assistant.setText("■")
            self.lbl_status.setText("Connecting...")
            self.wave.set_amplitude(0.0)
            self._recompute_instructions_for_current_conv()
            self.client.start()
            self._append_chat_system("Cuby آماده است، شروع کن به صحبت 🌙")
            self._set_status_mode("listening")
        else:
            # STOP
            self._assistant_running = False
            self.btn_assistant.setText("▶")
            self.client.stop()
            self.lbl_status.setText("Stopped")
            self.wave.set_amplitude(0.0)
            self._append_chat_system("Cuby stopped.")
            self._set_status_mode("stopped")

    # ---------- Settings dialog ----------

    @QtCore.Slot()
    def _open_settings(self):
        dlg = SettingsDialog(
            self,
            initial_instructions=self._base_instructions,
            initial_voice=self._voice,
            dark_mode=self._dark,
            initial_vad_threshold=self._vad_threshold,
            initial_vad_silence_ms=self._vad_silence_ms,
            initial_api_key=self._api_key or "",
            initial_knowledge_files=self._knowledge_files,
            initial_knowledge_enabled=self._knowledge_enabled,
        )
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            vals = dlg.values()
            self._base_instructions = vals["instructions"]
            self._voice = vals["voice"]
            self._dark = vals["dark"]
            self._vad_threshold = vals["vad_threshold"]
            self._vad_silence_ms = vals["vad_silence_ms"]

            new_key = vals["api_key"].strip()
            self._api_key = new_key

            self._knowledge_files = vals.get("knowledge_files", [])
            self._knowledge_enabled = bool(vals.get("knowledge_enabled", False))
            rebuild_knowledge = bool(vals.get("knowledge_rebuild", False))

            self._save_settings()

            self.client.set_voice(self._voice)
            self.client.set_vad_params(self._vad_threshold, self._vad_silence_ms)
            self.client.set_api_key(self._api_key or "")
            self._recompute_instructions_for_current_conv()

            has_key = bool(self._api_key)
            self.btn_assistant.setEnabled(has_key)
            if not has_key:
                self._append_chat_system(
                    "API key cleared. Cuby is disabled until you set a new OpenAI API key."
                )

            self._apply_theme(self._dark)

            if rebuild_knowledge:
                self._rebuild_company_knowledge()

            if self._assistant_running:
                self._append_chat_system(
                    "Restarting Cuby to apply new settings..."
                )
                self.btn_assistant.setChecked(False)
                self._toggle_assistant()
                if has_key:
                    QtCore.QTimer.singleShot(
                        1000,
                        lambda: (
                            self.btn_assistant.setChecked(True),
                            self._toggle_assistant(),
                        ),
                    )
            else:
                self._append_chat_system(
                    "Settings updated. Start Cuby to apply changes."
                )

    def _rebuild_company_knowledge(self):
        """
        Build / rebuild company knowledge from selected files, with
        a progress dialog and success message.
        """
        if not self._knowledge_files:
            self._append_chat_system(
                "No company documents selected. Nothing to rebuild."
            )
            return
        if not self._api_key:
            self._append_chat_system(
                "Cannot rebuild company knowledge: no OpenAI API key configured."
            )
            return

        files = list(self._knowledge_files)
        total = len(files)

        progress = QtWidgets.QProgressDialog(
            "Building company knowledge...", "Cancel", 0, total, self
        )
        progress.setWindowTitle("Building company knowledge")
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(True)
        progress.setAutoReset(True)

        self._append_chat_system(
            "Building company knowledge from selected documents…"
        )

        try:
            # Reset store by creating a new instance
            self.company_knowledge = CompanyKnowledge(KNOWLEDGE_STORE_PATH)

            for i, path in enumerate(files, start=1):
                self.company_knowledge.add_files([path])
                progress.setValue(i)
                QtWidgets.QApplication.processEvents()
                if progress.wasCanceled():
                    raise Exception("Rebuild cancelled by user.")

            self._append_chat_system(
                "Company knowledge updated successfully. Cuby will now use it for text and voice questions."
            )
            QtWidgets.QMessageBox.information(
                self,
                "Company Knowledge",
                "Company knowledge was built successfully from the selected documents.",
            )

        except Exception as e:
            progress.close()
            msg = f"Failed to build company knowledge: {e}"
            self._append_chat_system(msg)
            QtWidgets.QMessageBox.critical(
                self,
                "Company Knowledge",
                msg,
            )

    # ---------- Sidebar drawer + search ----------

    @QtCore.Slot()
    def _toggle_sidebar_collapsed(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        if self._sidebar_collapsed:
            # collapse
            self.sidebar_card.setMinimumWidth(60)
            self.sidebar_card.setMaximumWidth(72)
            self.conv_header.hide()
            self.conv_search.hide()
            self.conv_list.hide()
            self.btn_new_chat.hide()
            self.sidebar_collapsed_panel.show()
            self.btn_sidebar_toggle.setText("⟩")
        else:
            # expand
            self.sidebar_card.setMinimumWidth(240)
            self.sidebar_card.setMaximumWidth(300)
            self.conv_header.show()
            self.conv_search.show()
            self.conv_list.show()
            self.btn_new_chat.show()
            self.sidebar_collapsed_panel.hide()
            self.btn_sidebar_toggle.setText("⟨")

    @QtCore.Slot(str)
    def _filter_conversations(self, text: str):
        q = (text or "").strip().lower()
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            cid = item.data(QtCore.Qt.ItemDataRole.UserRole)
            conv = self.conv_manager.get(cid)
            if not conv:
                item.setHidden(False)
                continue
            title = (conv.title or "").lower()
            subtitle = (last_snippet(conv.messages) or "").lower()
            visible = not q or (q in title) or (q in subtitle)
            item.setHidden(not visible)

    @QtCore.Slot()
    def _collapsed_search_clicked(self):
        """
        When sidebar is collapsed and user clicks search icon.
        We expand the sidebar and open a small input dialog.
        """
        if self._sidebar_collapsed:
            self._toggle_sidebar_collapsed()

        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Search Conversations",
            "Search text:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            "",
        )
        if ok:
            self.conv_search.setText(text)

    # ---------- Theme toggle ----------

    @QtCore.Slot()
    def _toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme(self._dark)

    # ---------- Theme apply ----------

    def _apply_theme(self, dark: bool):
        apply_app_palette(dark)
        self._dark = dark

        for card in (self.sidebar_card, self.chat_card, self.voice_card):
            card.apply_style(dark)

        title_color = "#ffffff" if dark else "#111827"
        subtitle_color = (
            "rgba(255,255,255,0.75)" if dark else "rgba(17,24,39,0.75)"
        )
        self.header_title.setStyleSheet(
            f"font-weight:800; font-size:16px; letter-spacing:.2px; color:{title_color};"
        )
        self.header_subtitle.setStyleSheet(
            f"font-size:11px; color:{subtitle_color};"
        )

        conv_header_color = "#f9fafb" if dark else "#111827"
        self.conv_header.setStyleSheet(
            f"font-weight:800; letter-spacing:.3px; color:{conv_header_color};"
        )

        self._apply_avatar_style()

        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            w = self.conv_list.itemWidget(item)
            if isinstance(w, SidebarItemWidget):
                w.set_dark(dark)

        conv = self._current_conversation()
        if conv:
            self.chat_view.clear()
            for m in conv.messages:
                if m.role == "user":
                    self._append_chat_user(m.text)
                elif m.role == "assistant":
                    self._append_chat_bot(m.text)
                else:
                    self._append_chat_system(m.text)

    # ---------- Close ----------

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            self.client.stop()
        except Exception:
            pass
        super().closeEvent(event)
