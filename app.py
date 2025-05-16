print("<<<<< LOADING src/app.py - VERSION CHECK (DATUM/TIJD OF VERSIENUMMER) >>>>>")
import os
import sys
import traceback # Goed voor error logging
import logging
from pathlib import Path

from flask import Flask, jsonify, request # request is gebruikt in before_request en save_transcription_adjustment
from flask_cors import CORS, cross_origin # cross_origin is specifiek gebruikt op één route
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
# Initialisatie & logging
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()

# Deze imports moeten NA load_dotenv() komen als ze .env variabelen gebruiken bij import-time
from src.utils.log import setup_logging, log
from src.utils.config_schema import parse_schema_for_ui, PROJECT_ROOT
from src.utils.load_config import load_config # Wordt niet direct gebruikt in app.py, maar waarschijnlijk in andere modules
from src.database_logger import initialize_database
from src.constants import AUDIO_FOLDER_NAME, RESULTS_FOLDER_NAME 

# Roep setup_logging zo vroeg mogelijk aan
# setup_logging() # JE HAD DIT HIER AL, IS GOED

# De custom console_handler setup hieronder is prima, maar setup_logging()
# doet mogelijk al iets vergelijkbaars. Zorg dat ze niet conflicteren.
# Als setup_logging() al een root logger configureert, is het duplicatie.
# Voor nu laat ik het staan, maar check de implementatie van setup_logging().
# ----- BEGIN VERVANGENDE/AANVULLENDE LOGGING SETUP -----
# Verwijder of pas aan als setup_logging() dit al dekt.
# Het is beter om de logging configuratie op één plek te centraliseren (idealiter in setup_logging).
# Als setup_logging() de root logger al configureert, zijn de volgende regels mogelijk overbodig
# of kunnen ze de configuratie van setup_logging() overschrijven.

# logger = logging.getLogger() # Haal de root logger
# logger.setLevel(logging.DEBUG) # Zet het niveau voor de root logger

# # Voeg de custom console handler toe ALS deze nog niet bestaat (of als je specifieke formatting wilt)
# # Dit is een beetje complex om te checken; setup_logging() zou dit moeten beheren.
# if not any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout for h in logger.handlers):
#     console_handler = logging.StreamHandler(sys.stdout)
#     console_handler.setLevel(logging.DEBUG) # Of INFO, afhankelijk van wat je wilt zien
#     # Gebruik de formatter die je al had, of een standaard een.
#     console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')) # Voeg %(name)s toe
#     logger.addHandler(console_handler)

# # Werkzeug logger (voor Flask's eigen request logs)
# werkzeug_logger = logging.getLogger('werkzeug')
# werkzeug_logger.setLevel(logging.INFO) # Zet op INFO om niet te veel ruis te hebben, DEBUG kan ook
# werkzeug_logger.propagate = False # Voorkom dubbele logging als root ook werkzeug logs zou vangen
# # Voeg een handler toe aan werkzeug logger als je specifieke formatting wilt, anders erft het van root.
# if not werkzeug_logger.handlers: # Alleen toevoegen als het nog geen handlers heeft
#     werkzeug_console_handler = logging.StreamHandler(sys.stdout)
#     werkzeug_console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s (werkzeug)'))
#     werkzeug_logger.addHandler(werkzeug_console_handler)

# Gebruik je eigen setup_logging(), en zorg dat die de root en werkzeug naar wens instelt.
# De code die je had:
setup_logging() # Deze zou de root logger en werkzeug idealiter moeten configureren.

# De volgende custom handler is waarschijnlijk overbodig als setup_logging() goed werkt.
# Het kan zelfs conflicteren of de output van setup_logging() veranderen.
# console_handler = logging.StreamHandler(sys.stdout)
# console_handler.setLevel(logging.DEBUG)
# console_handler.setFormatter(
#     logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
# )
# root_logger = logging.getLogger()
# root_logger.setLevel(logging.DEBUG) # Dit forceert de root logger naar DEBUG
# if not any(
#     isinstance(h, logging.StreamHandler) and h.stream == sys.stdout
#     for h in root_logger.handlers
# ):
#     root_logger.addHandler(console_handler) # Dit voegt NOG een handler toe als setup_logging al een console handler heeft

# werkzeug_logger = logging.getLogger('werkzeug')
# werkzeug_logger.setLevel(logging.DEBUG) # Forceert werkzeug naar DEBUG
# werkzeug_logger.propagate = True # Laat werkzeug logs ook naar root logger gaan
# ----- EINDE AANBEVELING LOGGING SETUP -----

if not initialize_database():
    log("Database kon niet worden geïnitialiseerd. Afsluiten.", "CRITICAL") # Duidelijkere melding
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Flask‑app & CORS
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# CORS Configuratie
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
# Zorg ervoor dat er geen lege strings in de lijst komen als de .env variabele leeg is of alleen komma's bevat.
cors_origins_list = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

