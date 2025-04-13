# src/routes/info_routes.py
import traceback
from flask import Blueprint, jsonify

# Import utilities needed to fetch the info
from src.utils.log import log
# Import function to parse the schema into UI-friendly format
from src.utils.config_schema import parse_schema_for_ui
# Import function to get local Ollama models
from src.utils.llm import get_local_models

# Define the Blueprint object for informational endpoints
info_bp = Blueprint(
    'info',           # Blueprint name
    __name__,
    # url_prefix='/api/info' # Optional URL prefix
)

# --- Info Routes ---

@info_bp.route("/config_info", methods=["GET"])
def get_config_info():
    """
    API endpoint that returns configuration schema information formatted for UI use
    and a list of currently available local Ollama models.
    """
    log("API: Request received for /config_info", "INFO")
    try:
        # Call the utility function to parse the schema YAML file
        # This function handles loading and parsing the schema itself.
        schema_info = parse_schema_for_ui()
        # Basic check if schema parsing worked
        if not schema_info:
             log("API Error: Failed to load or parse schema information for /config_info.", "ERROR")
             # Return 500 if schema loading fails, as UI relies on it
             return jsonify({"error": "Could not retrieve configuration schema information from server"}), 500

        # Call the utility function to get the list of local Ollama models
        local_models = get_local_models()
        # An empty list of models is valid, so no specific error check needed here.

        log(f"API: Returning config info. Schema fields count: {len(schema_info)}, Available Ollama models count: {len(local_models)}", "DEBUG")

        # Combine the schema info and model list into a single JSON response
        return jsonify({
            "schema": schema_info,          # Parsed schema for UI elements
            "available_models": local_models # List of model names (e.g., ["llama3:8b", "mistral"])
            })

    except Exception as e:
        # Catch any unexpected errors during the process
        log(f"API Error: Unexpected error while gathering config info: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log full traceback for debugging
        # Return 500 Internal Server Error
        return jsonify({"error": "Could not retrieve server configuration information due to an internal error"}), 500

# --- End of src/routes/info_routes.py ---