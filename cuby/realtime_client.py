# cuby/realtime_client.py
import os
import asyncio
import json
import base64
import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

# Try to support both new and old versions of `websockets`
try:
    from websockets.asyncio.client import connect as ws_connect  # type: ignore
    USE_ADDITIONAL_HEADERS = True
except ImportError:
    import websockets  # type: ignore
    ws_connect = websockets.connect
    USE_ADDITIONAL_HEADERS = False

from websockets.exceptions import ConnectionClosedError  # type: ignore

DEFAULT_MODEL = "gpt-4o-realtime-preview"


class RealtimeClient:
    """
    Background client for OpenAI Realtime API:
      - Streams microphone PCM16 audio to WebSocket
      - Receives PCM16 audio and plays it on speakers
      - Emits final assistant messages (text) via callbacks
      - Supports sending text messages (user typing)
      - Supports user voice transcription for RAG (conversation.item.input_audio_transcription.completed)
      - Automatically reconnects until .stop() is called
    """

    def __init__(
        self,
        api_key: str,
        model: str = None,
        instructions: str = None,
        voice: str = "alloy",
        rate: int = 24000,
        chunk: int = 1024,
        channels: int = 1,
        vad_threshold: float = 0.95,
        vad_silence_ms: int = 1600,
    ):
        self.api_key = api_key
        self.model = model or os.getenv("OPENAI_REALTIME_MODEL", DEFAULT_MODEL)
        self.instructions = instructions or (
            "You are an intelligent, fast voice assistant named Cuby. "
            "Speak primarily in Persian (Farsi) when user speaks in Persian; "
            "otherwise, switch to the user's language. Keep answers concise "
            "unless explicitly asked for details."
        )
        self.voice = voice

        self.ws_url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        self.ws_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        # Audio config
        self.rate = rate
        self.chunk = chunk
        self.channels = channels
        self.dtype = "int16"

        # Server VAD parameters (exposed in Settings)
        self.vad_threshold = float(vad_threshold)
        self.vad_silence_ms = int(vad_silence_ms)

        # Thread / loop state
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_flag = threading.Event()
        self._mic_enabled = True
        self._speaker_enabled = True
        self._connected = False

        # Audio streams (created inside event loop thread)
        self._in_stream: Optional[sd.RawInputStream] = None
        self._out_stream: Optional[sd.RawOutputStream] = None

        # Current WebSocket (used by submit_text / shutdown)
        self._current_ws = None

        # Assistant speech flag (to avoid feeding model its own voice)
        self._assistant_speaking = False
        # For echo-protection cooldown
        self._last_assistant_audio_time: float = 0.0
        self._assistant_cooldown_sec: float = 0.8

        # Buffers for assistant text
        self._assistant_text_buffer: str = ""
        self._assistant_audio_buffer: str = ""

        # Callbacks (UI can assign these)
        self.on_event_text: Optional[Callable[[str], None]] = None        # final assistant text
        self.on_server_error: Optional[Callable[[str], None]] = None      # error log
        self.on_status: Optional[Callable[[str], None]] = None            # status log
        self.on_ws_state: Optional[Callable[[bool], None]] = None         # True/False (connected)
        self.on_audio_level: Optional[Callable[[float], None]] = None     # 0..1 RMS amplitude
        self.on_user_transcript: Optional[Callable[[str], None]] = None   # user voice transcript (for RAG)

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    def start(self):
        """Start the background thread with its own asyncio event loop."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Ask the reconnect loop to stop and close WS so sender/receiver exit.
        Also proactively close audio streams to unblock blocking reads.
        """
        self._stop_flag.set()

        # Close websocket to unblock ws.recv()/ws.send()
        if self._loop and self._current_ws is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._current_ws.close(), self._loop)
            except Exception:
                pass

        # Close audio streams to unblock sounddevice.read/write.
        try:
            if self._in_stream is not None:
                try:
                    self._in_stream.stop()
                except Exception:
                    pass
                try:
                    self._in_stream.close()
                except Exception:
                    pass
                self._in_stream = None
        except Exception:
            pass

        try:
            if self._out_stream is not None:
                try:
                    self._out_stream.stop()
                except Exception:
                    pass
                try:
                    self._out_stream.close()
                except Exception:
                    pass
                self._out_stream = None
        except Exception:
            pass

        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=3.0)
            except Exception:
                pass
        self._thread = None

    def set_instructions(self, text: str):
        """
        Update system instructions.

        - Always updates the local `self.instructions`
        - If a Realtime session is currently active, also sends
          a `session.update` event so the new instructions (including
          company RAG context) apply immediately.
        """
        if not text:
            return

        # 1) local copy for future sessions
        self.instructions = text

        # 2) live session update if connected
        if self._loop and self._connected and self._current_ws is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._send_session_update(self._current_ws),
                    self._loop,
                )
            except Exception:
                # اگر اینجا خطایی شد، سشن بعدی اینستراکشن جدید رو خواهد گرفت
                pass

    def set_voice(self, voice: str):
        """Update voice name for future WebSocket sessions."""
        if voice:
            self.voice = voice

    def set_vad_params(self, threshold: Optional[float] = None, silence_ms: Optional[int] = None):
        """
        Update server VAD parameters for future sessions.
        Take effect on the next WebSocket (or next session.update).
        """
        if threshold is not None:
            self.vad_threshold = max(0.0, min(1.0, float(threshold)))
        if silence_ms is not None:
            self.vad_silence_ms = max(100, int(silence_ms))

        if self.on_status:
            self.on_status(
                f"VAD updated: threshold={self.vad_threshold:.2f}, "
                f"silence={self.vad_silence_ms}ms"
            )

        # اگر سشن فعالی هست، یه session.update بفرستیم
        if self._loop and self._connected and self._current_ws is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._send_session_update(self._current_ws),
                    self._loop,
                )
            except Exception:
                pass

    def set_api_key(self, api_key: str):
        """Update API key (used for next WebSocket connections)."""
        self.api_key = api_key or ""
        self.ws_headers["Authorization"] = f"Bearer {self.api_key}"

    def toggle_mic(self, enabled: bool):
        """Enable / disable streaming microphone audio to the model."""
        self._mic_enabled = enabled
        if self.on_status:
            self.on_status(f"Microphone {'enabled' if enabled else 'muted'}.")

    def toggle_speaker(self, enabled: bool):
        """Enable / disable playback of model audio on speakers."""
        self._speaker_enabled = enabled
        if self.on_status:
            self.on_status(f"Speaker {'enabled' if enabled else 'muted'}.")

    # --- text sending API (typed) ---

    async def _send_user_text(self, ws, text: str):
        """
        Send user-typed text into the Realtime session using the
        conversation.item.create + response.create pattern.
        """
        try:
            # 1) Add a user message item to the conversation
            item_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": text},
                    ],
                },
            }
            await ws.send(json.dumps(item_event))

            # 2) Ask the model to generate a response (audio + text)
            resp_event = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                },
            }
            await ws.send(json.dumps(resp_event))

        except Exception as e:
            if self._stop_flag.is_set():
                return
            if self.on_server_error:
                self.on_server_error(f"send_user_text error: {e}")

    def submit_text(self, text: str):
        """Thread-safe: schedule _send_user_text on the Realtime loop if connected."""
        if not text or not self._loop or not self._connected:
            return
        ws = self._current_ws
        if ws is None:
            return
        asyncio.run_coroutine_threadsafe(self._send_user_text(ws, text), self._loop)

    # --- voice response trigger (for audio RAG) ---

    async def _send_response_create(self, ws):
        """
        Create a response for the *current conversation*.
        Used in voice mode after we have the user transcript and
        have updated instructions with RAG context.
        """
        try:
            resp_event = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                },
            }
            await ws.send(json.dumps(resp_event))
        except Exception as e:
            if self._stop_flag.is_set():
                return
            if self.on_server_error:
                self.on_server_error(f"request_response error: {e}")

    def request_response(self):
        """
        Thread-safe:
        Used by UI (window.py) after receiving a user voice transcript and
        updating instructions via set_instructions().
        """
        if not self._loop or not self._connected or self._current_ws is None:
            return
        asyncio.run_coroutine_threadsafe(self._send_response_create(self._current_ws), self._loop)

    # ------------------------------------------------------------------
    # Thread / loop internals
    # ------------------------------------------------------------------

    def _thread_main(self):
        """Create an event loop and run the reconnect loop inside the thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._reconnect_loop())
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _reconnect_loop(self):
        """Keep reconnecting until stop_flag is set."""
        while not self._stop_flag.is_set():
            try:
                await self._run_session()
            except ConnectionClosedError as e:
                if self._stop_flag.is_set():
                    break
                if self.on_status:
                    self.on_status(f"WebSocket closed: {e}. Reconnecting in 3s...")
                for _ in range(30):
                    if self._stop_flag.is_set():
                        break
                    await asyncio.sleep(0.1)
            except Exception as e:
                if self._stop_flag.is_set():
                    break
                if self.on_server_error:
                    self.on_server_error(f"Unexpected error: {e}")
                for _ in range(50):
                    if self._stop_flag.is_set():
                        break
                    await asyncio.sleep(0.1)
            else:
                if not self._stop_flag.is_set():
                    await asyncio.sleep(0.3)

    async def _run_session(self):
        """Open WebSocket + audio streams, and run sender/receiver until closed."""
        if self._stop_flag.is_set():
            return

        if self.on_status:
            self.on_status(f"Connecting to Realtime ({self.model})...")

        self._current_ws = None
        self._assistant_speaking = False
        self._assistant_text_buffer = ""
        self._assistant_audio_buffer = ""
        self._last_assistant_audio_time = 0.0

        # --- Open audio streams safely ---
        try:
            self._in_stream = sd.RawInputStream(
                samplerate=self.rate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=self.chunk,
            )
            self._out_stream = sd.RawOutputStream(
                samplerate=self.rate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=self.chunk,
            )
            self._in_stream.start()
            self._out_stream.start()
        except Exception as e:
            if self.on_server_error:
                self.on_server_error(f"Failed to open audio streams: {e}")
            try:
                if self._in_stream:
                    try:
                        self._in_stream.stop()
                    except Exception:
                        pass
                    try:
                        self._in_stream.close()
                    except Exception:
                        pass
            except Exception:
                pass
            self._in_stream = None

            try:
                if self._out_stream:
                    try:
                        self._out_stream.stop()
                    except Exception:
                        pass
                    try:
                        self._out_stream.close()
                    except Exception:
                        pass
            except Exception:
                pass
            self._out_stream = None

            if self.on_status:
                self.on_status("Audio streams closed due to init error.")
            return

        # Build kwargs depending on websockets version
        conn_kwargs = dict(ping_interval=30, ping_timeout=60)
        if USE_ADDITIONAL_HEADERS:
            conn_kwargs["additional_headers"] = self.ws_headers
        else:
            conn_kwargs["extra_headers"] = self.ws_headers

        try:
            async with ws_connect(self.ws_url, **conn_kwargs) as ws:
                self._current_ws = ws
                self._connected = True
                if self.on_ws_state:
                    self.on_ws_state(True)
                if self.on_status:
                    self.on_status("Connected. You can start speaking.")

                # Send initial session.update
                await self._send_session_update(ws)

                sender = asyncio.create_task(self._audio_sender(ws))
                receiver = asyncio.create_task(self._audio_receiver(ws))
                await asyncio.gather(sender, receiver)
        finally:
            self._current_ws = None
            self._connected = False
            if self.on_ws_state:
                self.on_ws_state(False)

            try:
                if self._in_stream:
                    try:
                        self._in_stream.stop()
                    except Exception:
                        pass
                    try:
                        self._in_stream.close()
                    except Exception:
                        pass
            except Exception:
                pass
            self._in_stream = None

            try:
                if self._out_stream:
                    try:
                        self._out_stream.stop()
                    except Exception:
                        pass
                    try:
                        self._out_stream.close()
                    except Exception:
                        pass
            except Exception:
                pass
            self._out_stream = None

            if self.on_status:
                self.on_status("Audio streams closed.")

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    async def _send_session_update(self, ws):
        """
        Send session.update with instructions, modalities, voice, VAD settings,
        and input audio transcription enabled (for voice RAG).
        """
        payload = {
            "type": "session.update",
            "session": {
                "model": self.model,
                "instructions": self.instructions,
                "modalities": ["text", "audio"],
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": float(self.vad_threshold),
                    "silence_duration_ms": int(self.vad_silence_ms),
                    # IMPORTANT: we create the response manually after RAG
                    "create_response": False,
                },
                # Enable input transcription so we can get
                # conversation.item.input_audio_transcription.completed
                "input_audio_transcription": {
                    "model": "gpt-4o-mini-transcribe"
                },
            },
        }
        await ws.send(json.dumps(payload))
        if self.on_status:
            self.on_status(
                f"session.update sent (VAD threshold={self.vad_threshold:.2f}, "
                f"silence={self.vad_silence_ms}ms)."
            )

    async def _audio_sender(self, ws):
        """Continuously read mic audio and send to server if mic is enabled."""
        if self.on_status:
            self.on_status("Mic sender started.")
        while not self._stop_flag.is_set():
            if self._in_stream is None:
                break

            try:
                data, overflowed = self._in_stream.read(self.chunk)
            except Exception as e:
                if self._stop_flag.is_set():
                    break
                if self.on_server_error:
                    self.on_server_error(f"Input stream error: {e}")
                break

            # 1) If mic is muted => don't send
            if not self._mic_enabled:
                await asyncio.sleep(0)
                continue

            # 2) If assistant is currently speaking => don't send (avoid feedback loop)
            if self._assistant_speaking:
                await asyncio.sleep(0)
                continue

            # 3) Cooldown after assistant speech to avoid echo
            if self._last_assistant_audio_time > 0.0:
                now = time.monotonic()
                if now - self._last_assistant_audio_time < self._assistant_cooldown_sec:
                    await asyncio.sleep(0)
                    continue

            # 4) Send audio to input buffer; server_vad handles turn detection
            audio_b64 = base64.b64encode(data).decode("ascii")
            msg = {"type": "input_audio_buffer.append", "audio": audio_b64}
            try:
                await ws.send(json.dumps(msg))
            except Exception as e:
                if self._stop_flag.is_set():
                    break
                if self.on_server_error:
                    self.on_server_error(f"Sender error: {e}")
                break

            await asyncio.sleep(0)

    async def _audio_receiver(self, ws):
        """
        Continuously receive events:
          - Play assistant audio chunks
          - Emit final assistant text
          - Emit user voice transcript (for RAG)
          - Emit audio level for visualizer
        """
        if self.on_status:
            self.on_status("Receiver started.")
        while not self._stop_flag.is_set():
            try:
                msg_str = await ws.recv()
            except Exception as e:
                if self._stop_flag.is_set():
                    break
                if self.on_server_error:
                    self.on_server_error(f"Receiver error: {e}")
                break

            msg = json.loads(msg_str)
            etype = msg.get("type")

            # --- Assistant audio stream ---
            if etype == "response.audio.delta":
                if not self._speaker_enabled:
                    continue
                b64 = msg.get("delta")
                if not b64:
                    continue
                raw = base64.b64decode(b64)

                self._assistant_speaking = True
                self._last_assistant_audio_time = time.monotonic()

                try:
                    if self._out_stream is not None:
                        self._out_stream.write(raw)
                except Exception:
                    if self._stop_flag.is_set():
                        break

                if self.on_audio_level:
                    try:
                        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                        if arr.size:
                            rms = float(np.sqrt(np.mean(np.square(arr))) / 32768.0)
                            level = min(1.0, rms * 4.0)
                            self.on_audio_level(level)
                    except Exception:
                        pass

            elif etype == "response.audio.done":
                self._assistant_speaking = False

            # --- Assistant audio transcript (what Cuby said) ---
            elif etype == "response.audio_transcript.delta":
                delta = msg.get("delta") or ""
                if delta:
                    self._assistant_audio_buffer += delta

            elif etype == "response.audio_transcript.done":
                if not self._assistant_text_buffer:
                    transcript = msg.get("transcript") or self._assistant_audio_buffer
                    if transcript and self.on_event_text:
                        self.on_event_text(transcript)
                self._assistant_audio_buffer = ""
                self._assistant_text_buffer = ""

            # --- Assistant text stream (modalities: ["text","audio"]) ---
            elif etype == "response.text.delta":
                delta = msg.get("delta") or ""
                if delta:
                    self._assistant_text_buffer += delta

            elif etype == "response.text.done":
                text = msg.get("text") or self._assistant_text_buffer
                if text and self.on_event_text:
                    self.on_event_text(text)
                self._assistant_text_buffer = ""
                self._assistant_audio_buffer = ""

            # --- USER voice transcription (for RAG pipeline) ---
            elif etype == "conversation.item.input_audio_transcription.completed":
                # This is the text of what the user said via mic
                transcript = msg.get("transcript") or ""
                if transcript and self.on_user_transcript:
                    self.on_user_transcript(transcript)

            # --- Errors ---
            elif etype == "error":
                err = msg.get("error") or {}
                code = err.get("code")
                if code == "conversation_already_has_active_response":
                    continue
                if self.on_server_error:
                    self.on_server_error(str(msg))
