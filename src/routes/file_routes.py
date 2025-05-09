# File: src/routes/file_routes.py
# Contains only API-related file routes (e.g., upload)

import os
import uuid
import traceback
from pathlib import Path
from flask import Blueprint, request, jsonify, abort

# Import utilities and constants
from src.utils.log import log
# Import PROJECT_ROOT for constructing paths safely
from src.utils.config_schema import PROJECT_ROOT
from src.constants import AUDIO_FOLDER_NAME # Import folder name constant
from werkzeug.utils import secure_filename # Import secure_filename


# --- Define Paths Used by this Blueprint ---
# Use constant for folder name
UPLOAD_FOLDER = PROJECT_ROOT / AUDIO_FOLDER_NAME
# RESULTS_FOLDER is not needed here anymore

# --- Define the Blueprint for File API ---
file_api_bp = Blueprint(
    'file_api',       # Blueprint identifier
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
        # Secure the filename - this is primarily for the basename part
        original_filename = file.filename
        if not original_filename:
             log("API Warning: Original filename is empty, generating name.", "WARNING")
             # Generate a safe name if original is empty
             filename = f"upload_{uuid.uuid4().hex}.upload" # Use .upload extension fallback
        else:
            # Use secure_filename to sanitize the name part
            filename = secure_filename(original_filename)
            if not filename:
                log(f"API Warning: Original filename '{original_filename}' sanitized to empty, generating name.", "WARNING")
                # Generate a safe name if sanitation resulted in empty
                base, ext = os.path.splitext(original_filename)
                # Use original extension if possible, otherwise fallback
                filename = f"upload_{uuid.uuid4().hex}{ext if ext else '.upload'}"


        save_path_abs = (UPLOAD_FOLDER / filename).resolve() # Resolve absolute path
        upload_folder_abs = UPLOAD_FOLDER.resolve() # Resolve upload folder abs path

        # Crucial Security Check: Ensure the resolved path is within the upload directory
        if not save_path_abs.is_relative_to(upload_folder_abs):
            log(f"API Security Error: Attempted upload with path traversal detected. Original='{original_filename}', Sanitized='{filename}', Resolved='{save_path_abs}'", "CRITICAL")
            # Delete potentially created partial file if any
            if save_path_abs.exists():
                 try: save_path_abs.unlink()
                 except Exception: pass
            abort(400, description="Invalid or unsafe filename provided.")


        try:
            # Ensure the upload directory exists
            UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"API Error: Could not create upload directory '{UPLOAD_FOLDER}': {e}. Check permissions.", "CRITICAL")
            return jsonify({"error": "Server configuration error preventing file upload."}), 500

        if save_path_abs.exists():
             log(f"API Warning: File '{filename}' already exists. Overwriting.", "WARNING")

        # Save the file to the secured absolute path
        file.save(str(save_path_abs))

        # Return the path relative to PROJECT_ROOT (e.g., "audio/my_file.mp3")
        # Use the name derived from secure_filename for the relative path too
        # The save_path_abs is based on the secured name.
        relative_path_to_return = save_path_abs.relative_to(PROJECT_ROOT)

        log(f"API: File '{filename}' uploaded successfully. Relative path: '{relative_path_to_return}'", "SUCCESS")

        return jsonify({
            "message": "File uploaded successfully",
            "relative_path": str(relative_path_to_return) # Return the full relative path
            }), 200

    except Exception as e:
        # General error during file handling/saving
        log(f"API Error: Failed to save uploaded file '{getattr(file, 'filename', 'N/A')}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return jsonify({"error": "Failed to save file on server"}), 500

# --- Static file serving routes (/results/ and /audio/) are now in static_routes.py ---