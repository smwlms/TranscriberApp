
"""
Routes voor de review‐stap (intermediate transcript + speaker‐map)
van de Transcriber‑pipeline.
"""
from __future__ import annotations # DEZE MOET HIER, ALS EERSTE IMPORT/CODE



import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, abort, jsonify, request

from src.job_manager import STATUS_WAITING_FOR_REVIEW, job_manager
from src.pipeline_part2 import run_part2
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log

log("Loaded src/routes/review_routes.py", "DEBUG")

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
        log(f"Helper: Path traversal attempt blocked for _safe_load_json: {rel_path}", "ERROR")
        abort(400, description="Ongeldig pad")
    if not full_path.is_file():
        if must_exist:
            log(f"Helper: Bestand niet gevonden (must_exist=True) voor _safe_load_json: {rel_path}", "ERROR")
            abort(500, description=f"Bestand niet gevonden: {rel_path}")
        log(f"Helper: Bestand niet gevonden (must_exist=False) voor _safe_load_json: {rel_path}", "WARNING")
        return None
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"Helper: Fout bij laden JSON '{full_path}': {e}", "ERROR")
        # Afhankelijk van de context, kun je hier aborten of None returnen
        if must_exist:
            abort(500, description=f"Fout bij laden JSON: {e}")
        return None


def _safe_write_json(rel_path: str | Path, data: Any) -> None:
    """Schrijft JSON relatief t.o.v. PROJECT_ROOT en creëert parent‑dirs."""
    full_path = (PROJECT_ROOT / rel_path).resolve()
    if not full_path.is_relative_to(PROJECT_ROOT.resolve()):
        log(f"Helper: Path traversal attempt blocked for _safe_write_json: {rel_path}", "ERROR")
        abort(400, description="Ongeldig pad")
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"Helper: JSON succesvol geschreven naar '{full_path}'", "DEBUG")
    except Exception as e:
        log(f"Helper: Fout bij schrijven JSON naar '{full_path}': {e}", "ERROR")
        abort(500, description=f"Fout bij schrijven JSON: {e}")

