import threading
import traceback
import json
from pathlib import Path
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify, abort, current_app
from werkzeug.utils import secure_filename

from src.job_manager import job_manager
from src.constants import (
    STATUS_WAITING_FOR_REVIEW,
    STATUS_MAPPING_SPEAKERS,
    PROGRESS_AFTER_MAPPING
)
from src.utils.log import log
from src.utils.route_helpers import parse_config_overrides_from_form
from src.utils.config_schema import PROJECT_ROOT

UPLOAD_FOLDER_NAME = "audio"
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
RESULTS_FOLDER_NAME = "results"
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME

pipeline_bp = Blueprint('pipeline', __name__)


@pipeline_bp.route("/start_pipeline", methods=["POST"])
def start_pipeline_route():
    log("API: Request received for /start_pipeline", "INFO")
    # Lazy import to avoid heavy dependencies at app startup
    try:
        from src.pipeline_part1 import run_part1  # noqa: WPS433 (local import intentional)
    except Exception as e:
        log(f"Import error for pipeline_part1 (likely missing heavy deps like torch): {e}", "ERROR")
        return jsonify({
            "error": "Pipeline dependencies missing",
            "message": "Install full requirements to run the pipeline (pip install -r requirements.txt or make install)."
        }), 500
    if not request.form:
        return jsonify({"error": "Missing form data"}), 400

    # --- valideer en bouw het pad naar de audio-file ---
    relative_audio_path_from_form = request.form.get("relative_audio_path")
    if not relative_audio_path_from_form:
        return jsonify({"error": "Missing 'relative_audio_path'"}), 400

    try:
        submitted_path = Path(relative_audio_path_from_form)
        safe_filename = secure_filename(submitted_path.name)
        if not safe_filename:
            raise ValueError("Invalid filename derived from path.")
        abs_path = (UPLOAD_FOLDER / safe_filename).resolve()
        if not abs_path.is_file():
            raise FileNotFoundError(f"Audio file '{safe_filename}' not found in upload directory.")
        if not abs_path.is_relative_to(UPLOAD_FOLDER.resolve()):
            raise ValueError("Security check failed: Resolved path is outside.")
        validated_relative_path_for_config = str(Path(UPLOAD_FOLDER_NAME) / safe_filename)
        log(f"Validated input path. Using relative path for config: '{validated_relative_path_for_config}'", "DEBUG")
    except (ValueError, FileNotFoundError) as e:
        log(f"API Error: /start_pipeline invalid 'relative_audio_path': {e}", "WARNING")
        return jsonify({"error": f"Invalid or non-existent audio file: {relative_audio_path_from_form}"}), 400

    # --- parse overige overrides uit het formulier ---
    schema_info = current_app.config.get('SCHEMA_INFO_FOR_UI', {})
    config_overrides = parse_config_overrides_from_form(request.form, schema_info)
    config_overrides["input_audio"] = validated_relative_path_for_config
    log(f"API: Using config overrides for start_pipeline: {config_overrides}", "DEBUG")

    try:
        job_id = job_manager.create_job(initial_config=config_overrides)
        log(f"API: Created job {job_id} via /start_pipeline.", "INFO")
        t = threading.Thread(target=run_part1, args=(job_id, config_overrides), daemon=True)
        t.start()
        log(f"API: Started Part 1 thread for job {job_id}.", "INFO")
        return jsonify({"job_id": job_id}), 202
    except Exception as e:
        log(f"API Error: Failed to create/start job for Part 1: {e}", "CRITICAL")
        log(traceback.format_exc(), "ERROR")
        return jsonify({"error": "Failed to start pipeline job"}), 500


@pipeline_bp.route("/status/<string:job_id>", methods=["GET"])
def get_job_status(job_id):
    log(f"API: Status request for job {job_id}", "DEBUG")
    status_data = job_manager.get_status(job_id)
    if not status_data:
        log(f"API Warning: Status request for non-existent job ID '{job_id}'.", "WARNING")
        abort(404, description=f"Job with ID '{job_id}' not found.")
    try:
        return jsonify(status_data)
    except TypeError as e:
        log(f"API Error: Failed to jsonify job status data for job {job_id}: {e}", "CRITICAL")
        # sanitize non-serializable velden
        safe = {}
        for k,v in status_data.items():
            try:
                json.dumps({k: v})
                safe[k] = v
            except:
                safe[k] = f"<{type(v).__name__} not serializable>"
        log(f"Sanitized status data: {safe}", "ERROR")
        return jsonify({"error": "Internal Server Error", "message": "Failed to serialize job status"}), 500


@pipeline_bp.route("/stop_pipeline/<string:job_id>", methods=["POST"])
def stop_pipeline_route(job_id):
    log(f"API: Received stop request for job {job_id}", "INFO")
    ok = job_manager.request_stop(job_id)
    if ok:
        return jsonify({"message": "Stop request sent."}), 200
    else:
        data = job_manager.get_status(job_id)
        if not data:
            abort(404, description=f"Job '{job_id}' not found.")
        else:
            return jsonify({"message": f"Cannot stop job in status {data.get('status')}."}), 409


# Let op: de route voor het opslaan van de gereviewde speaker‑map
# staat in review_routes.py onder hetzelfde pad
# Route verplaatst: zie src/routes/review_routes.py
