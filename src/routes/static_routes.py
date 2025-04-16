# File: src/routes/static_routes.py

import traceback
from pathlib import Path
# Ensure send_from_directory is imported from flask
from flask import Blueprint, abort, send_from_directory

# Import utilities and constants
from src.utils.log import log
# Import PROJECT_ROOT for constructing paths safely
from src.utils.config_schema import PROJECT_ROOT
# Import secure_filename for sanitizing input
from werkzeug.utils import secure_filename

# --- Define Paths Used by this Blueprint ---
UPLOAD_FOLDER_NAME = "audio"
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
RESULTS_FOLDER_NAME = "results"
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME

# --- Define the Blueprint for Static Files ---
static_files_bp = Blueprint(
    'static_files', # Use the name expected by app.py
    __name__,
    # NO url_prefix here, registration in app.py handles root paths
)

# --- Static File Serving Routes ---

@static_files_bp.route("/results/<path:filename>")
def download_result_file(filename):
    """
    Endpoint to allow downloading of result files stored in the RESULTS_FOLDER.
    Uses Flask's send_from_directory for secure file serving.
    (Registered without prefix in app.py)
    """
    log(f"Static Route: Request to download result file: {filename}", "INFO")

    # --- Sanitize Filename ---
    safe_basename = Path(secure_filename(filename)).name
    if not safe_basename or safe_basename != filename:
         log(f"Static Route Warning: Download request blocked for potentially unsafe filename. Original='{filename}', Sanitized='{safe_basename}'", "WARNING")
         abort(400, description="Invalid filename provided.")

    # --- Serve File ---
    try:
        log(f"Static Route: Attempting to send file from directory '{RESULTS_FOLDER}' with safe path '{safe_basename}'", "DEBUG")
        return send_from_directory(
                directory=str(RESULTS_FOLDER.resolve()), # Use absolute path string
                path=safe_basename,
                as_attachment=True # Force download
            )
    except FileNotFoundError:
        log(f"Static Route Error: Download failed - result file not found: {safe_basename} in {RESULTS_FOLDER}", "ERROR")
        abort(404, description="Result file not found.")
    except Exception as e:
        log(f"Static Route Error: Server error during result file download ('{safe_basename}'): {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        abort(500, description="Server error during file download.")


@static_files_bp.route("/audio/<path:filename>")
def serve_audio_file(filename):
    """
    Endpoint to allow accessing original uploaded audio files
    stored in the UPLOAD_FOLDER. Uses Flask's send_from_directory.
    Needed for the <audio> tag source in the ReviewDialog.
    (Registered without prefix in app.py)
    """
    # *** ADDED DEBUG LOG TO CONFIRM ROUTE IS HIT ***
    log("!!!!!!!!!!!! SERVING AUDIO FILE ROUTE HIT !!!!!!!!!!!!", "CRITICAL")
    log(f"Static Route: Request to serve audio file: {filename}", "INFO")

    # --- Sanitize Filename (IMPORTANT!) ---
    safe_basename = Path(secure_filename(filename)).name
    if not safe_basename or safe_basename != filename:
         log(f"Static Route Warning: Audio file request blocked for potentially unsafe filename. Original='{filename}', Sanitized='{safe_basename}'", "WARNING")
         abort(400, description="Invalid filename provided.")

    # --- Serve File using send_from_directory ---
    try:
        log(f"Static Route: Attempting to send audio file from directory '{UPLOAD_FOLDER}' with safe path '{safe_basename}'", "DEBUG")
        return send_from_directory(
                directory=str(UPLOAD_FOLDER.resolve()), # Use absolute path string
                path=safe_basename,
                # Default: as_attachment=False - allows browser to play/handle inline
            )
    except FileNotFoundError:
        log(f"Static Route Error: Serve audio failed - file not found: {safe_basename} in {UPLOAD_FOLDER}", "ERROR")
        abort(404, description="Audio file not found.")
    except Exception as e:
        log(f"Static Route Error: Server error serving audio file ('{safe_basename}'): {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        abort(500, description="Server error serving audio file.")

# --- End of src/routes/static_routes.py ---