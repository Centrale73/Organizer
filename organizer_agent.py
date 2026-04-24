"""
organizer_agent.py — Backend organizer module for BonsaiChat.

Replaces the monolithic tkinter app.py with a pure service module that:
  - handles any file type (not just PDFs)
  - supports rule / cluster / ai / hybrid classification strategies
  - exposes a dry-run flag (preview without moving files)
  - runs as a background watcher daemon
  - integrates as a singleton Agno agent alongside bonsai_agent.py

Borrowed best-of:
  - connor          : KMeans + TF-IDF clustering (rule-free semantic grouping)
  - yonuc/hazelnut  : Extension-based rule maps + watch/dry-run pattern
  - Local-File-Org  : Multi-type file reading (pdf, csv, text, image fallback)
  - Centrale73/Org  : Agno agent, multi-provider, confidence scoring
  - BonsaiChat      : Singleton agent pattern, LanceDB knowledge, SqliteDb memory

Usage from bridge.py:
    from organizer.organizer_agent import organize_folder, get_organizer_agent
"""

from __future__ import annotations

import os
import json
import shutil
import hashlib
import datetime
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from collections import defaultdict

# ── Agno ──────────────────────────────────────────────────────────────────────
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.llama_cpp import LlamaCpp
from agno.memory import MemoryManager
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb
from agno.knowledge.embedder.fastembed import FastEmbedEmbedder
from agno.knowledge.chunking.recursive import RecursiveChunking

# ── Optional heavy deps (graceful fallback) ────────────────────────────────────
try:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np
    _SKLEARN = True
except ImportError:
    _SKLEARN = False

try:
    from agno.knowledge.reader.pdf_reader import PDFReader
    _PDF = True
except ImportError:
    _PDF = False

try:
    from agno.knowledge.reader.csv_reader import CSVReader
    _CSV = True
except ImportError:
    _CSV = False

try:
    from agno.knowledge.reader.text_reader import TextReader
    _TEXT = True
except ImportError:
    _TEXT = False

# ── Paths (mirrors bonsai_agent.py pattern) ───────────────────────────────────
_base_dir = os.path.dirname(os.path.abspath(__file__))
_app_data = os.path.join(_base_dir, "..", "memory_data")
os.makedirs(_app_data, exist_ok=True)

LANCE_URI = os.path.join(_app_data, "lancedb")
DB_FILE   = os.path.join(_app_data, "bonsaichat_memory.db")

DEFAULT_CHUNKER = RecursiveChunking(chunk_size=1000, overlap=150)

