# src/routes/pipeline_routes.py
import threading
import traceback
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify, abort, current_app
from werkzeug.utils import secure_filename

from src.job_manager import job_manager
from src.pipeline_part1 import run_part1
from src.utils.log import log
from src.utils.route_helpers import parse_config_overrides_from_form
from src.utils.config_schema import PROJECT_ROOT

UPLOAD_FOLDER_NAME = "audio"
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
RESULTS_FOLDER_NAME = "results"
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME

pipeline_bp = Blueprint('pipeline', __name__, url_prefix='/api/v1')

@pipeline_bp.route("/start_pipeline", methods=["POST"])
def start_pipeline_route():
    # --- Unchanged ---
    log("API: Request received for /start_pipeline", "INFO")
    if not request.form: return jsonify({"error": "Missing form data"}), 400
    relative_audio_path_from_form = request.form.get("relative_audio_path")
    if not relative_audio_path_from_form: return jsonify({"error": "Missing 'relative_audio_path'"}), 400
    validated_relative_path_for_config: Optional[str] = None
    try:
        submitted_path = Path(relative_audio_path_from_form)
        safe_filename = secure_filename(submitted_path.name)
        if not safe_filename: raise ValueError("Invalid filename derived from path.")
        abs_path = (UPLOAD_FOLDER / safe_filename).resolve()
        if not abs_path.is_file(): raise FileNotFoundError(f"Audio file '{safe_filename}' not found in upload directory.")
        if not abs_path.is_relative_to(UPLOAD_FOLDER.resolve()): raise ValueError("Security check failed: Resolved path is outside.")
        validated_relative_path_for_config = str(Path(UPLOAD_FOLDER_NAME) / safe_filename)
        log(f"Validated input path. Using relative path for config: '{validated_relative_path_for_config}'", "DEBUG")
    except (ValueError, FileNotFoundError, Exception) as e:
        log(f"API Error: /start_pipeline invalid 'relative_audio_path' ('{relative_audio_path_from_form}'): {e}", "WARNING")
        return jsonify({"error": f"Invalid or non-existent audio file specified: {relative_audio_path_from_form}"}), 400
    schema_info = current_app.config.get('SCHEMA_INFO_FOR_UI', {})
    config_overrides = parse_config_overrides_from_form(request.form, schema_info)
    config_overrides["input_audio"] = validated_relative_path_for_config
    log(f"API: Using config overrides for start_pipeline: {config_overrides}", "DEBUG")
    try:
        job_id = job_manager.create_job(initial_config=config_overrides)
        log(f"API: Created job {job_id} via /start_pipeline.", "INFO")
        pipeline_thread = threading.Thread(target=run_part1, args=(job_id, config_overrides), daemon=True)
        pipeline_thread.start()
        log(f"API: Started Part 1 thread for job {job_id}.", "INFO")
        return jsonify({"job_id": job_id}), 202 # Accepted
    except Exception as e:
        log(f"API Error: Failed to create/start job for Part 1: {e}", "CRITICAL"); log(traceback.format_exc(), "ERROR")
        return jsonify({"error": "Failed to start pipeline job due to internal server error"}), 500

# --- RESTORED get_job_status with <string:job_id> converter ---
@pipeline_bp.route("/status/<string:job_id>", methods=["GET"]) # Use <string:job_id> converter
def get_job_status(job_id):
    """API endpoint to get the status of a specific job, using string converter."""
    log(f"API: Status request for job {job_id} (using string route)", "DEBUG")
    status_data = job_manager.get_status(job_id) # Get data from JobManager

    if status_data:
        try:
            log(f"Attempting to jsonify status_data for job {job_id}. Keys: {list(status_data.keys())}", "DEBUG")
            return jsonify(status_data) # Attempt to return REAL JSON response
        except TypeError as e:
            log(f"API Error: Failed to jsonify job status data for job {job_id}. Error: {e}", "CRITICAL")
            safe_log_data = {}
            for k, v in status_data.items():
                 try: json.dumps({k: v}); safe_log_data[k] = v
                 except TypeError: safe_log_data[k] = f"<{type(v).__name__} - Not Serializable>"
                 except Exception as dump_e: safe_log_data[k] = f"<Error serializing field '{k}': {dump_e}>"
            try: log(f"Problematic status_data (sanitized): {json.dumps(safe_log_data, indent=2)}", "ERROR")
            except Exception as final_dump_e: log(f"Could not dump sanitized status data: {final_dump_e}", "ERROR")
            return jsonify(error="Internal Server Error", message="Failed to serialize job status data."), 500
        except Exception as e:
             log(f"API Error: Unexpected error during jsonify for job {job_id}: {e}", "CRITICAL"); log(traceback.format_exc(), "ERROR")
             return jsonify(error="Internal Server Error", message="Unexpected error processing job status."), 500
    else:
        log(f"API Warning: Status request for non-existent job ID '{job_id}'.", "WARNING")
        abort(404, description=f"Job with ID '{job_id}' not found.")


@pipeline_bp.route("/stop_pipeline/<job_id>", methods=["POST"])
def stop_pipeline_route(job_id):
    # --- Unchanged ---
    log(f"API: Received stop request for job {job_id}", "INFO")
    stop_requested_ok = job_manager.request_stop(job_id)
    if stop_requested_ok:
        log(f"API: Stop request processed successfully for job {job_id}.", "INFO"); return jsonify({"message": "Stop request sent successfully."}), 200
    else:
        status_data = job_manager.get_status(job_id);
        if not status_data: log(f"API Warning: Stop request for non-existent job ID '{job_id}'.", "WARNING"); abort(404, description=f"Job with ID '{job_id}' not found.")
        else: current_status = status_data.get('status', 'UNKNOWN'); log(f"API Info: Stop request ignored for job {job_id} (Status: {current_status}).", "INFO"); return jsonify({"message": f"Job cannot be stopped in its current state (Status: {current_status})."}), 409

# --- End of src/routes/pipeline_routes.py ---