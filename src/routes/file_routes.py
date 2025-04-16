# File: src/routes/file_routes.py
# Contains only API-related file routes (e.g., upload)

import os
import uuid
import traceback
from pathlib import Path
# Removed send_from_directory import as it's no longer used here
from flask import Blueprint, request, jsonify, abort
from werkzeug.utils import secure_filename

# Import utilities and constants
from src.utils.log import log
# Import PROJECT_ROOT for constructing paths safely
from src.utils.config_schema import PROJECT_ROOT

# --- Define Paths Used by this Blueprint ---
UPLOAD_FOLDER_NAME = "audio"
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
# RESULTS_FOLDER is not needed here anymore

# --- Define the Blueprint for File API ---
# *** RENAMED Blueprint to match app.py import/registration ***
file_api_bp = Blueprint(
    'file_api',       # Renamed blueprint identifier
    __name__,
    # The url_prefix '/api/v1' will be added during registration in app.py
)

# --- API Route for File Upload ---

# Note: This route will be accessed via /api/v1/upload_audio after registration
@file_api_bp.route("/upload_audio", methods=["POST"])
def upload_audio():
    """API endpoint to handle audio file uploads.
    Expects a file in the 'audio_file' part of the multipart/form-data request.
    Returns the relative path of the saved file on success.
    (Registered WITH /api/v1 prefix in app.py)
    """
    log("API: Request received for /upload_audio", "INFO")

    # --- Validate Request ---
    if 'audio_file' not in request.files:
        log("API Error: /upload_audio request missing 'audio_file' part.", "WARNING")
        return jsonify({"error": "No file part named 'audio_file' in the request"}), 400
    file = request.files['audio_file']
    if not file or file.filename == '':
        log("API Error: /upload_audio no file selected or filename is empty.", "WARNING")
        return jsonify({"error": "No file selected"}), 400

    # --- Secure and Save File ---
    try:
        filename = secure_filename(file.filename)
        if not filename:
             base, ext = os.path.splitext(file.filename)
             filename = f"upload_{uuid.uuid4().hex}{ext if ext else '.upload'}"
             log(f"API Warning: Original filename ('{file.filename}') was unsafe or empty, using generated name: {filename}", "WARNING")

        save_path = UPLOAD_FOLDER / filename
        try:
            UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"API Error: Could not create upload directory '{UPLOAD_FOLDER}': {e}. Check permissions.", "CRITICAL")
            return jsonify({"error": "Server configuration error preventing file upload."}), 500

        if save_path.exists():
             log(f"API Warning: File '{filename}' already exists. Overwriting.", "WARNING")

        file.save(str(save_path))

        relative_path = Path(UPLOAD_FOLDER_NAME) / filename
        log(f"API: File '{filename}' uploaded successfully. Relative path: '{relative_path}'", "SUCCESS")

        return jsonify({
            "message": "File uploaded successfully",
            "relative_path": str(relative_path)
            }), 200

    except Exception as e:
        log(f"API Error: Failed to save uploaded file '{getattr(file, 'filename', 'N/A')}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return jsonify({"error": "Failed to save file on server"}), 500

# --- Static file serving routes (/results/ and /audio/) are now in static_routes.py ---

# --- End of src/routes/file_routes.py ---