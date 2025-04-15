# app.py
import os
import traceback
import time
from pathlib import Path
from flask import Flask, jsonify, request # Keep request for error handlers
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
    # Store parsed schema in app config for access in routes
    app.config['SCHEMA_INFO_FOR_UI'] = schema_info
    log("Schema info loaded into app config.", "DEBUG")
except Exception as e:
     log(f"CRITICAL: Failed to load schema info at startup: {e}", "CRITICAL")
     app.config['SCHEMA_INFO_FOR_UI'] = {} # Ensure key exists even on failure


# --- Import and Register Blueprints ---
log("Registering API blueprints...", "INFO")
from src.routes.pipeline_routes import pipeline_bp
from src.routes.review_routes import review_bp
from src.routes.file_routes import file_bp
from src.routes.info_routes import info_bp

API_PREFIX = "/api/v1"
# Register each blueprint on its own line with the correct prefix
app.register_blueprint(pipeline_bp, url_prefix=API_PREFIX)
app.register_blueprint(review_bp, url_prefix=API_PREFIX)
app.register_blueprint(file_bp, url_prefix=API_PREFIX) # Corrected: file_bp now uses prefix
app.register_blueprint(info_bp, url_prefix=API_PREFIX)
log(f"Registered API blueprints (Info, Pipeline, Review, Files) with prefix: {API_PREFIX}", "INFO") # Corrected log message


# --- Basic Error Handling & Root Endpoint ---
@app.route("/")
def health_check():
     """Basic health check endpoint."""
     log("Health check endpoint '/' accessed.", "DEBUG")
     return jsonify({"status": "ok", "message": "Transcriber API is running."})

# --- Error Handlers ---
@app.errorhandler(500)
def handle_internal_error(error):
    """Handles unexpected internal server errors."""
    log(f"Internal Server Error (500): {error}", "ERROR")
    log(traceback.format_exc(), "ERROR")
    return jsonify(error="Internal Server Error", message="An unexpected error occurred on the server."), 500

@app.errorhandler(404)
def handle_not_found_error(error):
     """Handles requests to non-existent routes."""
     log(f"Not Found Error (404): Path '{request.path}'. Description: {getattr(error, 'description', 'N/A')}", "WARNING")
     return jsonify(error="Not Found", message="The requested API endpoint or resource was not found."), 404

@app.errorhandler(405)
def handle_method_not_allowed(error):
     """Handles requests with an HTTP method not allowed for the route."""
     log(f"Method Not Allowed (405): Method '{request.method}' not allowed for path '{request.path}'.", "WARNING")
     response = jsonify(error="Method Not Allowed", message="The method specified in the Request-Line is not allowed for the resource identified by the Request-URI.")
     if hasattr(error, 'valid_methods') and isinstance(error.valid_methods, (list, tuple)):
         response.headers['Allow'] = ', '.join(error.valid_methods)
     return response, 405

@app.errorhandler(415)
def handle_unsupported_media_type(error):
    """Handles requests with an unsupported Content-Type."""
    log(f"Unsupported Media Type (415): Request for '{request.path}' had unsupported Content-Type '{request.mimetype}'.", "WARNING")
    return jsonify(error="Unsupported Media Type", message="The server cannot process the request because the payload format is not supported."), 415


# --- Main Execution Guard ---
if __name__ == "__main__":
    log("Starting Flask development server directly...", "INFO")
    host = os.environ.get("FLASK_HOST", "0.0.0.0") # Listen on all interfaces by default
    port = int(os.environ.get("FLASK_PORT", 5001)) # Default port 5001
    # Debug mode controlled by FLASK_DEBUG env var, defaults to True for development
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() in ['true', '1', 'yes']
    log(f"Running Flask app on http://{host}:{port}/ (Debug mode: {debug_mode})", "INFO")
    # use_reloader is implicitly True when debug=True
    app.run(host=host, port=port, debug=debug_mode)

# --- End of app.py ---