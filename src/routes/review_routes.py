"""
Routes voor de review‑stap (intermediate transcript + speaker‑map)
van de Transcriber‑pipeline.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, abort, jsonify, request

from src.job_manager import STATUS_WAITING_FOR_REVIEW, job_manager
from src.pipeline_part2 import run_part2
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log

# ────────────────────────────────────────────────────────────────────────────────
# Blueprint
# ────────────────────────────────────────────────────────────────────────────────
review_bp = Blueprint("review_bp", __name__)  # app.py voegt '/api/v1' toe

# ────────────────────────────────────────────────────────────────────────────────
# Helper‑functies
# ────────────────────────────────────────────────────────────────────────────────
def _safe_load_json(rel_path: str | Path, must_exist: bool = False) -> Any:
    """Laadt JSON relatief t.o.v. PROJECT_ROOT en doet beveiligings‑check."""
    full_path = (PROJECT_ROOT / rel_path).resolve()
    if not full_path.is_relative_to(PROJECT_ROOT.resolve()):
        abort(400, description="Ongeldig pad")
    if not full_path.is_file():
        if must_exist:
            abort(500, description=f"Bestand niet gevonden: {rel_path}")
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_write_json(rel_path: str | Path, data: Any) -> None:
    """Schrijft JSON relatief t.o.v. PROJECT_ROOT en creëert parent‑dirs."""
    full_path = (PROJECT_ROOT / rel_path).resolve()
    if not full_path.is_relative_to(PROJECT_ROOT.resolve()):
        abort(400, description="Ongeldig pad")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ────────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────────
@review_bp.route("/get_review_data/<string:job_id>", methods=["GET"])
def get_review_data(job_id: str):
    """Haal transcript, voorgestelde speaker‑map & context op voor review‑UI."""
    log(f"API: Request review data voor job {job_id}", "INFO")

    job_data = job_manager.get_status(job_id)
    if not job_data:
        abort(404, description="Job niet gevonden")
    if job_data.get("status") != STATUS_WAITING_FOR_REVIEW:
        return jsonify({
            "error": "Job staat niet in review-fase",
            "current_status": job_data.get("status"),
        }), 409

    paths = job_data.get("review_data_paths", {})
    transcript_rel = paths.get("intermediate_transcript_path")
    map_rel = paths.get("proposed_map_path")
    context_rel = paths.get("context_snippets_path")

    payload: Dict[str, Any] = {
        "intermediate_transcript": None,
        "proposed_map": {},
        "context_snippets": {},
    }
    errors: List[str] = []

    # Transcript
    try:
        payload["intermediate_transcript"] = _safe_load_json(
            transcript_rel, must_exist=True)
    except Exception as e:
        msg = f"Fout bij laden transcript '{transcript_rel}': {e}"
        log(msg, "ERROR")
        errors.append(msg)

    # Speaker‑map
    try:
        data = _safe_load_json(map_rel) if map_rel else {}
        payload["proposed_map"] = data or {}
    except Exception as e:
        msg = f"Fout bij laden speaker-map '{map_rel}': {e}"
        log(msg, "WARNING")
        errors.append(msg)

    # Context‑snippets
    try:
        data = _safe_load_json(context_rel) if context_rel else {}
        payload["context_snippets"] = data or {}
    except Exception as e:
        msg = f"Fout bij laden context '{context_rel}': {e}"
        log(msg, "WARNING")
        errors.append(msg)

    if payload["intermediate_transcript"] is None:
        return jsonify({
            "error": "Transcript kon niet geladen worden",
            "details": errors,
        }), 500

    if errors:
        payload["non_critical_errors"] = errors

    return jsonify(payload)

# ────────────────────────────────────────────────────────────────────────────────
@review_bp.route("/update_review_data/<string:job_id>", methods=["POST"])
def update_review_data(job_id: str):
    """
    Slaat de definitieve speaker‑map op en start Pipeline‑Part 2.
    Verwacht body: { "final_speaker_map": { ... } }
    """
    log(f"API: Review update ontvangen voor job {job_id}", "INFO")

    job_data = job_manager.get_status(job_id)
    if not job_data:
        abort(404, description="Job niet gevonden")
    if job_data.get("status") != STATUS_WAITING_FOR_REVIEW:
        return jsonify({
            "error": "Job staat niet in review-fase",
            "current_status": job_data.get("status"),
        }), 409
    if not request.is_json:
        abort(415, description="Content-Type moet application/json zijn")

    body = request.get_json()
    final_map = body.get("final_speaker_map")
    if not isinstance(final_map, dict):
        return jsonify(error="'final_speaker_map' ontbreekt of is geen object"), 400

    # Start Part 2 in een aparte thread
    threading.Thread(
        target=lambda: run_part2(job_id, final_map),
        daemon=True
    ).start()

    log(f"Pipeline deel 2 gestart voor job {job_id}", "INFO")
    return jsonify(message="Review opgeslagen; pipeline gaat verder"), 202

# ────────────────────────────────────────────────────────────────────────────────
@review_bp.route("/update_transcript_data/<string:job_id>", methods=["POST"])
def update_transcript_data(job_id: str):
    """
    Overschrijft het intermediate transcript.
    Accepts body:
       { "transcript": [...] }   # preferred key
       { "new_transcript": [...] }   # legacy key
    """
    log(f"API: Transcript update ontvangen voor job {job_id}", "INFO")

    job_data = job_manager.get_status(job_id)
    if not job_data:
        abort(404, description="Job niet gevonden")

    paths = job_data.get("review_data_paths", {})
    transcript_rel = paths.get("intermediate_transcript_path")
    if not transcript_rel:
        abort(500, description="Geen transcriptie-pad bekend voor job")

    if not request.is_json:
        abort(415, description="Content-Type moet application/json zijn")

    body = request.get_json()
    new_transcript = body.get("transcript") or body.get("new_transcript")
    if not isinstance(new_transcript, list):
        return jsonify(error="'transcript' ontbreekt of is geen lijst"), 400

    try:
        _safe_write_json(transcript_rel, new_transcript)
    except Exception as e:
        log(f"Fout bij opslaan van nieuwe transcriptie: {e}", "ERROR")
        abort(500, description=f"Kon transcriptie niet opslaan: {e}")

    log(f"Nieuwe transcriptie opgeslagen voor job {job_id}", "INFO")
    return jsonify(message="Transcriptie bijgewerkt", job_id=job_id), 200