if not cors_origins_list: # Fallback als de lijst leeg is na parsen
    log("CORS_ORIGINS .env variabele is leeg of onjuist geformatteerd. Fallback naar default 'http://localhost:5173'.", "WARNING")
    cors_origins_list = ["http://localhost:5173"]

CORS(
    app,
    origins=cors_origins_list, # Gebruik de geparste lijst
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], # Voeg eventueel PUT, DELETE toe als je die gebruikt
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"], # Voeg gangbare headers toe
    supports_credentials=True, # Als je cookies/auth headers meeneemt
    expose_headers=["Content-Length", "X-My-Custom-Header"] # Optioneel, als je custom headers exposeert
)
log(f"CORS geconfigureerd voor origins: {cors_origins_list}", "INFO")

# ──────────────────────────────────────────────────────────────────────────────
# Paden & config in app‑context
# ──────────────────────────────────────────────────────────────────────────────
# Definieer paden met Path objecten voor consistentie
UPLOAD_FOLDER_PATH = PROJECT_ROOT / AUDIO_FOLDER_NAME
RESULTS_FOLDER_PATH = PROJECT_ROOT / RESULTS_FOLDER_NAME

try:
    UPLOAD_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
    RESULTS_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
except OSError as e:
    log(f"Kritieke fout bij aanmaken mappen: {e}", "CRITICAL")
    sys.exit(1)

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER_PATH)
app.config['RESULTS_FOLDER'] = str(RESULTS_FOLDER_PATH)
log(f"Upload folder ingesteld: {app.config['UPLOAD_FOLDER']}", "INFO")
log(f"Results folder ingesteld: {app.config['RESULTS_FOLDER']}", "INFO")

try:
    schema = parse_schema_for_ui()
    app.config['SCHEMA_INFO_FOR_UI'] = schema
    log("Schema info voor UI succesvol geladen.", "DEBUG")
except Exception as e:
    log(f"Kritieke fout bij laden UI schema: {e}", "CRITICAL")
    log(traceback.format_exc(), "ERROR") # Log volledige traceback
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Blueprint‑registratie
# ──────────────────────────────────────────────────────────────────────────────
# Plaats imports dichter bij waar ze gebruikt worden, of groepeer ze bovenaan.
# Voor nu is dit prima.
from src.routes.pipeline_routes import pipeline_bp
from src.routes.review_routes import review_bp
from src.routes.file_routes import file_api_bp
from src.routes.static_routes import static_files_bp # Voor het serveren van audio/results
from src.routes.info_routes import info_bp       # Voor /config_info etc.

default_prefix = "/api/v1"
API_PREFIX = os.getenv("API_PREFIX", default_prefix).rstrip('/') # Verwijder trailing slash indien aanwezig

app.register_blueprint(pipeline_bp, url_prefix=API_PREFIX)
app.register_blueprint(review_bp,    url_prefix=API_PREFIX)
app.register_blueprint(file_api_bp,  url_prefix=API_PREFIX)
app.register_blueprint(info_bp,      url_prefix=API_PREFIX)
app.register_blueprint(static_files_bp)  # Deze serveert /audio en /results, meestal zonder prefix

log(f"API blueprints geregistreerd met prefix '{API_PREFIX}'. Static routes ook geregistreerd.", "INFO")

# ──────────────────────────────────────────────────────────────────────────────
# Middleware: request‑logging
# ──────────────────────────────────────────────────────────────────────────────
@app.before_request
def log_request_info_detailed(): # Naam veranderd voor duidelijkheid
    # Log niet voor OPTIONS requests (CORS preflight) om logs schoner te houden
    if request.method == 'OPTIONS':
        return

    payload_summary = "No JSON payload or not applicable"
    if request.is_json:
        try:
            data = request.get_json()
            # Toon alleen keys of een deel van de payload om logs niet te overspoelen
            if isinstance(data, dict):
                payload_summary = f"JSON keys: {list(data.keys())}"
            elif isinstance(data, list):
                payload_summary = f"JSON list with {len(data)} items"
            else:
                payload_summary = "JSON payload (non-dict/list)"
        except Exception:
            payload_summary = "Error parsing JSON payload"
    elif request.form:
        payload_summary = f"Form keys: {list(request.form.keys())}"
    elif request.data:
        payload_summary = f"Raw data: {len(request.data)} bytes"

    log(f"Request: {request.method} {request.path} (Remote: {request.remote_addr}) | {payload_summary}", "DEBUG")

# ──────────────────────────────────────────────────────────────────────────────
# Basispaden
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
@cross_origin(origins=cors_origins_list) # Voeg cross_origin toe als je dit direct vanuit browser wilt testen
def health_check():
    log("Health check '/' endpoint accessed.", "DEBUG")
    return jsonify({"status": "ok", "message": "Transcriber API is running."})

