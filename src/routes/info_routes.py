# File: src/routes/info_routes.py

import traceback
from flask import Blueprint, jsonify

# --- Utility and App Logic Imports ---
from src.utils.log import log
from src.utils.config_schema import parse_schema_for_ui # Keep this import
from src.utils.llm import get_local_models             # Keep this import

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
info_bp = Blueprint('info_bp', __name__, url_prefix='/api/v1')

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

# --- End of src/routes/info_routes.py ---