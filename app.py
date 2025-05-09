# app.py
import os
import traceback
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Laden en initialisatie
load_dotenv()

# Import utilities and constants
from src.utils.log import setup_logging, log
from src.utils.config_schema import parse_schema_for_ui, PROJECT_ROOT
from src.utils.load_config import load_config
from src.database_logger import initialize_database
# Import constants for folder names
from src.constants import AUDIO_FOLDER_NAME, RESULTS_FOLDER_NAME

setup_logging()

if not initialize_database():
    log("Database kon niet worden geïnitialiseerd", "CRITICAL")
    # TODO: Consider sys.exit() here if DB is critical

# --- Flask App ---
app = Flask(__name__)
# CORS vóór blueprint‑registratie
CORS(app, origins=["http://localhost:5173"]) # TODO: Make origins configurable
log("CORS geconfigureerd voor http://localhost:5173", "INFO")

# Folders (Use constants for names)
UPLOAD_FOLDER = PROJECT_ROOT / AUDIO_FOLDER_NAME
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME
UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER) # Store as string for Flask config
app.config['RESULTS_FOLDER'] = str(RESULTS_FOLDER) # Store as string for Flask config
log(f"Upload folder: {UPLOAD_FOLDER}", "INFO")
log(f"Results folder: {RESULTS_FOLDER}", "INFO")

# UI schema
try:
    schema = parse_schema_for_ui()
    app.config['SCHEMA_INFO_FOR_UI'] = schema
    log("Schema info geladen", "DEBUG")
except Exception as e:
    log(f"Fout bij laden UI schema: {e}", "CRITICAL")
    # TODO: Consider sys.exit() here if schema is critical for app startup
    app.config['SCHEMA_INFO_FOR_UI'] = {}

# Blueprints
from src.routes.pipeline_routes import pipeline_bp
from src.routes.review_routes import review_bp
from src.routes.file_routes import file_api_bp
from src.routes.static_routes import static_files_bp
from src.routes.info_routes import info_bp

API_PREFIX = "/api/v1" # Keep API_PREFIX here as it's Flask-specific routing detail
app.register_blueprint(pipeline_bp, url_prefix=API_PREFIX)
app.register_blueprint(review_bp, url_prefix=API_PREFIX)
app.register_blueprint(file_api_bp, url_prefix=API_PREFIX)
app.register_blueprint(info_bp, url_prefix=API_PREFIX)
# Static serve zonder prefix
app.register_blueprint(static_files_bp)
log(f"Registered API blueprints met prefix {API_PREFIX} en static routes.", "INFO")

# Health check
@app.route("/")
def health_check():
    log("Health check '/' accessed.", "DEBUG")
    return jsonify({"status": "ok", "message": "Transcriber API is running."})

# Fouthandlers
@app.errorhandler(404)
def not_found(e):
    log(f"404 op {request.path}", "WARNING")
    # Ensure the error message is JSON serializable
    error_message = str(e) if isinstance(e, Exception) else "Resource not found"
    return jsonify(error="Not Found", message=error_message), 404

@app.errorhandler(500)
def internal_error(e):
    log(f"500: {e}", "ERROR")
    log(traceback.format_exc(), "ERROR")
    # Return a generic error message, avoid exposing internal details
    return jsonify(error="Internal Server Error", message="An unexpected server error occurred."), 500

@app.errorhandler(405)
def method_not_allowed(e):
    log(f"405: {e}", "WARNING")
    error_message = str(e) if isinstance(e, Exception) else "Method not allowed"
    return jsonify(error="Method Not Allowed", message=error_message), 405, {'Allow': ','.join(e.valid_methods or [])}

@app.errorhandler(415)
def unsupported_media_type(e):
    log(f"415: {e}", "WARNING")
    error_message = str(e) if isinstance(e, Exception) else "Unsupported media type"
    return jsonify(error="Unsupported Media Type", message=error_message), 415

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", 5000))
    # More robust boolean check for debug
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ["1", "true", "yes"]
    log(f"Starting Flask app with debug={debug}", "INFO")
    # Use host='0.0.0.0' if you need to access it from outside localhost,
    # but be mindful of security in production without a proper web server.
    app.run(host=host, port=port, debug=debug)