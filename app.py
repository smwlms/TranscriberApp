import os
import traceback
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Laden en initialisatie
load_dotenv()
from src.utils.log import setup_logging, log
setup_logging()

from src.database_logger import initialize_database
if not initialize_database():
    log("Database kon niet worden geïnitialiseerd", "CRITICAL")

from src.utils.config_schema import parse_schema_for_ui, PROJECT_ROOT
from src.utils.load_config import load_config

# --- Flask App ---
app = Flask(__name__)
# CORS vóór blueprint‑registratie
CORS(app, origins=["http://localhost:5173"])
log("CORS geconfigureerd voor http://localhost:5173", "INFO")

# Folders
UPLOAD_FOLDER = PROJECT_ROOT / "audio"
RESULTS_FOLDER = PROJECT_ROOT / "results"
UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['RESULTS_FOLDER'] = str(RESULTS_FOLDER)
log(f"Upload folder: {UPLOAD_FOLDER}", "INFO")
log(f"Results folder: {RESULTS_FOLDER}", "INFO")

# UI schema
try:
    schema = parse_schema_for_ui()
    app.config['SCHEMA_INFO_FOR_UI'] = schema
    log("Schema info geladen", "DEBUG")
except Exception as e:
    log(f"Fout bij laden UI schema: {e}", "CRITICAL")
    app.config['SCHEMA_INFO_FOR_UI'] = {}

# Blueprints
from src.routes.pipeline_routes import pipeline_bp
from src.routes.review_routes import review_bp
from src.routes.file_routes import file_api_bp
from src.routes.static_routes import static_files_bp
from src.routes.info_routes import info_bp

API_PREFIX = "/api/v1"
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
    return jsonify(error="Not Found", message=str(e)), 404

@app.errorhandler(500)
def internal_error(e):
    log(f"500: {e}", "ERROR")
    log(traceback.format_exc(), "ERROR")
    return jsonify(error="Internal Server Error"), 500

@app.errorhandler(405)
def method_not_allowed(e):
    log(f"405: {e}", "WARNING")
    return jsonify(error="Method Not Allowed"), 405, {'Allow': ','.join(e.valid_methods or [])}

@app.errorhandler(415)
def unsupported_media_type(e):
    log(f"415: {e}", "WARNING")
    return jsonify(error="Unsupported Media Type"), 415

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ["1","true"]
    app.run(host=host, port=port, debug=debug)