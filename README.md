
# Cuby — An Uncapped Desktop AI Assistant 🎙️🧠

Cuby is a desktop assistant that lets you run advanced AI features from your own account—so you’re not boxed in by typical app-level limits on voice sessions, file uploads, or retrieval workflows.

> Built by DarkCube

---

## What Cuby Solves

Most AI chat apps (even paid plans) can impose practical caps on:
- Real-time voice sessions (time/usage limits)
- Document-based answering (file count/size limits)
- Customization (restricted system behavior)

Cuby turns those capabilities into a **personal workspace**:
- You connect once in Settings
- You control the assistant’s behavior via instructions
- You use features based on your own usage, not product plan boundaries

---

## Highlights

- **Real-time voice conversations** (low-latency speech-to-speech)
- **Company Knowledge (Local RAG)**  
  Add documents (PDF/DOCX/TXT/MD), retrieve relevant context, and answer grounded in your files.
- **Full customization via System Instructions**  
  Rename the assistant, change tone, enforce rules, pick any language, and create specialized “agents.”
- **Conversation management**  
  List, search, rename, delete, and continue chats.
- **Modern desktop UI**  
  Glassmorphism, dark/light theme, waveform visualizer, and a branded splash screen.

---

## How It Works (High-Level)

Cuby has three layers:
1. **UI (PySide6)** — the desktop interface, settings, and conversation view  
2. **Realtime Client** — streaming audio in/out + transcript events  
3. **Local Knowledge Layer (RAG)** — chunking + embeddings + top-k retrieval for grounded answers  

---

## Project Structure

```text
.
├── main.py
├── requirements.txt
├── assets/
│   ├── cuby_logo.png
│   ├── darkcube_logo.png
│   └── fonts/
│       ├── Vazirmatn-Regular.ttf
│       ├── Vazirmatn-Medium.ttf
│       ├── Vazirmatn-SemiBold.ttf
│       └── Vazirmatn-Bold.ttf
├── data/
│   ├── conversations.json
│   ├── settings.json
│   ├── company_knowledge.json
│   └── cuby.log
└── cuby/
    ├── __init__.py
    ├── window.py
    ├── splash.py
    ├── realtime_client.py
    ├── conversations.py
    ├── company_knowledge.py
    ├── widgets.py
    ├── theme.py
    ├── visuals.py
    └── constants.py


---

Requirements

Python 3.10+ (recommended)

Microphone + speakers



---

Installation

pip install -r requirements.txt


---

Configuration

Create a .env file next to main.py:

OPENAI_API_KEY=YOUR_KEY_HERE
OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview

You can also set these as OS environment variables.


---

Run

python main.py


---

Customization (System Instructions)

Cuby is instruction-driven:

Define identity (name/persona)

Set language(s)

Enforce strict rules (format, safety, style)

Build “task modes” (study assistant, legal helper, ops agent, etc.)


This means Cuby is not tied to any specific language—it follows what you define.


---

Company Knowledge (Local RAG)

Typical pipeline:

Chunking (sliding window), e.g. chunk_size=800 words and overlap=200

Embeddings via multilingual Sentence Transformers

Retrieval: top-k similar chunks

Response: model answers with retrieved context injected


Supported formats: txt, md, log, docx, pdf (depending on installed libraries).


---

Data Storage

Cuby stores everything locally:

data/conversations.json — conversations

data/settings.json — settings (may include credentials)

data/company_knowledge.json — RAG store (chunks + embeddings)

data/cuby.log — logs



---

Security Notes

If the repo is public:

Add data/ (or at least data/settings.json) to .gitignore

Prefer environment variables or .env for secrets


Example .gitignore lines:

data/
.env


---

Roadmap

[ ] Export conversations to Markdown/PDF

[ ] Multiple instruction profiles (“agents”)

[ ] Better RAG file management (status, rebuild timestamps, indexing indicators)

[ ] Streaming transcript UI (delta rendering)

[ ] Plugin/tool system for internal workflows



---

Contributing

PRs are welcome.
For major changes, please open an issue first to discuss the approach.


---

License

Choose a license: MIT


---

Credits

PySide6

sounddevice

websockets

sentence-transformers

OpenAI Realtime API
