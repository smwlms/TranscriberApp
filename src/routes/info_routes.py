# src/routes/info_routes.py
import traceback
from flask import Blueprint, jsonify

# Import utilities
from src.utils.log import log
from src.utils.config_schema import parse_schema_for_ui
from src.utils.llm import get_local_models
# --- Import the device detection utility ---
# Note: Ensure this import path is correct relative to your structure
# Assuming _get_compute_device is still accessible via transcriber for now
# A cleaner approach might be to move _get_compute_device to a common util module
try:
    from src.transcriber import _get_compute_device
except ImportError:
    log("Could not import _get_compute_device from src.transcriber in info_routes. Using fallback 'cpu'.", "ERROR")
    # Provide a fallback if import fails, though this indicates a potential structure issue
    def _get_compute_device(): return "cpu"

# Define the Blueprint object
info_bp = Blueprint('info', __name__, url_prefix='/api/v1')

# --- Info Routes ---

@info_bp.route("/config_info", methods=["GET"])
def get_config_info():
    """
    API endpoint that returns UI-friendly schema information,
    locally available Ollama models, and the detected compute device.
    """
    log("API: Request received for /config_info", "INFO")
    response_data = {"schema": {}, "available_models": [], "detected_device": "unknown"}
    try:
        # Get the parsed schema for the UI
        schema_info = parse_schema_for_ui()
        if not schema_info:
             log("API Error: Failed to load/parse schema for /config_info.", "ERROR")
             # Still try to return models and device info if possible
             response_data["schema"] = {} # Indicate schema loading failed
        else:
             response_data["schema"] = schema_info

        # Get available local LLM models
        local_models = get_local_models()
        response_data["available_models"] = local_models

        # --- Get detected compute device ---
        try:
            detected_device = _get_compute_device() # Call the utility function
            response_data["detected_device"] = detected_device
            log(f"Detected compute device for config info: {detected_device}", "DEBUG")
        except Exception as device_err:
             log(f"API Error: Failed to detect compute device: {device_err}", "ERROR")
             response_data["detected_device"] = "error" # Indicate error during detection

        # --- Return combined data ---
        log(f"API: Returning config info - Schema fields: {len(response_data['schema'])}, Models: {len(response_data['available_models'])}, Device: {response_data['detected_device']}", "DEBUG")
        return jsonify(response_data)

    except Exception as e:
        # Catch unexpected errors during info gathering
        log(f"API Error: Unexpected error while gathering config info: {e}", "CRITICAL")
        log(traceback.format_exc(), "ERROR")
        # Return 500 but try to include any partial data gathered if helpful
        response_data["error"] = "Failed to retrieve complete server configuration info."
        return jsonify(response_data), 500

# --- End of src/routes/info_routes.py ---