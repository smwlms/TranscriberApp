import os
import sys
import traceback
import logging
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
# Initialisatie & logging
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()

from src.utils.log import setup_logging, log
from src.utils.config_schema import parse_schema_for_ui, PROJECT_ROOT
from src.utils.load_config import load_config
from src.database_logger import initialize_database
from src.constants import AUDIO_FOLDER_NAME, RESULTS_FOLDER_NAME

setup_logging()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
if not any(
    isinstance(h, logging.StreamHandler) and h.stream == sys.stdout
    for h in root_logger.handlers
):
    root_logger.addHandler(console_handler)

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.DEBUG)
werkzeug_logger.propagate = True

if not initialize_database():
    log("Database kon niet worden geïnitialiseerd", "CRITICAL")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Flask‑app & CORS
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
CORS(
    app,
    origins=cors_origins,
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
log(f"CORS geconfigureerd voor: {cors_origins}", "INFO")

# ──────────────────────────────────────────────────────────────────────────────
# Paden & config in app‑context
# ──────────────────────────────────────────────────────────────────────────────
UPLOAD_FOLDER = PROJECT_ROOT / AUDIO_FOLDER_NAME
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME
UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['RESULTS_FOLDER'] = str(RESULTS_FOLDER)
log(f"Upload folder:  {UPLOAD_FOLDER}", "INFO")
log(f"Results folder: {RESULTS_FOLDER}", "INFO")

try:
    schema = parse_schema_for_ui()
    app.config['SCHEMA_INFO_FOR_UI'] = schema
    log("Schema info geladen", "DEBUG")
except Exception as e:
    log(f"Fout bij laden UI schema: {e}", "CRITICAL")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Blueprint‑registratie
# ──────────────────────────────────────────────────────────────────────────────
from src.routes.pipeline_routes import pipeline_bp
from src.routes.review_routes import review_bp
from src.routes.file_routes import file_api_bp
from src.routes.static_routes import static_files_bp
from src.routes.info_routes import info_bp

default_prefix = "/api/v1"
API_PREFIX = os.getenv("API_PREFIX", default_prefix)

app.register_blueprint(pipeline_bp, url_prefix=API_PREFIX)
app.register_blueprint(review_bp,    url_prefix=API_PREFIX)
app.register_blueprint(file_api_bp,  url_prefix=API_PREFIX)
app.register_blueprint(info_bp,      url_prefix=API_PREFIX)
app.register_blueprint(static_files_bp)  # zonder prefix

log(f"Registered API blueprints met prefix {API_PREFIX} en static routes.", "INFO")

# ──────────────────────────────────────────────────────────────────────────────
# Middleware: request‑logging
# ──────────────────────────────────────────────────────────────────────────────
@app.before_request
def log_request_info():
    try:
        data = request.get_json(silent=True)
    except Exception:
        data = None
    log(f"Incoming request: {request.method} {request.path} | Payload: {data}", "DEBUG")

# ──────────────────────────────────────────────────────────────────────────────
# Basispaden
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def health_check():
    log("Health check '/' accessed.", "DEBUG")
    return jsonify({"status": "ok", "message": "Transcriber API is running."})

# Endpoint voor losse TXT‑export (alleen op /transcriptions/.../adjust)
@app.route(f"{API_PREFIX}/transcriptions/<string:file_id>/adjust",
           methods=["POST", "OPTIONS"])
@cross_origin(
    origins=cors_origins,
    methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
def save_transcription_adjustment(file_id):
    """
    Verwacht JSON: { "transcript": "bijgewerkte tekst..." }
    Slaat de aangepaste transcriptie op als .txt (niet gebruikt in review‑flow).
    """
    try:
        payload = request.get_json(force=True)
        adjusted = payload.get("transcript")
        if not adjusted:
            log(f"Geen transcriptie‑tekst ontvangen voor bestand {file_id}", "WARNING")
            return jsonify(error="Geen transcriptie‑tekst ontvangen"), 400

        output_path = Path(app.config['RESULTS_FOLDER']) / f"{file_id}_adjusted.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(adjusted)

        log(f"Aangepaste transcriptie opgeslagen: {output_path}", "INFO")
        return jsonify(status="succes",
                       message="Transcriptie‑aanpassing opgeslagen."), 200
    except Exception as e:
        log(f"Fout bij opslaan transcriptie‑aanpassing voor {file_id}: {e}", "ERROR")
        log(traceback.format_exc(), "ERROR")
        return jsonify(
            error="Internal Server Error",
            message="Kon transcriptie niet opslaan."
        ), 500

# ──────────────────────────────────────────────────────────────────────────────
# Error‑handlers
# ──────────────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    log(f"404 op {request.path}", "WARNING")
    msg = e.description if hasattr(e, 'description') else "Resource not found"
    return jsonify(error="Not Found", message=msg), 404

@app.errorhandler(500)
def internal_error(e):
    log(f"500: {e}", "ERROR")
    log(traceback.format_exc(), "ERROR")
    return jsonify(
        error="Internal Server Error",
        message="Er is een onverwachte fout opgetreden."
    ), 500

@app.errorhandler(405)
def method_not_allowed(e):
    log(f"405: {e}", "WARNING")
    msg = e.description if hasattr(e, 'description') else "Method not allowed"
    headers = {'Allow': ','.join(e.valid_methods or [])}
    return jsonify(error="Method Not Allowed", message=msg), 405, headers

@app.errorhandler(415)
def unsupported_media_type(e):
    log(f"415: {e}", "WARNING")
    msg = e.description if hasattr(e, 'description') else "Unsupported media type"
    return jsonify(error="Unsupported Media Type", message=msg), 415

# ──────────────────────────────────────────────────────────────────────────────
# Start de server
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host  = os.getenv("FLASK_HOST",  "127.0.0.1")
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}
    log(f"Starting Flask app on {host}:{port} with debug={debug}", "INFO")
    app.run(host=host, port=port, debug=debug)
