# src/routes/static_routes.py (Met Favicon Route)

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

# --- Import Constants ---
# BELANGRIJK: Zorg ervoor dat deze constanten gedefinieerd zijn in src/constants.py
try:
    # GECORRIGEERDE IMPORT: Voeg STATIC_FOLDER_NAME toe
    from src.constants import UPLOAD_FOLDER_NAME, RESULTS_FOLDER_NAME, STATIC_FOLDER_NAME
except ImportError:
    # Fallback/Error if constants are not defined. Should ideally be caught by config/setup.
    log("CRITICAL: Could not import folder names from src.constants. Static file serving may fail.", "CRITICAL")
    UPLOAD_FOLDER_NAME = "audio" # Fallback to default name
    RESULTS_FOLDER_NAME = "results" # Fallback to default name
    STATIC_FOLDER_NAME = "static" # Fallback to default name


# --- Define Base Directories ---
# Use constants for directory names
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME
STATIC_FOLDER = PROJECT_ROOT / STATIC_FOLDER_NAME # <-- Definieer STATIC_FOLDER


# --- Define the Blueprint for Static Files ---
# Use the name expected by app.py registration
static_files_bp = Blueprint(
    'static_files',
    __name__,
    # NO url_prefix here, registration in app.py handles root paths like /results/ and /audio/
)

# --- Helper Function for Secure File Serving (already exists) ---
def _safe_send_from_project_subdir(directory_name: str, filename: str, as_attachment: bool = False):
    """
    Safely serves a file from a specified subdirectory within the PROJECT_ROOT.
    Prevents directory traversal attacks.
    """
    # ... (existing implementation of _safe_send_from_project_subdir)
    safe_basename = Path(secure_filename(filename)).name
    if not safe_basename or safe_basename != filename:
         log(f"Static Route Warning: File request blocked for potentially unsafe filename. Original='{filename}', Sanitized='{safe_basename}'", "WARNING")
         abort(400, description="Invalid filename provided.")

    base_directory = PROJECT_ROOT / directory_name
    resolved_base_directory = base_directory.resolve()

    try:
        log(f"Static Route: Attempting to send file '{safe_basename}' from directory '{resolved_base_directory}' (as_attachment={as_attachment})", "DEBUG")
        return send_from_directory(
                directory=str(resolved_base_directory),
                path=safe_basename,
                as_attachment=as_attachment
            )
    except FileNotFoundError:
        log(f"Static Route Error: File not found: '{safe_basename}' in '{resolved_base_directory}'", "ERROR")
        abort(404, description="File not found.")
    except Exception as e:
        log(f"Static Route Error: Server error serving file '{safe_basename}' from '{resolved_base_directory}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        abort(500, description="Server error during file serving.")


# --- Static File Serving Routes ---
# These routes call the helper function

@static_files_bp.route(f"/{RESULTS_FOLDER_NAME}/<path:filename>")
def download_result_file(filename):
    """
    Endpoint to allow downloading of result files.
    Serves files from the configured RESULTS_FOLDER.
    Forces download.
    """
    log(f"Static Route: Request to download result file: {filename}", "INFO")
    return _safe_send_from_project_subdir(RESULTS_FOLDER_NAME, filename, as_attachment=True)


@static_files_bp.route(f"/{UPLOAD_FOLDER_NAME}/<path:filename>")
def serve_audio_file(filename):
    """
    Endpoint to allow accessing original uploaded audio files.
    Serves files from the configured UPLOAD_FOLDER.
    Allows browser to play/handle inline by default.
    """
    log(f"Static Route: Request to serve audio file: {filename}", "INFO")
    return _safe_send_from_project_subdir(UPLOAD_FOLDER_NAME, filename, as_attachment=False)


# --- NEW Route for Favicon ---
@static_files_bp.route('/favicon.ico')
def serve_favicon():
    """
    Endpoint to serve the favicon.ico file from the static directory.
    Browsers automatically request this from the root.
    """
    log("Static Route: Request for favicon.ico", "DEBUG")
    try:
        # Serve the favicon.ico file directly from the STATIC_FOLDER
        # No need for sanitization as the filename is hardcoded
        return send_from_directory(
            directory=str(STATIC_FOLDER.resolve()), # Use absolute path string
            path='favicon.ico',                   # Hardcoded filename
            mimetype='image/vnd.microsoft.icon'   # Specify MIME type
        )
    except FileNotFoundError:
        log("Static Route Warning: Favicon.ico not found in static directory.", "WARNING")
        abort(404) # Return 404 if favicon is not found
    except Exception as e:
        log(f"Static Route Error: Server error serving favicon.ico: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        abort(500)

# --- End of src/routes/static_routes.py ---