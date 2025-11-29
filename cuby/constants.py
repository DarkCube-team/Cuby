import os

APP_NAME = "Cuby"

# Project base dir (parent of package folder)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Paths
LOGO_PATH = os.path.join(BASE_DIR, "assets", "cuby_logo.png")
DATA_DIR = os.path.join(BASE_DIR, "data")
CONV_PATH = os.path.join(DATA_DIR, "conversations.json")
LOG_PATH = os.path.join(DATA_DIR, "cuby.log")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
KNOWLEDGE_STORE_PATH = os.path.join(DATA_DIR, "company_knowledge.json")

# Theming
CUBY_ACCENT = "#786BFF"  # purple-blue
GLASS_BG_DARK = "rgba(30,30,35,0.55)"
GLASS_BG_LIGHT = "rgba(255,255,255,0.60)"
BORDER_RADIUS = 16

# Defaults
DEFAULT_INSTRUCTIONS = (
    "You are an intelligent, fast voice assistant named Cuby. "
    "Speak primarily in Persian (Farsi) when the user speaks in Persian; "
    "otherwise, switch to the user's language. Keep answers concise "
    "unless explicitly asked for details."
)
DEFAULT_VAD_THRESHOLD = 0.95
DEFAULT_VAD_SILENCE_MS = 1600
DEFAULT_VOICE = "alloy"
