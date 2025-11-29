# cuby/conversations.py
import os
import json
import uuid
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ConversationMessage:
    role: str  # "user" | "assistant" | "system"
    text: str


@dataclass
class Conversation:
    id: str
    title: str
    messages: List[ConversationMessage] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z"
    )


class ConversationManager:
    """Handles loading/saving and managing multiple conversations."""

    def __init__(self, path: str):
        self.path = path
        self.conversations: Dict[str, Conversation] = {}
        self._load()

    # ---------- Persistence ----------

    def _load(self):
        """Load conversations from disk. Be tolerant to minor schema variations."""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # Support both {"conversations":[...]} and direct list [...]
        convs_data = []
        if isinstance(data, dict) and "conversations" in data:
            convs_data = data.get("conversations", [])
        elif isinstance(data, list):
            convs_data = data
        else:
            # Unknown format; ignore to avoid crashing
            return

        for c in convs_data:
            try:
                cid = c.get("id") or str(uuid.uuid4())
                title = (c.get("title") or "Untitled").strip() or "Untitled"
                created = c.get("created_at") or datetime.datetime.utcnow().isoformat() + "Z"
                msgs_data = c.get("messages", [])
                msgs: List[ConversationMessage] = []
                for m in msgs_data:
                    role = (m.get("role") or "user").strip()
                    text = m.get("text") or ""
                    msgs.append(ConversationMessage(role=role, text=text))
                conv = Conversation(id=cid, title=title, messages=msgs, created_at=created)
                self.conversations[cid] = conv
            except Exception:
                # Skip malformed conversation entries gracefully
                continue

    def _save(self):
        """Persist all conversations to disk in a stable schema."""
        data = {
            "conversations": [
                {
                    "id": conv.id,
                    "title": conv.title,
                    "created_at": conv.created_at,
                    "messages": [
                        {"role": m.role, "text": m.text} for m in conv.messages
                    ],
                }
                for conv in self.conversations.values()
            ]
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- Public API ----------

    def list_conversations(self) -> List[Conversation]:
        """Return conversations sorted by creation time (oldest first)."""
        return sorted(
            self.conversations.values(),
            key=lambda c: c.created_at,
        )

    def get(self, conv_id: str) -> Optional[Conversation]:
        return self.conversations.get(conv_id)

    def create_conversation(self, title: Optional[str] = None) -> Conversation:
        cid = str(uuid.uuid4())
        title = (title or "New Chat").strip() or "New Chat"
        conv = Conversation(id=cid, title=title)
        self.conversations[cid] = conv
        self._save()
        return conv

    def rename_conversation(self, conv_id: str, new_title: str):
        conv = self.conversations.get(conv_id)
        if not conv:
            return
        new_title = (new_title or "").strip()
        if not new_title:
            return
        conv.title = new_title
        self._save()

    def add_message(self, conv_id: str, role: str, text: str):
        conv = self.conversations.get(conv_id)
        if not conv:
            return
        conv.messages.append(ConversationMessage(role=role, text=text))
        self._save()

    def delete_conversation(self, conv_id: str) -> bool:
        """
        Delete a conversation by id and persist to disk.
        Returns True if deleted, False if not found.
        """
        if conv_id not in self.conversations:
            return False
        try:
            del self.conversations[conv_id]
            self._save()
            return True
        except Exception:
            return False

    # ---------- Memory helpers ----------

    def build_memory_snippet(
        self,
        conv_id: str,
        max_messages: int = 10,
    ) -> Optional[str]:
        """
        Build a compact text memory from the last N messages of a conversation.
        This will be injected into instructions for that chat.
        """
        conv = self.conversations.get(conv_id)
        if not conv or not conv.messages:
            return None

        msgs = conv.messages[-max_messages:]
        lines = []
        for m in msgs:
            if m.role == "user":
                who = "User"
            elif m.role == "assistant":
                who = "Cuby"
            else:
                who = "System"
            lines.append(f"{who}: {m.text}")
        return "\n".join(lines)
