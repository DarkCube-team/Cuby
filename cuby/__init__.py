# cuby/__init__.py
"""
Cuby desktop assistant package.

This package contains:
- RealtimeClient: a high-level wrapper around the OpenAI Realtime WebSocket API
- WaveformBars: a custom Qt widget for audio visualization
"""

from .realtime_client import RealtimeClient
from .visuals import WaveformBars

__all__ = ["RealtimeClient", "WaveformBars"]
