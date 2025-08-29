# File: src/routes/info_routes.py

import traceback
from flask import Blueprint, jsonify, request

# --- Utility and App Logic Imports ---
from src.utils.log import log
from src.utils.config_schema import parse_schema_for_ui # Keep this import
from src.utils.llm import get_local_models             # Keep this import
from src.utils.config_schema import PROJECT_ROOT
from src.constants import AUDIO_FOLDER_NAME, RESULTS_FOLDER_NAME, TRANSCRIPTS_FOLDER_NAME
from src.database_logger import initialize_database, get_db_path

# *** CORRECTED IMPORT for compute device ***
# Import the renamed function from the correct location in core module
try:
    from src.core.model_loader import get_compute_device
    DEVICE_DETECTION_AVAILABLE = True
except ImportError:
    log("Could not import get_compute_device from src.core.model_loader in info_routes. Device detection disabled for this route.", "ERROR")
    # Provide a fallback if import fails
    def get_compute_device(): return "import_failed"
    DEVICE_DETECTION_AVAILABLE = False

# Define the Blueprint object
# Make sure the prefix '/api/v1' is correct based on how it's registered in app.py
# If app.py already adds the prefix when registering, remove it here. Assuming prefix is needed here:
info_bp = Blueprint('info_bp', __name__)

# --- Info Routes ---

@info_bp.route("/config_info", methods=["GET"])
def get_config_info_route():
    """
    API endpoint that returns UI-friendly schema information,
    locally available Ollama models, and the detected compute device.
    """
    log("API: Request received for /config_info", "INFO")
    # Initialize with default/error values
    response_data = {
        "schema": {},
        "available_models": [],
        "detected_device": "unknown" # Default until detected
        }
    status_code = 200 # Default OK status

    try:
        # 1. Get the parsed schema for the UI
        try:
            schema_info = parse_schema_for_ui()
            if not schema_info:
                 log("API Warning: Failed to load/parse schema for /config_info.", "WARNING")
                 response_data["schema"] = {"error": "Schema not available"} # Indicate specific issue
            else:
                 response_data["schema"] = schema_info
        except Exception as schema_err:
             log(f"API Error: Exception during schema parsing: {schema_err}", "ERROR")
             log(traceback.format_exc(), "DEBUG")
             response_data["schema"] = {"error": "Failed to process schema"}

        # 2. Get available local LLM models
        try:
            local_models = get_local_models()
            response_data["available_models"] = local_models
        except Exception as llm_err:
            log(f"API Error: Exception during get_local_models: {llm_err}", "ERROR")
            log(traceback.format_exc(), "DEBUG")
            response_data["available_models"] = [] # Return empty list on error

        # 3. Get detected compute device
        if DEVICE_DETECTION_AVAILABLE:
            try:
                # --- USE CORRECTED FUNCTION CALL ---
                detected_device = get_compute_device() # Call the correctly imported function
                response_data["detected_device"] = detected_device
                log(f"Detected compute device for config info: {detected_device}", "DEBUG")
            except Exception as device_err:
                 log(f"API Error: Exception during get_compute_device call: {device_err}", "ERROR")
                 log(traceback.format_exc(), "DEBUG")
                 response_data["detected_device"] = "error_detecting" # Indicate error during detection
        else:
             response_data["detected_device"] = "detection_unavailable" # Indicate if import failed

        # --- Return combined data ---
        log(f"API: Returning config info - Schema fields: {len(response_data.get('schema',{}))}, Models: {len(response_data.get('available_models',[]))}, Device: {response_data.get('detected_device','N/A')}", "DEBUG")
        # Fall through to return jsonify(response_data), status_code

    except Exception as e:
        # Catch unexpected errors during the overall info gathering process
        log(f"API Error: Unexpected critical error while gathering config info: {e}", "CRITICAL")
        log(traceback.format_exc(), "ERROR")
        # Return 500 status code and include an error message
        response_data["error"] = "Failed to retrieve complete server configuration info due to an internal error."
        status_code = 500

    return jsonify(response_data), status_code


@info_bp.route("/healthz", methods=["GET"])
def healthz_route():
    """
    Lightweight health endpoint.
    - liveness: server reachable
    - readiness: schema parse, folder write perms, DB init
    Optional query `deep=true` adds an Ollama/models check and device detect.
    """
    deep = str(request.args.get("deep", "false")).lower() in ("1", "true", "yes", "y")

    checks = {}
    status = "ok"

    # 1) Schema parse
    try:
        _s = parse_schema_for_ui()
        checks["schema"] = bool(_s)
        if not _s:
            status = "degraded"
    except Exception as e:
        log(f"/healthz: schema parse error: {e}", "ERROR")
        checks["schema"] = False
        status = "error"

    # 2) Folders writable
    def _writable(rel_name):
        try:
            p = (PROJECT_ROOT / rel_name).resolve()
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".healthz.tmp"
            with open(test, "w", encoding="utf-8") as f:
                f.write("ok")
            test.unlink(missing_ok=True)
            return True
        except Exception as we:
            log(f"/healthz: write test failed for {rel_name}: {we}", "ERROR")
            return False

    checks["audio_writable"] = _writable(AUDIO_FOLDER_NAME)
    checks["results_writable"] = _writable(RESULTS_FOLDER_NAME)
    checks["transcripts_writable"] = _writable(TRANSCRIPTS_FOLDER_NAME)
    if not all((checks["audio_writable"], checks["results_writable"], checks["transcripts_writable"])):
        status = "degraded" if status == "ok" else status

    # 3) DB readiness
    try:
        db_ok = initialize_database(get_db_path())
        checks["database_ready"] = bool(db_ok)
        if not db_ok:
            status = "degraded" if status == "ok" else status
    except Exception as dbe:
        log(f"/healthz: DB init error: {dbe}", "ERROR")
        checks["database_ready"] = False
        status = "error"

    # 4) Optional deep check: available models + device
    if deep:
        try:
            checks["available_models_count"] = len(get_local_models() or [])
        except Exception as me:
            log(f"/healthz: model discovery failed: {me}", "WARNING")
            checks["available_models_count"] = 0
            status = "degraded" if status == "ok" else status
        try:
            dev = get_compute_device() if DEVICE_DETECTION_AVAILABLE else "unknown"
            checks["device"] = dev
        except Exception as de:
            log(f"/healthz: device detection failed: {de}", "WARNING")
            checks["device"] = "error"
            status = "degraded" if status == "ok" else status

    return jsonify({
        "status": status,
        "checks": checks
    }), 200 if status in ("ok", "degraded") else 500

# --- End of src/routes/info_routes.py ---