# ────────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────────
@review_bp.route("/get_review_data/<string:job_id>", methods=["GET"])
def get_review_data(job_id: str):
    """Haal transcript, voorgestelde speaker‑map & context op voor review‑UI."""
    log(f"API CALL: GET /get_review_data/{job_id}", "INFO")

    job_data = job_manager.get_status(job_id)
    if not job_data:
        log(f"API: GET /get_review_data - Job {job_id} niet gevonden.", "WARNING")
        abort(404, description="Job niet gevonden")

    log(f"API: GET /get_review_data - Job {job_id} huidige status: {job_data.get('status')}", "DEBUG")
    if job_data.get("status") != STATUS_WAITING_FOR_REVIEW:
        log(f"API: GET /get_review_data - Job {job_id} staat niet in review-fase. Status is '{job_data.get('status')}'.", "WARNING")
        return jsonify({
            "error": "Job staat niet in review-fase",
            "current_status": job_data.get("status"),
        }), 409

    paths = job_data.get("review_data_paths", {})
    transcript_rel = paths.get("intermediate_transcript_path")
    map_rel = paths.get("proposed_map_path")
    context_rel = paths.get("context_snippets_path")

    log(f"API: GET /get_review_data - Paden voor job {job_id}: transcript='{transcript_rel}', map='{map_rel}', context='{context_rel}'", "DEBUG")

    payload: Dict[str, Any] = {
        "intermediate_transcript": None,
        "proposed_map": {},
        "context_snippets": {},
    }
    errors: List[str] = []

    # Transcript
    if transcript_rel:
        try:
            payload["intermediate_transcript"] = _safe_load_json(transcript_rel, must_exist=True)
            log(f"API: GET /get_review_data - Intermediate transcript geladen voor job {job_id}", "DEBUG")
        except Exception as e: # _safe_load_json kan aborten of None returnen; Exception hier is fallback
            msg = f"Fout bij laden transcript '{transcript_rel}' voor job {job_id}: {e}"
            log(msg, "ERROR")
            errors.append(msg)
            # Als transcript essentieel is en niet geladen kan worden, overweeg hier te aborten.
            # De must_exist=True in _safe_load_json zou dit al moeten doen.
    else:
        msg = f"API: GET /get_review_data - Geen pad voor intermediate transcript voor job {job_id}"
        log(msg, "ERROR")
        errors.append(msg)
        # Abort als transcript essentieel is
        return jsonify({
            "error": "Configuratiefout: Pad naar intermediate transcript ontbreekt voor de job.",
            "details": errors,
        }), 500


    # Speaker‑map
    if map_rel:
        try:
            data = _safe_load_json(map_rel) # Kan None zijn als het bestand niet bestaat
            payload["proposed_map"] = data or {}
            log(f"API: GET /get_review_data - Proposed map geladen voor job {job_id} (of leeg indien niet gevonden/fout)", "DEBUG")
        except Exception as e:
            msg = f"Fout bij laden speaker-map '{map_rel}' voor job {job_id}: {e}"
            log(msg, "WARNING") # Niet-kritiek als het niet bestaat
            errors.append(msg)
    else:
        log(f"API: GET /get_review_data - Geen pad voor proposed map voor job {job_id}. Gebruik lege map.", "INFO")


    # Context‑snippets
    if context_rel:
        try:
            data = _safe_load_json(context_rel) # Kan None zijn
            payload["context_snippets"] = data or {}
            log(f"API: GET /get_review_data - Context snippets geladen voor job {job_id} (of leeg indien niet gevonden/fout)", "DEBUG")
        except Exception as e:
            msg = f"Fout bij laden context '{context_rel}' voor job {job_id}: {e}"
            log(msg, "WARNING") # Niet-kritiek
            errors.append(msg)
    else:
        log(f"API: GET /get_review_data - Geen pad voor context snippets voor job {job_id}. Gebruik lege map.", "INFO")


    if payload["intermediate_transcript"] is None and not errors: # Dubbelcheck, zou al eerder afgehandeld moeten zijn
        log(f"API: GET /get_review_data - Kritieke fout: Intermediate transcript is None ZONDER errors lijst voor job {job_id}", "ERROR")
        return jsonify({
            "error": "Transcript kon niet geladen worden (onbekende reden)",
            "details": ["Intermediate transcript is None"],
        }), 500

    if errors:
        payload["non_critical_errors"] = errors # Stuur niet-kritieke fouten mee

    log(f"API: GET /get_review_data - Payload succesvol samengesteld voor job {job_id}", "INFO")
    return jsonify(payload)

