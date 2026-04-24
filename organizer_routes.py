"""
organizer_routes.py — Flask routes to expose the Organizer in BonsaiChat.

Register with:
    from api.organizer_routes import organizer_bp
    app.register_blueprint(organizer_bp)

Endpoints
---------
POST /organizer/scan          — list files + metadata, no changes made
POST /organizer/organize      — run the full organize pipeline
POST /organizer/chat          — natural-language chat with the organizer agent
POST /organizer/watch/start   — start background watcher daemon
POST /organizer/watch/stop    — stop background watcher daemon
"""

from flask import Blueprint, request, jsonify

from organizer.organizer_agent import (
    scan_folder,
    organize_folder,
    get_organizer_agent,
    ingest_organized_manifest,
    start_watch,
    stop_watch,
)

organizer_bp = Blueprint("organizer", __name__, url_prefix="/organizer")


# ── /scan ─────────────────────────────────────────────────────────────────────

@organizer_bp.route("/scan", methods=["POST"])
def scan():
    """
    Body: {"path": "/abs/path/to/folder"}
    Returns the file manifest without touching anything.
    """
    data = request.json or {}
    path = data.get("path", "")
    if not path:
        return jsonify({"ok": False, "error": "Missing 'path' field"}), 400
    try:
        manifest = scan_folder(path)
        return jsonify({"ok": True, "files": manifest, "count": len(manifest)})
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ── /organize ─────────────────────────────────────────────────────────────────

@organizer_bp.route("/organize", methods=["POST"])
def organize():
    """
    Body:
        source             (str, required)  — folder to read from
        target             (str, required)  — folder to write into
        strategy           (str)            — "rule" | "cluster" | "ai" | "hybrid"
        dry_run            (bool)           — preview without moving files
        preserve_originals (bool)           — copy rather than move
    """
    data = request.json or {}

    source = data.get("source", "")
    target = data.get("target", "")
    if not source or not target:
        return jsonify(
            {"ok": False, "error": "Both 'source' and 'target' fields are required"}
        ), 400

    try:
        results = organize_folder(
            source_path=source,
            target_path=target,
            strategy=data.get("strategy", "hybrid"),
            dry_run=data.get("dry_run", False),
            preserve_originals=data.get("preserve_originals", True),
        )
        ingest_organized_manifest(results)

        summary = {
            "total":   len(results),
            "copied":  sum(1 for r in results if r["status"] == "Copied"),
            "moved":   sum(1 for r in results if r["status"] == "Moved"),
            "dry_run": sum(1 for r in results if r["status"] == "DryRun"),
            "errors":  sum(1 for r in results if "Error" in r.get("status", "")),
        }
        return jsonify({"ok": True, "summary": summary, "manifest": results})

    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── /chat ─────────────────────────────────────────────────────────────────────

@organizer_bp.route("/chat", methods=["POST"])
def chat():
    """
    Natural-language interface to the organizer agent.

    Body:
        message    (str, required)
        session_id (str)          — defaults to "organizer-default"
        language   (str)          — "en" | "fr" | "es"
    """
    data = request.json or {}
    message    = data.get("message", "").strip()
    session_id = data.get("session_id", "organizer-default")
    language   = data.get("language", "en")

    if not message:
        return jsonify({"ok": False, "error": "No message provided"}), 400

    try:
        agent = get_organizer_agent(session_id, language)
        response = agent.run(message)
        content = (
            response.content if hasattr(response, "content") else str(response)
        )
        return jsonify({"ok": True, "response": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── /watch/start ──────────────────────────────────────────────────────────────

@organizer_bp.route("/watch/start", methods=["POST"])
def watch_start():
    """
    Body:
        source   (str, required)
        target   (str, required)
        strategy (str)             — default "hybrid"
        interval (int)             — seconds between scans, default 60
    """
    data = request.json or {}
    source = data.get("source", "")
    target = data.get("target", "")
    if not source or not target:
        return jsonify(
            {"ok": False, "error": "Both 'source' and 'target' fields are required"}
        ), 400

    start_watch(
        source_path=source,
        target_path=target,
        strategy=data.get("strategy", "hybrid"),
        interval_seconds=int(data.get("interval", 60)),
    )
    return jsonify({"ok": True, "watching": source})


# ── /watch/stop ───────────────────────────────────────────────────────────────

@organizer_bp.route("/watch/stop", methods=["POST"])
def watch_stop():
    stop_watch()
    return jsonify({"ok": True, "message": "Watcher stopped."})
