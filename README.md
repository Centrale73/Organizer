# AI Document Organizer

An intelligent **service module** (and optional standalone CLI) for automated file organization. Built with Python and the [Agno](https://github.com/agno-agi/agno) framework, it classifies and moves files using a tiered strategy — extension rules → semantic clustering → LLM — so it only calls the AI when it needs to.

Designed to run either as a **BonsaiChat backend module** or as a **standalone script**.

---

## ✨ What's New (v2)

| Before | After |
|---|---|
| PDF-only | Any file type |
| One strategy (LLM always) | `rule` / `cluster` / `ai` / `hybrid` |
| No preview | `dry_run=True` previews without moving |
| Blocking tkinter UI | Pure backend module + Flask blueprint |
| No watch mode | Background daemon via `start_watch()` |
| Standalone app | Importable module, shared memory with BonsaiChat |

---

## 🚀 Features

- **Hybrid classification pipeline** — extension lookup (instant) → KMeans+TF-IDF clustering (free) → LLM (only for ambiguous files)
- **Any file type** — not just PDFs; images, audio, video, code, archives, and more
- **Dry-run mode** — preview the planned folder structure without touching a single file
- **Watch daemon** — background thread polls for new/changed files and organizes them automatically
- **BonsaiChat integration** — shares SQLite memory and LanceDB vector store with `bonsai_agent.py`; chat interface asks "where did my invoice go?"
- **Flask REST API** — `/organizer/scan`, `/organizer/organize`, `/organizer/chat`, `/organizer/watch/start|stop`
- **Multi-provider AI** — plugs into any LlamaCpp-compatible server (local Ollama, LM Studio, etc.)
- **Confidence scoring** — every file tagged with a 0–100 confidence score and the strategy that classified it

---

## 🗂️ Project Structure

```
Organizer/
├── organizer/
│   ├── __init__.py
│   └── organizer_agent.py   ← core backend module
├── api/
│   └── organizer_routes.py  ← Flask blueprint (register in app.py)
├── app.py                   ← original tkinter UI (kept for reference)
├── loadstorage.py           ← storage helpers
└── memory_data/             ← auto-created: LanceDB + SQLite
```

---

## 🛠️ Installation

### Prerequisites

- Python 3.10+
- A running LlamaCpp-compatible model server (e.g. [LM Studio](https://lmstudio.ai), [Ollama](https://ollama.ai)) at `http://127.0.0.1:8081/v1`

### Setup

```bash
git clone https://github.com/Centrale73/Organizer.git
cd Organizer

pip install agno lancedb fastembed
pip install scikit-learn          # optional: enables cluster strategy
pip install flask                 # optional: enables REST API
```

---

## ⚡ Quick Start

### As a Python module

```python
from organizer import organize_folder, scan_folder

# Preview what would happen (no files moved)
manifest = organize_folder(
    source_path="/Users/me/Downloads",
    target_path="/Users/me/Organized",
    strategy="hybrid",
    dry_run=True,
)

for item in manifest:
    print(f"{item['filename']} → {item['category']} ({item['confidence']}%)")

# Actually organize
organize_folder(
    source_path="/Users/me/Downloads",
    target_path="/Users/me/Organized",
    strategy="hybrid",
    dry_run=False,
    preserve_originals=True,   # copy, not move
)
```

### As a Flask service (BonsaiChat integration)

```python
# app.py
from flask import Flask
from api.organizer_routes import organizer_bp

app = Flask(__name__)
app.register_blueprint(organizer_bp)
```

Then call the API:

```bash
# Scan (no changes)
curl -X POST http://localhost:5000/organizer/scan \
  -H "Content-Type: application/json" \
  -d '{"path": "/Users/me/Downloads"}'

# Dry-run organize
curl -X POST http://localhost:5000/organizer/organize \
  -H "Content-Type: application/json" \
  -d '{"source": "/Users/me/Downloads", "target": "/Users/me/Organized", "dry_run": true}'

# Start watcher daemon (re-checks every 60 s)
curl -X POST http://localhost:5000/organizer/watch/start \
  -H "Content-Type: application/json" \
  -d '{"source": "/Users/me/Downloads", "target": "/Users/me/Organized", "interval": 60}'

# Chat about organized files
curl -X POST http://localhost:5000/organizer/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Where did my March invoice end up?", "session_id": "user-1"}'
```

---

## 🎯 Classification Strategies

| Strategy | Speed | Cost | Best for |
|---|---|---|---|
| `rule` | Instant | Free | Known extensions (images, video, code…) |
| `cluster` | Fast | Free | Text files with no obvious category |
| `ai` | Slow | Model tokens | High-value ambiguous documents |
| `hybrid` | Fast + smart | Minimal | **Recommended default** |

`hybrid` applies all three in sequence, stopping as soon as a file is confidently classified.

---

## 📁 Default Category Map

Extension-based categories (rule strategy):

`Documents` · `Spreadsheets` · `Presentations` · `Images` · `Videos` · `Audio` · `Archives` · `Code` · `Ebooks` · `Data` · `Fonts` · `Executables`

AI categories (for ambiguous files):

`Financial` · `Legal` · `Medical` · `Academic` · `Business` · `Personal` · `Technical` · `Research` · `Creative` · `Reference` · `Correspondence`

---

## 🔌 BonsaiChat Integration

`organizer_agent.py` shares BonsaiChat's SQLite memory DB and LanceDB vector store. After each organize run, `ingest_organized_manifest()` writes the file manifest into the knowledge base so the chat agent can answer questions like:

> "Where did my Q3 invoice go?"  
> "Organize my Downloads folder and show me a preview first."  
> "Move only the PDFs from /tmp/inbox to /Archive."

---

## License

MIT