# ────────────────────────────────────────────────────────────────────────────────
@review_bp.route("/update_review_data/<string:job_id>", methods=["POST"])
def update_review_data(job_id: str):
    """
    Slaat de definitieve speaker‑map op en start Pipeline‑Part 2.
    Verwacht body: { "final_speaker_map": { ... } }
    """
    log(f"API CALL: POST /update_review_data/{job_id}", "CRITICAL") # Duidelijke start log

    job_data = job_manager.get_status(job_id)
    # NIEUWE GEDETAILLEERDE LOG VOOR DE STATUS
    log(f"API: POST /update_review_data - Huidige job_data voor {job_id} VOOR status check: {job_data}", "CRITICAL")

    if not job_data:
        log(f"API: POST /update_review_data - Job {job_id} niet gevonden. Afbreken.", "ERROR")
        abort(404, description="Job niet gevonden")

    current_status_from_job_manager = job_data.get("status")
    if current_status_from_job_manager != STATUS_WAITING_FOR_REVIEW:
        # VERBETERDE LOG VOOR AFWIJZING
        log(f"API: POST /update_review_data - AFGEWEZEN. Job {job_id} status is '{current_status_from_job_manager}', verwacht '{STATUS_WAITING_FOR_REVIEW}'.", "ERROR")
        return jsonify({
            "error": "Job staat niet in review-fase",
            "current_status": current_status_from_job_manager, # Stuur de actuele status mee
        }), 409

    if not request.is_json:
        log(f"API: POST /update_review_data - Request voor job {job_id} is geen JSON. Afbreken.", "ERROR")
        abort(415, description="Content-Type moet application/json zijn")

    body = request.get_json()
    final_map = body.get("final_speaker_map")

    if not isinstance(final_map, dict):
        log(f"API: POST /update_review_data - 'final_speaker_map' ontbreekt of is geen object in request body voor job {job_id}. Afbreken.", "ERROR")
        return jsonify(error="'final_speaker_map' ontbreekt of is geen object"), 400

    log(f"API: POST /update_review_data - GEACCEPTEERD. Job {job_id} status is correct. Final map: {final_map}. Starten van Part 2 in thread.", "INFO")

    # Start Part 2 in een aparte thread
    # Het is belangrijk dat run_part2 de status van de job direct update (bv. naar ANALYZING)
    try:
        threading.Thread(
            target=lambda: run_part2(job_id, final_map), # Zorg dat final_map correct wordt doorgegeven
            daemon=True, # Zorgt ervoor dat de thread stopt als de hoofdapplicatie stopt
            name=f"RunPart2Thread-{job_id}"
        ).start()
    except Exception as e:
        log(f"API: POST /update_review_data - Kon Part 2 thread niet starten voor job {job_id}: {e}", "CRITICAL")
        # Hier zou je kunnen overwegen de jobstatus naar een FAILED state te zetten
        # job_manager.set_status(job_id, "PART2_START_FAILED", error_message=str(e))
        return jsonify(error=f"Kon Part 2 van de pipeline niet starten: {e}"), 500


    log(f"API: POST /update_review_data - Thread voor Part 2 gestart voor job {job_id}. HTTP 202 wordt geretourneerd.", "INFO")
    # De client (frontend) zal de statusverandering oppikken via polling.
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
    log(f"API CALL: POST /update_transcript_data/{job_id}", "INFO")

    job_data = job_manager.get_status(job_id)
    if not job_data:
        log(f"API: POST /update_transcript_data - Job {job_id} niet gevonden. Afbreken.", "WARNING")
        abort(404, description="Job niet gevonden")

    # OPTIONELE EXTRA LOGGING/CHECK: Controleer of de job wel in review staat
    current_status_from_job_manager = job_data.get("status")
    if current_status_from_job_manager != STATUS_WAITING_FOR_REVIEW:
        log(f"API: POST /update_transcript_data - WAARSCHUWING: Job {job_id} is in status '{current_status_from_job_manager}', niet '{STATUS_WAITING_FOR_REVIEW}', maar transcript update wordt toch verwerkt.", "WARNING")
        # Overweeg of je hier een 409 wilt sturen als de job niet in review is.
        # Voor nu, log alleen een waarschuwing en ga door.
        # Als je een 409 wilt:
        # return jsonify({
        #     "error": "Job staat niet in review-fase, transcript update afgewezen",
        #     "current_status": current_status_from_job_manager,
        # }), 409

    paths = job_data.get("review_data_paths", {})
    transcript_rel = paths.get("intermediate_transcript_path")
    if not transcript_rel:
        log(f"API: POST /update_transcript_data - Geen transcriptie-pad bekend voor job {job_id}. Afbreken.", "ERROR")
        abort(500, description="Geen transcriptie-pad bekend voor job")

    if not request.is_json:
        log(f"API: POST /update_transcript_data - Request voor job {job_id} is geen JSON. Afbreken.", "ERROR")
        abort(415, description="Content-Type moet application/json zijn")

    body = request.get_json()
    new_transcript = body.get("transcript") # Preferred key
    if new_transcript is None: # Fallback to legacy key
        new_transcript = body.get("new_transcript")

    if not isinstance(new_transcript, list):
        log(f"API: POST /update_transcript_data - 'transcript' (of 'new_transcript') ontbreekt of is geen lijst in request body voor job {job_id}. Afbreken.", "ERROR")
        return jsonify(error="'transcript' (of 'new_transcript') ontbreekt of is geen lijst"), 400

    log(f"API: POST /update_transcript_data - Nieuw transcript ontvangen voor job {job_id}. Aantal segmenten: {len(new_transcript)}", "DEBUG")

    try:
        _safe_write_json(transcript_rel, new_transcript)
        log(f"API: POST /update_transcript_data - Nieuwe transcriptie succesvol opgeslagen voor job {job_id} naar '{transcript_rel}'.", "INFO")
    except Exception as e: # _safe_write_json kan aborten; dit is een extra vangnet.
        log(f"API: POST /update_transcript_data - Fout bij opslaan van nieuwe transcriptie voor job {job_id}: {e}", "ERROR")
        abort(500, description=f"Kon transcriptie niet opslaan: {e}")


    return jsonify(message="Transcriptie bijgewerkt", job_id=job_id), 200