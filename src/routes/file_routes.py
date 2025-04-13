# src/routes/file_routes.py
import os
import uuid
import traceback
from pathlib import Path
from flask import Blueprint, request, jsonify, abort, send_from_directory
from werkzeug.utils import secure_filename

# Import utilities and constants
from src.utils.log import log
# Import PROJECT_ROOT for constructing paths safely
from src.utils.config_schema import PROJECT_ROOT

# --- Define Paths Used by this Blueprint ---
# Consider getting these from app.config in a real application
UPLOAD_FOLDER_NAME = "audio"
UPLOAD_FOLDER = PROJECT_ROOT / UPLOAD_FOLDER_NAME
RESULTS_FOLDER_NAME = "results"
RESULTS_FOLDER = PROJECT_ROOT / RESULTS_FOLDER_NAME

# --- Define the Blueprint ---
file_bp = Blueprint(
    'files',          # Blueprint name
    __name__,
    # url_prefix='/api/files' # Optional URL prefix
)

# --- File Routes ---

@file_bp.route("/upload_audio", methods=["POST"])
def upload_audio():
    """API endpoint to handle audio file uploads.
    Expects a file in the 'audio_file' part of the multipart/form-data request.
    Returns the relative path of the saved file on success.
    """
    log("API: Request received for /upload_audio", "INFO")

    # --- Validate Request ---
    if 'audio_file' not in request.files:
        log("API Error: /upload_audio request missing 'audio_file' part.", "WARNING")
        return jsonify({"error": "No file part named 'audio_file' in the request"}), 400 # Bad Request
    file = request.files['audio_file']
    # Check if a file was actually selected
    if not file or file.filename == '':
        log("API Error: /upload_audio no file selected or filename is empty.", "WARNING")
        return jsonify({"error": "No file selected"}), 400 # Bad Request

    # --- Secure and Save File ---
    try:
        # Sanitize the filename to prevent directory traversal and other security issues
        filename = secure_filename(file.filename)
        # Generate a safe fallback filename if secure_filename fails or returns empty
        if not filename:
             base, ext = os.path.splitext(file.filename) # Try to keep original extension
             filename = f"upload_{uuid.uuid4().hex}{ext if ext else '.upload'}" # Add default ext if none
             log(f"API Warning: Original filename ('{file.filename}') was unsafe or empty, using generated name: {filename}", "WARNING")

        # Construct the full path to save the file
        save_path = UPLOAD_FOLDER / filename
        # Ensure the upload directory exists (should be handled at app startup ideally)
        UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

        # Save the file stream to the designated path
        file.save(str(save_path))

        # Construct the relative path to return to the client
        # This path should be relative to the location defined by UPLOAD_FOLDER_NAME
        relative_path = Path(UPLOAD_FOLDER_NAME) / filename
        log(f"API: File '{filename}' uploaded successfully. Relative path: '{relative_path}'", "SUCCESS")

        # Return success response with the relative path
        return jsonify({
            "message": "File uploaded successfully",
            "relative_path": str(relative_path) # Convert Path object to string for JSON
            }), 200 # OK

    except Exception as e:
        # Catch potential exceptions during file saving (e.g., disk full, permissions)
        log(f"API Error: Failed to save uploaded file '{file.filename}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log traceback for server debugging
        # Return 500 Internal Server Error
        return jsonify({"error": "Failed to save file on server"}), 500


@file_bp.route("/results/<path:filename>")
def download_result_file(filename):
    """
    API endpoint to allow downloading of result files stored in the RESULTS_FOLDER.
    Uses Flask's send_from_directory for secure file serving.
    """
    log(f"API: Request to download result file: {filename}", "INFO")

    # --- Sanitize Filename ---
    # Use secure_filename and then extract only the basename to prevent path manipulation
    safe_basename = Path(secure_filename(filename)).name
    # Double-check that sanitization didn't result in an empty name or fundamentally change it
    if not safe_basename or safe_basename != filename:
         log(f"API Warning: Download request blocked for potentially unsafe filename. Original='{filename}', Sanitized='{safe_basename}'", "WARNING")
         abort(400, description="Invalid filename provided.") # Bad Request

    # --- Serve File ---
    try:
        # Use Flask's built-in function for safely sending files from a directory
        # It handles security checks (e.g., preventing access outside the directory)
        # and sets appropriate Content-Disposition headers.
        log(f"API: Attempting to send file from directory '{RESULTS_FOLDER}' with safe path '{safe_basename}'", "DEBUG")
        return send_from_directory(
                directory=str(RESULTS_FOLDER), # Directory must be an absolute path string
                path=safe_basename,            # The sanitized filename
                as_attachment=True             # Suggest to the browser to download the file
            )
    except FileNotFoundError:
        # Log error and return 404 if the file doesn't exist in the results directory
        log(f"API Error: Download failed - result file not found: {safe_basename}", "ERROR")
        abort(404, description="Result file not found.") # Not Found
    except Exception as e:
        # Catch other potential server errors (e.g., file permission issues)
        log(f"API Error: Server error during result file download ('{safe_basename}'): {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        abort(500, description="Server error during file download.") # Internal Server Error

# --- End of src/routes/file_routes.py ---