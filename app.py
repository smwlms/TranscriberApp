# File: app.py
import os
import traceback
import time
from pathlib import Path
from flask import Flask, jsonify, request
from dotenv import load_dotenv
load_dotenv() # Load environment variables early

# Setup logging and DB first
from src.utils.log import setup_logging, log
setup_logging() # Configure logging based on config.yaml/defaults
from src.database_logger import initialize_database
db_initialized = initialize_database()
if not db_initialized:
    log("Database could not be initialized. DB logging might fail.", "CRITICAL")

# Import PROJECT_ROOT and schema parser utility
from src.utils.config_schema import parse_schema_for_ui, PROJECT_ROOT
# job_manager is used via blueprints, no direct import needed here

# --- Create Flask App Instance ---
log("Initializing Flask application...", "INFO")
app = Flask(__name__) # Core Flask app instance

# --- Application Configuration ---
UPLOAD_FOLDER_NAME = "audio"
RESULTS_FOLDER_NAME = "results"
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME
try:
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
    app.config['RESULTS_FOLDER'] = str(RESULTS_FOLDER)
    log(f"Upload folder: {app.config['UPLOAD_FOLDER']}", "INFO")
    log(f"Results folder: {app.config['RESULTS_FOLDER']}", "INFO")
except Exception as e:
     log(f"CRITICAL: Failed to create/access essential folders (upload/results): {e}", "CRITICAL")

# --- Load and Store Schema Info in App Config ---
try:
    log("Loading UI schema info...", "INFO")
    schema_info = parse_schema_for_ui()
    if not schema_info: log("Schema info could not be loaded/parsed.", "ERROR")
    app.config['SCHEMA_INFO_FOR_UI'] = schema_info
    log("Schema info loaded into app config.", "DEBUG")
except Exception as e:
     log(f"CRITICAL: Failed to load schema info at startup: {e}", "CRITICAL")
     app.config['SCHEMA_INFO_FOR_UI'] = {}


# --- Import and Register Blueprints ---
log("Registering API blueprints...", "INFO")
from src.routes.pipeline_routes import pipeline_bp
from src.routes.review_routes import review_bp
# *** MODIFICATION: Import the renamed/split blueprints ***
from src.routes.file_routes import file_api_bp # Contains only /upload_audio API
from src.routes.static_routes import static_files_bp # Contains /audio/ and /results/ static routes
from src.routes.info_routes import info_bp

API_PREFIX = "/api/v1"

# --- Blueprint Registration (Corrected based on split) ---
# Register API routes WITH prefix
app.register_blueprint(pipeline_bp, url_prefix=API_PREFIX)
app.register_blueprint(review_bp, url_prefix=API_PREFIX)
app.register_blueprint(file_api_bp, url_prefix=API_PREFIX) # Register API part with prefix
app.register_blueprint(info_bp, url_prefix=API_PREFIX)

# Register static file serving routes WITHOUT prefix
app.register_blueprint(static_files_bp) # Register static part without prefix
# ------------------------------------
# Log message reflects the intended structure
log(f"Registered API blueprints with prefix: {API_PREFIX}. Registered static file serving blueprint.", "INFO")


# --- Basic Error Handling & Root Endpoint ---
@app.route("/")
def health_check():
     """Basic health check endpoint."""
     log("Health check endpoint '/' accessed.", "DEBUG")
     return jsonify({"status": "ok", "message": "Transcriber API is running."})

# --- Error Handlers --- (Remain unchanged)
@app.errorhandler(500)
def handle_internal_error(error):
    log(f"Internal Server Error (500): {error}", "ERROR"); log(traceback.format_exc(), "ERROR")
    return jsonify(error="Internal Server Error", message="An unexpected error occurred."), 500
@app.errorhandler(404)
def handle_not_found_error(error):
    log(f"Not Found Error (404): Path '{request.path}'. Description: {getattr(error, 'description', 'N/A')}", "WARNING")
    return jsonify(error="Not Found", message="The requested API endpoint or resource was not found."), 404
@app.errorhandler(405)
def handle_method_not_allowed(error):
    log(f"Method Not Allowed (405): Method '{request.method}' not allowed for path '{request.path}'.", "WARNING")
    response = jsonify(error="Method Not Allowed", message="The method specified is not allowed for the requested URL.")
    if hasattr(error, 'valid_methods') and isinstance(error.valid_methods, (list, tuple)): response.headers['Allow'] = ', '.join(error.valid_methods)
    return response, 405
@app.errorhandler(415)
def handle_unsupported_media_type(error):
    log(f"Unsupported Media Type (415): Request for '{request.path}' had unsupported Content-Type '{request.mimetype}'.", "WARNING")
    return jsonify(error="Unsupported Media Type", message="The request content type is not supported by this endpoint."), 415

# --- Main Execution Guard --- (Remains unchanged)
if __name__ == "__main__":
    log("Starting Flask development server directly...", "INFO")
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5001))
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() in ['true', '1', 'yes']
    log(f"Running Flask app on http://{host}:{port}/ (Debug mode: {debug_mode})", "INFO")
    app.run(host=host, port=port, debug=debug_mode)

# --- End of app.py ---