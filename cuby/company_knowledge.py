# cuby/company_knowledge.py
import os
import json
import uuid
from typing import List, Dict, Any

import numpy as np
from sentence_transformers import SentenceTransformer

# Optional imports for DOCX / PDF support
try:
    import docx  # python-docx
except ImportError:
    docx = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None


class CompanyKnowledge:
    """
    Simple local RAG store:
      - Stores document chunks + embeddings in a single JSON file.
      - Supports TXT / DOCX / PDF (if libs are available).
      - Uses a multilingual sentence-transformers model (for Persian + English).
    """

    def __init__(
        self,
        storage_path: str,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ):
        """
        storage_path: path to JSON file, e.g. data/company_knowledge.json
        """
        self.storage_path = storage_path

        # ✅ مهم: فقط فولدر پدر رو می‌سازیم، نه خود فایل JSON رو
        self.storage_dir = os.path.dirname(storage_path) or "."
        os.makedirs(self.storage_dir, exist_ok=True)

        self.model_name = model_name
        self._model = SentenceTransformer(self.model_name)

        self._docs: List[Dict[str, Any]] = []
        self._emb_matrix: np.ndarray | None = None

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        """Load existing JSON store if it exists; otherwise start empty."""
        if not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        if not isinstance(data, dict):
            return

        stored_model = data.get("model_name")
        docs = data.get("documents") or []
        self._docs = docs

        # If model name changed, re-embed all texts
        if stored_model != self.model_name:
            texts = [d.get("text", "") for d in self._docs]
            texts = [t for t in texts if t.strip()]
            if not texts:
                self._emb_matrix = None
                return

            embs = self._model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            i = 0
            for d in self._docs:
                t = d.get("text", "")
                if not t.strip():
                    d["embedding"] = None
                else:
                    d["embedding"] = embs[i].tolist()
                    i += 1
            self._emb_matrix = embs
            self._save()
        else:
            # Try to load embeddings directly
            embs = []
            for d in self._docs:
                emb = d.get("embedding")
                if emb is None:
                    embs = []
                    break
                embs.append(np.array(emb, dtype=np.float32))

            if embs:
                self._emb_matrix = np.vstack(embs)
            else:
                # embeddings missing → recompute
                texts = [d.get("text", "") for d in self._docs]
                texts = [t for t in texts if t.strip()]
                if not texts:
                    self._emb_matrix = None
                    return
                embs = self._model.encode(
                    texts,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                i = 0
                for d in self._docs:
                    t = d.get("text", "")
                    if not t.strip():
                        d["embedding"] = None
                    else:
                        d["embedding"] = embs[i].tolist()
                        i += 1
                self._emb_matrix = embs
                self._save()

    def _save(self):
        """Save documents + embeddings metadata to JSON."""
        try:
            data = {
                "model_name": self.model_name,
                "documents": self._docs,
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # File reading helpers
    # ------------------------------------------------------------------

    def _read_txt(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _read_docx(self, path: str) -> str:
        if docx is None:
            return ""
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)

    def _read_pdf(self, path: str) -> str:
        if PyPDF2 is None:
            return ""
        text_parts: List[str] = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    text_parts.append(page.extract_text() or "")
                except Exception:
                    continue
        return "\n".join(text_parts)

    def _extract_text_from_file(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".txt", ".md", ".log"):
            return self._read_txt(path)
        if ext == ".docx":
            return self._read_docx(path)
        if ext == ".pdf":
            return self._read_pdf(path)

        # fallback
        try:
            return self._read_txt(path)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_files(
        self,
        paths: List[str],
        chunk_size: int = 800,
        chunk_overlap: int = 200,
    ):
        """
        Add/update documents from given file paths:
          - Remove previous chunks from same file
          - Split into sliding window chunks
          - Embed and store
        """
        new_texts: List[str] = []
        new_docs: List[Dict[str, Any]] = []

        for path in paths:
            if not path:
                continue
            abs_path = os.path.abspath(path)

            # Read text
            text = self._extract_text_from_file(abs_path)
            if not text.strip():
                continue

            # Remove old chunks of the same file (avoid duplicates)
            self._docs = [
                d
                for d in self._docs
                if os.path.abspath(d.get("source_path", "")) != abs_path
            ]

            # Split text into word chunks
            tokens = text.split()
            if not tokens:
                continue

            i = 0
            while i < len(tokens):
                chunk_tokens = tokens[i : i + chunk_size]
                i += max(1, chunk_size - chunk_overlap)
                chunk_text = " ".join(chunk_tokens).strip()
                if not chunk_text:
                    continue
                new_texts.append(chunk_text)
                new_docs.append(
                    {
                        "id": str(uuid.uuid4()),
                        "source_path": abs_path,
                        "text": chunk_text,
                        "embedding": None,
                    }
                )

        if not new_docs:
            return

        # Embed new chunks
        embs = self._model.encode(
            new_texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        for d, e in zip(new_docs, embs):
            d["embedding"] = e.tolist()

        # Append to all docs
        self._docs.extend(new_docs)

        # Rebuild embedding matrix
        all_embs = [
            np.array(d["embedding"], dtype=np.float32)
            for d in self._docs
            if d.get("embedding") is not None
        ]
        if all_embs:
            self._emb_matrix = np.vstack(all_embs)
        else:
            self._emb_matrix = None

        self._save()

    def build_context_for_query(self, query: str, top_k: int = 5) -> str:
        """
        Given a user question, return a concatenated context string
        from the most similar chunks.
        """
        query = (query or "").strip()
        if not query:
            return ""
        if not self._docs or self._emb_matrix is None:
            return ""

        q_emb = self._model.encode(
            [query],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )[0]

        scores = np.dot(self._emb_matrix, q_emb)
        k = min(top_k, len(self._docs))
        top_idx = np.argsort(-scores)[:k]

        selected: List[str] = []
        for idx in top_idx:
            d = self._docs[int(idx)]
            txt = d.get("text", "").strip()
            if txt:
                selected.append(txt)

        # Join chunks با جداکننده
        return "\n\n---\n\n".join(selected)