# Endpoint voor losse TXT‑export - Deze is specifiek en lijkt buiten de hoofd API flow
# De @cross_origin decorator hier is redundant als de globale CORS(app, ...) al alles dekt.
# Echter, als je fijnmazige controle wilt per route, kan het nuttig zijn.
# Zorg dat de origins hier overeenkomen met de globale instelling of specifieker zijn.
@app.route(f"{API_PREFIX}/transcriptions/<string:file_id>/adjust", methods=["POST", "OPTIONS"])
# @cross_origin(...) # Waarschijnlijk niet nodig als globale CORS goed is ingesteld
def save_transcription_adjustment(file_id):
    # ... (code blijft hetzelfde) ...
    pass # Placeholder om de structuur te behouden

# ──────────────────────────────────────────────────────────────────────────────
# Error‑handlers
# ──────────────────────────────────────────────────────────────────────────────
# Deze error handlers zijn goed. Ze vangen errors en retourneren JSON.
# Zorg ervoor dat CORS headers ook worden toegevoegd aan deze error responses.
# Flask-CORS zou dit automatisch moeten doen voor routes die onder zijn beheer vallen,
# maar voor handmatig geaborteerde requests of exceptions die Flask zelf afhandelt,
# kan het nodig zijn om response objecten te maken en headers handmatig te zetten.
# Echter, meestal werkt het out-of-the-box.

@app.errorhandler(404)
def not_found_error(e): # Naam veranderd om conflict met variabele e te vermijden
    log(f"404 Not Found: {request.path} - {e.description if hasattr(e, 'description') else str(e)}", "WARNING")
    return jsonify(error="Not Found", message=e.description if hasattr(e, 'description') else "The requested resource was not found."), 404

@app.errorhandler(500)
def internal_server_error(e): # Naam veranderd
    original_exception = getattr(e, "original_exception", e) # Probeer de originele exceptie te krijgen
    log(f"500 Internal Server Error: {request.path} - {original_exception}", "ERROR")
    log(traceback.format_exc(), "ERROR") # Log volledige traceback
    return jsonify(error="Internal Server Error", message="An unexpected error occurred on the server."), 500

@app.errorhandler(405)
def method_not_allowed_error(e): # Naam veranderd
    log(f"405 Method Not Allowed: {request.method} on {request.path} - Valid methods: {e.valid_methods if hasattr(e, 'valid_methods') else 'N/A'}", "WARNING")
    headers = {'Allow': ', '.join(e.valid_methods)} if hasattr(e, 'valid_methods') and e.valid_methods else {}
    return jsonify(error="Method Not Allowed", message="The method is not allowed for the requested URL."), 405, headers

@app.errorhandler(415)
def unsupported_media_type_error(e): # Naam veranderd
    log(f"415 Unsupported Media Type: {request.path} - {e.description if hasattr(e, 'description') else str(e)}", "WARNING")
    return jsonify(error="Unsupported Media Type", message=e.description if hasattr(e, 'description') else "The request entity has a media type which the server or resource does not support."), 415

@app.errorhandler(403) # Voeg een handler toe voor 403 Forbidden
def forbidden_error(e):
    log(f"403 Forbidden: {request.path} - {e.description if hasattr(e, 'description') else str(e)}", "WARNING")
    return jsonify(error="Forbidden", message=e.description if hasattr(e, 'description') else "You don't have the permission to access the requested resource."), 403

# ──────────────────────────────────────────────────────────────────────────────
# Start de server
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    flask_host  = os.getenv("FLASK_HOST",  "127.0.0.1")
    # Valideer poortnummer
    try:
        flask_port  = int(os.getenv("FLASK_PORT", 5000))
        if not (1024 <= flask_port <= 65535): # Standaard range voor user ports
            raise ValueError("Port must be between 1024 and 65535")
    except ValueError as e_port:
        log(f"Ongeldige FLASK_PORT waarde: {os.getenv('FLASK_PORT')}. Gebruik default 5000. Fout: {e_port}", "WARNING")
        flask_port = 5000

    flask_debug_str = os.getenv("FLASK_DEBUG", "false").lower()
    # Wees voorzichtig met debug=True in productie-achtige setups.
    # Flask's development server is niet voor productie.
    flask_debug_bool = flask_debug_str in ["true", "1", "t", "yes"]

    log(f"Flask app '{__name__}' wordt gestart op http://{flask_host}:{flask_port}/ | Debug: {flask_debug_bool}", "INFO")
    # Voor development, `use_reloader=True` is vaak standaard als debug=True.
    # Overweeg `use_reloader=False` als je problemen hebt met dubbele initialisatie of threads.
    app.run(host=flask_host, port=flask_port, debug=flask_debug_bool)