# ── Extension rule map (from yonuc / hazelnut pattern) ───────────────────────
EXT_RULES: Dict[str, List[str]] = {
    "Documents":     [".pdf", ".doc", ".docx", ".odt", ".rtf", ".tex"],
    "Spreadsheets":  [".xls", ".xlsx", ".csv", ".ods"],
    "Presentations": [".ppt", ".pptx", ".odp"],
    "Images":        [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic"],
    "Videos":        [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    "Audio":         [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
    "Archives":      [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"],
    "Code":          [
        ".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c",
        ".h", ".rs", ".go", ".sh", ".bat", ".json", ".yaml", ".yml", ".toml",
    ],
    "Ebooks":        [".epub", ".mobi", ".azw"],
    "Data":          [".db", ".sqlite", ".parquet", ".feather"],
    "Fonts":         [".ttf", ".otf", ".woff", ".woff2"],
    "Executables":   [".exe", ".msi", ".dmg", ".deb", ".AppImage"],
}

# ── AI category taxonomy (from original Organizer) ────────────────────────────
AI_CATEGORIES = [
    "Financial", "Legal", "Medical", "Academic",
    "Business", "Personal", "Technical", "Research",
    "Creative", "Reference", "Correspondence",
]

# ── Singletons ─────────────────────────────────────────────────────────────────
_organizer_agent: Optional[Agent] = None
_knowledge:       Optional[Knowledge] = None
_db:              Optional[SqliteDb] = None
_watch_thread:    Optional[threading.Thread] = None
_watch_stop = threading.Event()


# ══════════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_db() -> SqliteDb:
    global _db
    if _db is None:
        _db = SqliteDb(db_file=DB_FILE)
    return _db


def _get_knowledge() -> Knowledge:
    global _knowledge
    if _knowledge is None:
        _knowledge = Knowledge(
            vector_db=LanceDb(
                table_name="organizer_docs",
                uri=LANCE_URI,
                embedder=FastEmbedEmbedder(
                    id="BAAI/bge-small-en-v1.5",
                    dimensions=384,
                ),
            ),
        )
    return _knowledge


def _read_text_content(file_path: Path, max_chars: int = 4000) -> str:
    """
    Multi-type reader (PDF, CSV, plain text, images via filename heuristic).
    Mirrors Local-File-Organizer's approach of reading whatever it can.
    Falls back gracefully to filename stem for binary/unknown types.
    """
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".pdf" and _PDF:
            reader = PDFReader(chunking_strategy=DEFAULT_CHUNKER)
            docs = reader.read(str(file_path))
            return " ".join(d.content for d in docs if d.content)[:max_chars]

        if suffix == ".csv" and _CSV:
            reader = CSVReader(chunking_strategy=DEFAULT_CHUNKER)
            docs = reader.read(str(file_path))
            return " ".join(d.content for d in docs if d.content)[:max_chars]

        if suffix in (
            ".txt", ".md", ".py", ".js", ".json", ".yaml",
            ".yml", ".html", ".rst", ".toml", ".log",
        ):
            return file_path.read_text(errors="ignore")[:max_chars]

        # Fallback: filename stem gives clustering at least something to work with
        return file_path.stem.replace("_", " ").replace("-", " ")

    except Exception:
        return file_path.stem.replace("_", " ").replace("-", " ")


def _rule_classify(file_path: Path) -> Optional[str]:
    """
    Instant, zero-cost extension-based triage.
    Returns None for unknown extensions so the next strategy can handle them.
    """
    ext = file_path.suffix.lower()
    for category, extensions in EXT_RULES.items():
        if ext in extensions:
            return category
    return None


def _cluster_classify(files_with_content: List[tuple]) -> Dict[str, str]:
    """
    KMeans + TF-IDF clustering (from connor).
    Groups files by semantic similarity with zero LLM cost.
    Cluster labels are derived from top TF-IDF terms (connor's naming.py approach).

    Args:
        files_with_content: list of (filepath_str, content_str) tuples

    Returns:
        {filepath_str: cluster_label_str}
    """
    if not _SKLEARN or len(files_with_content) < 3:
        return {}

    names = [p for p, _ in files_with_content]
    texts = [c for _, c in files_with_content]

    vectorizer = TfidfVectorizer(max_features=500, stop_words="english", min_df=1)
    try:
        X = vectorizer.fit_transform(texts).toarray()
    except ValueError:
        return {}

    n_clusters = max(2, int(len(files_with_content) ** 0.5))
    n_clusters = min(n_clusters, len(files_with_content) - 1)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    # Name each cluster with its top TF-IDF terms
    feature_names = vectorizer.get_feature_names_out()
    cluster_names: Dict[int, str] = {}
    for cid in range(n_clusters):
        mask = labels == cid
        if not mask.any():
            continue
        cluster_X = X[mask]
        scores = cluster_X.mean(axis=0)
        top_idx = scores.argsort()[-4:][::-1]
        words = [feature_names[i].capitalize() for i in top_idx if scores[i] > 0]
        cluster_names[cid] = "_".join(words) if words else f"Cluster_{cid}"

    return {
        name: cluster_names.get(label, "Misc")
        for name, label in zip(names, labels)
    }


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC SCANNING API
# ══════════════════════════════════════════════════════════════════════════════

def scan_folder(folder_path: str) -> List[Dict[str, Any]]:
    """
    Walk a folder recursively and return a metadata manifest for every file.
    Called by BonsaiChat's bridge before organize_folder, or standalone.

    Returns:
        List of dicts, one per file, with keys:
        filename, filepath, extension, size_bytes, modified,
        category, confidence, strategy_used, status.
    """
    root = Path(folder_path)
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    manifest = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            manifest.append({
                "filename":      f.name,
                "filepath":      str(f),
                "extension":     f.suffix.lower(),
                "size_bytes":    stat.st_size,
                "modified":      datetime.datetime.fromtimestamp(
                                     stat.st_mtime
                                 ).isoformat(),
                "category":      None,
                "confidence":    0,
                "strategy_used": None,
                "status":        "Pending",
            })
    return manifest


# ══════════════════════════════════════════════════════════════════════════════
#  CORE ORGANIZE PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def organize_folder(
    source_path: str,
    target_path: str,
    strategy: str = "hybrid",
    dry_run: bool = False,
    preserve_originals: bool = True,
    progress_cb: Optional[Callable[[dict], None]] = None,
    ai_model_url: str = "http://127.0.0.1:8081/v1",
) -> List[Dict[str, Any]]:
    """
    Main organize pipeline. Returns the final manifest with per-file results.

    Strategies
    ----------
    "rule"    — Extension lookup only (instant, zero deps).
    "cluster" — KMeans + TF-IDF semantic grouping (no LLM cost, needs sklearn).
    "ai"      — Agno LLM agent on every file (highest quality, needs model).
    "hybrid"  — rule → cluster for text files → AI only on ambiguous remainder.
                This is the recommended default.

    Parameters
    ----------
    dry_run           : categorize but skip all file system moves / copies.
    preserve_originals: copy (True) rather than move (False).
    progress_cb       : called with each item dict as it is finalized, useful
                        for streaming progress to a UI or WebSocket.
    """
    manifest = scan_folder(source_path)
    target = Path(target_path)

    # ── Step 1: Rule pass (always runs, always fast) ───────────────────────────
    unclassified = []
    for item in manifest:
        fp = Path(item["filepath"])
        rule_cat = _rule_classify(fp)
        if rule_cat:
            item["category"]      = rule_cat
            item["confidence"]    = 95
            item["strategy_used"] = "rule"
        else:
            unclassified.append(item)

    # ── Step 2: Cluster pass ───────────────────────────────────────────────────
    if strategy in ("cluster", "hybrid") and unclassified and _SKLEARN:
        readable = []
        for item in unclassified:
            content = _read_text_content(Path(item["filepath"]))
            if content.strip():
                readable.append((item["filepath"], content))

        cluster_map = _cluster_classify(readable)

        for item in unclassified:
            if item["filepath"] in cluster_map:
                item["category"]      = cluster_map[item["filepath"]]
                item["confidence"]    = 72
                item["strategy_used"] = "cluster"

    still_unclassified = [
        i for i in manifest
        if i["category"] is None or i["confidence"] < 50
    ]

    # ── Step 3: AI pass (only on truly ambiguous files) ───────────────────────
    if strategy in ("ai", "hybrid") and still_unclassified:
        _ai_batch_classify(still_unclassified, ai_model_url)

    # ── Step 4: Move / Copy (or skip on dry-run) ──────────────────────────────
    for item in manifest:
        if not item.get("category"):
            item["category"]  = "Uncategorized"
            item["confidence"] = 0

        if progress_cb:
            progress_cb(item)

        if dry_run:
            item["status"] = "DryRun"
            continue

        source_file = Path(item["filepath"])
        if not source_file.exists():
            item["status"] = "SourceMissing"
            continue

        dest_dir = target / item["category"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / source_file.name

        # Collision handling: append counter suffix (from original Organizer)
        counter = 1
        while dest_file.exists():
            dest_file = dest_dir / (
                f"{source_file.stem}_{counter}{source_file.suffix}"
            )
            counter += 1

        try:
            if preserve_originals:
                shutil.copy2(source_file, dest_file)
                item["status"] = "Copied"
            else:
                shutil.move(str(source_file), str(dest_file))
                item["status"] = "Moved"
            item["organized_path"] = str(dest_file)
        except Exception as e:
            item["status"] = f"Error: {e}"

    return manifest


def _ai_batch_classify(items: List[Dict], model_url: str) -> None:
    """
    Use BonsaiChat's local LlamaCpp model to classify ambiguous files.
    Updates items in-place. Confidence scoring preserved from original Organizer.
    """
    try:
        classifier = Agent(
            model=LlamaCpp(id="bonsai-8b", base_url=model_url),
            instructions=(
                f"You are a file classification expert. Given a filename and "
                f"optional content snippet, classify the file into exactly one "
                f"of these categories:\n{', '.join(AI_CATEGORIES)}\n\n"
                "Respond ONLY with valid JSON:\n"
                '{"category": "CategoryName", "confidence": 85, "reason": "brief explanation"}'
            ),
            markdown=False,
            stream=False,
        )
    except Exception:
        return

    for item in items:
        try:
            content_snippet = _read_text_content(
                Path(item["filepath"]), max_chars=800
            )
            prompt = (
                f"Filename: {item['filename']}\nContent: {content_snippet}"
            )
            response = classifier.run(prompt)
            raw = (
                response.content if hasattr(response, "content") else str(response)
            )

            start, end = raw.find("{"), raw.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(raw[start:end])
                item["category"]      = result.get("category", "General")
                item["confidence"]    = max(
                    0, min(100, int(result.get("confidence", 50)))
                )
                item["strategy_used"] = "ai"
                item["reason"]        = result.get("reason", "")
        except Exception:
            item["category"]      = "General"
            item["confidence"]    = 20
            item["strategy_used"] = "ai_fallback"


# ══════════════════════════════════════════════════════════════════════════════
#  WATCH MODE (hazelnut-inspired daemon)
# ══════════════════════════════════════════════════════════════════════════════

def start_watch(
    source_path: str,
    target_path: str,
    strategy: str = "hybrid",
    interval_seconds: int = 30,
    progress_cb: Optional[Callable[[dict], None]] = None,
) -> None:
    """
    Start a background daemon that re-runs organize_folder every
    `interval_seconds`. Uses SHA-256 hashing to detect only new/changed files
    and skip files already processed — avoids redundant AI calls.
    """
    global _watch_thread, _watch_stop
    _watch_stop.clear()
    seen: Dict[str, str] = {}  # filepath → sha256

    def _hash(path: str) -> str:
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def _loop() -> None:
        while not _watch_stop.is_set():
            try:
                manifest = scan_folder(source_path)
                new_items = []
                for item in manifest:
                    fp = item["filepath"]
                    h = _hash(fp)
                    if seen.get(fp) != h:
                        new_items.append(item)
                        seen[fp] = h

                if new_items:
                    organize_folder(
                        source_path=source_path,
                        target_path=target_path,
                        strategy=strategy,
                        dry_run=False,
                        progress_cb=progress_cb,
                    )
            except Exception as e:
                print(f"[OrganizerWatch] Error: {e}")

            _watch_stop.wait(timeout=interval_seconds)

    _watch_thread = threading.Thread(
        target=_loop, daemon=True, name="OrganizerWatch"
    )
    _watch_thread.start()
    print(f"[OrganizerWatch] Started watching: {source_path}")


def stop_watch() -> None:
    """Stop the background watcher daemon."""
    _watch_stop.set()
    print("[OrganizerWatch] Stopped.")


# ══════════════════════════════════════════════════════════════════════════════
#  AGNO CHAT AGENT (singleton pattern mirrored from bonsai_agent.py)
# ══════════════════════════════════════════════════════════════════════════════

_ORGANIZER_INSTRUCTIONS = (
    "You are a file organization assistant integrated into BonsaiChat. "
    "You can scan folders, organize files by category, explain what was organized, "
    "and answer questions about file structure. "
    "When the user asks to organize a folder, call the appropriate function. "
    "Always confirm before moving files unless dry_run mode is active. "
    "Format file trees and category lists as markdown."
)


def init_organizer_agent(model_url: str = "http://127.0.0.1:8081/v1") -> None:
    """
    Build and cache the organizer Agno agent.
    Shares the same SqliteDb and LanceDb as bonsai_agent.py so the chat
    agent can answer 'where did my invoice go?' without a separate memory store.
    Safe to call multiple times (idempotent).
    """
    global _organizer_agent
    if _organizer_agent is not None:
        return

    _organizer_agent = Agent(
        model=LlamaCpp(id="bonsai-8b", base_url=model_url),
        db=_get_db(),
        memory_manager=MemoryManager(
            db=_get_db(),
            additional_instructions=(
                "Remember user's preferred folder structures and naming conventions."
            ),
        ),
        update_memory_on_run=True,
        add_memories_to_context=True,
        add_history_to_context=True,
        instructions=_ORGANIZER_INSTRUCTIONS,
        knowledge=_get_knowledge(),
        search_knowledge=True,
        markdown=True,
    )


def get_organizer_agent(session_id: str, language: str = "en") -> Agent:
    """
    Return the singleton organizer agent, initialising it on first call.
    Supports per-session language switching (en / fr / es).
    """
    if _organizer_agent is None:
        init_organizer_agent()

    _organizer_agent.session_id = session_id

    lang_map = {
        "fr": f"{_ORGANIZER_INSTRUCTIONS} Réponds toujours en français.",
        "es": f"{_ORGANIZER_INSTRUCTIONS} Responde siempre en español.",
    }
    _organizer_agent.instructions = lang_map.get(
        language, _ORGANIZER_INSTRUCTIONS
    )
    return _organizer_agent


def ingest_organized_manifest(manifest: List[Dict]) -> bool:
    """
    After organizing, push the manifest summary into BonsaiChat's LanceDB
    so the chat agent can answer 'where did my invoice go?'
    """
    summary_lines = ["# Organized File Manifest\n"]
    by_cat: Dict[str, list] = defaultdict(list)
    for item in manifest:
        by_cat[item.get("category", "Unknown")].append(item["filename"])

    for cat, files in sorted(by_cat.items()):
        summary_lines.append(f"## {cat}")
        for f in files:
            summary_lines.append(f"- {f}")

    summary_text = "\n".join(summary_lines)
    tmp_path = os.path.join(_app_data, "last_manifest.md")
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(summary_text)
        _get_knowledge().insert(
            path=tmp_path,
            name="last_manifest.md",
            reader=(
                TextReader(chunking_strategy=DEFAULT_CHUNKER) if _TEXT else None
            ),
            metadata={"type": "organizer_manifest"},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[OrganizerAgent] Manifest ingest failed: {e}")
        return False
