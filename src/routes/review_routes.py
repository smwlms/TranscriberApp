# File: src/routes/review_routes.py
import threading
import json
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

# Define SecurityError if not already imported
class SecurityError(Exception):
    """Custom exception for security-related errors."""
    pass
from flask import Blueprint, request, jsonify, abort

# Import application components and utilities
# Make sure job_manager and STATUS_WAITING_FOR_REVIEW are imported correctly
from src.job_manager import job_manager, STATUS_WAITING_FOR_REVIEW
from src.pipeline_part2 import run_part2
from src.utils.log import log
# Import PROJECT_ROOT for resolving file paths safely
from src.utils.config_schema import PROJECT_ROOT

# Define the Blueprint object for review-related routes
review_bp = Blueprint( # Ensure this name 'review_bp' is unique and used here
    'review',         # Blueprint name
    __name__,
    url_prefix='/api/v1' # Use the same prefix for consistency
)

# --- Review Routes ---

@review_bp.route("/get_review_data/<job_id>", methods=["GET"])
def get_review_data(job_id):
    """
    API endpoint to retrieve data needed for the speaker review step UI.
    Loads content from intermediate files (transcript, proposed map, context)
    identified in the job state.
    """
    log(f"API: Request received for review data for job {job_id}", "INFO")
    job_data = job_manager.get_status(job_id)

    # --- Validate Job Existence and Status ---
    if not job_data:
        log(f"API Error: Get review data failed: Job ID '{job_id}' not found.", "WARNING")
        abort(404, description="Job not found")
    current_status = job_data.get("status")
    if current_status != STATUS_WAITING_FOR_REVIEW:
        log(f"API Warning: Get review data requested for job '{job_id}' but status is '{current_status}' (Expected: '{STATUS_WAITING_FOR_REVIEW}').", "WARNING")
        # Return 409 Conflict if the job is not in the correct state
        return jsonify({"error": f"Job status is '{current_status}', expected '{STATUS_WAITING_FOR_REVIEW}'"}), 409

    # --- Get Relative Paths Stored by Part 1 ---
    review_paths = job_data.get("review_data_paths", {})
    intermediate_transcript_rel_path = review_paths.get("intermediate_transcript_path")
    proposed_map_rel_path = review_paths.get("proposed_map_path")
    context_snippets_rel_path = review_paths.get("context_snippets_path")

    # --- Load Data Content from Files ---
    # Initialize payload structure
    review_payload = {"intermediate_transcript": None, "proposed_map": {}, "context_snippets": {}}
    load_errors = [] # Collect errors encountered during file loading

    # Load Intermediate Transcript (Considered Essential)
    if intermediate_transcript_rel_path:
        try:
            # Construct absolute path safely relative to PROJECT_ROOT
            full_path = (PROJECT_ROOT / intermediate_transcript_rel_path).resolve()
            # Security check: prevent accessing files outside project root
            if not full_path.is_relative_to(PROJECT_ROOT.resolve()):
                raise SecurityError("Attempted path traversal.")
            if not full_path.is_file():
                raise FileNotFoundError(f"File not found at resolved path: {full_path}")

            # Read and parse the JSON file
            with open(full_path, "r", encoding='utf-8') as f:
                review_payload["intermediate_transcript"] = json.load(f)
            log(f"API: Successfully loaded intermediate transcript for review: {intermediate_transcript_rel_path}", "DEBUG")
        except (FileNotFoundError, SecurityError, json.JSONDecodeError, Exception) as e:
            msg = f"Error loading intermediate transcript '{intermediate_transcript_rel_path}': {type(e).__name__}: {e}"
            log(msg, "ERROR"); load_errors.append(msg)
            log(traceback.format_exc(), "DEBUG") # Log full traceback for debugging
    else:
        # If the path itself is missing from job_data
        msg = "Intermediate transcript path missing in job data."
        log(msg, "ERROR"); load_errors.append(msg)

    # Load Proposed Speaker Map (Optional - may not exist)
    # This will load the file containing the new structure if saved correctly by Part 1
    if proposed_map_rel_path:
        try:
            full_path = (PROJECT_ROOT / proposed_map_rel_path).resolve()
            if not full_path.is_relative_to(PROJECT_ROOT.resolve()): raise SecurityError("Attempted path traversal.")
            # Only try loading if the file exists
            if full_path.is_file():
                 with open(full_path, "r", encoding='utf-8') as f:
                     # json.load will parse the nested structure correctly
                     review_payload["proposed_map"] = json.load(f)
                 log(f"API: Successfully loaded proposed map for review: {proposed_map_rel_path}", "DEBUG")
            else:
                 # File not found is expected if name detection didn't produce a map
                 log(f"API Info: Proposed map file not found at '{proposed_map_rel_path}'. Returning empty map.", "INFO")
                 review_payload["proposed_map"] = {} # Default to empty dict if not found
        except (SecurityError, json.JSONDecodeError, Exception) as e:
             # Treat loading errors here as warnings, as proposed map is optional
             msg = f"Could not load proposed map '{proposed_map_rel_path}': {type(e).__name__}: {e}"
             log(msg, "WARNING"); load_errors.append(msg) # Add to errors but don't fail request yet
             log(traceback.format_exc(), "DEBUG")
    else:
        log("API Info: No proposed map path found in job data. Returning empty map.", "INFO")


    # Load Context Snippets (Optional - may not exist)
    # This remains unchanged and loads the context snippets needed for explanation
    if context_snippets_rel_path:
        try:
            full_path = (PROJECT_ROOT / context_snippets_rel_path).resolve()
            if not full_path.is_relative_to(PROJECT_ROOT.resolve()): raise SecurityError("Attempted path traversal.")
            if full_path.is_file():
                 with open(full_path, "r", encoding='utf-8') as f:
                     review_payload["context_snippets"] = json.load(f)
                 log(f"API: Successfully loaded context snippets for review: {context_snippets_rel_path}", "DEBUG")
            else:
                 log(f"API Info: Context snippets file not found at '{context_snippets_rel_path}'. Returning empty dict.", "INFO")
                 review_payload["context_snippets"] = {}
        except (SecurityError, json.JSONDecodeError, Exception) as e:
             msg = f"Could not load context snippets '{context_snippets_rel_path}': {type(e).__name__}: {e}"
             log(msg, "WARNING"); load_errors.append(msg)
             log(traceback.format_exc(), "DEBUG")
    else:
        log("API Info: No context snippets path found in job data. Returning empty dict.", "INFO")

    # --- Final Check and Return Response ---
    # If the essential transcript data couldn't be loaded, return a server error
    if review_payload["intermediate_transcript"] is None:
         log(f"API Critical Error: Intermediate transcript could not be loaded for job {job_id}. Cannot provide review data.", "ERROR")
         # Return 500 Internal Server Error with details
         return jsonify({"error": "Failed to load essential review data (transcript).", "details": load_errors}), 500

    # If loading succeeded (at least for the transcript), return the payload
    # This payload now contains the structured proposed_map and context_snippets
    log(f"API: Successfully prepared review data payload for job {job_id}.", "INFO")
    return jsonify(review_payload)


@review_bp.route("/update_review_data/<job_id>", methods=["POST"])
def update_review_data(job_id):
    """
    API endpoint to receive the final speaker map (as JSON) from the user
    and trigger Part 2 of the pipeline in a background thread.
    (This function remains unchanged as it only receives the final map edited by the user)
    """
    log(f"API: Received review update (final map) for job {job_id}", "INFO")

    # --- Validate Request and Job State ---
    job_data = job_manager.get_status(job_id)
    if not job_data:
        log(f"API Warning: Update review data for non-existent job ID '{job_id}'.", "WARNING")
        abort(404, description="Job not found")
    current_status = job_data.get("status")
    if current_status != STATUS_WAITING_FOR_REVIEW:
        log(f"API Warning: Update review data for job '{job_id}' - incorrect status '{current_status}'.", "WARNING")
        return jsonify({"error": f"Job status is '{current_status}', expected '{STATUS_WAITING_FOR_REVIEW}'."}), 409 # Conflict

    # Ensure request body is JSON content type
    if not request.is_json:
        log(f"API Error: Update review data request body is not JSON for job '{job_id}'.", "WARNING")
        return jsonify({"error": "Request body must be JSON"}), 415 # Unsupported Media Type

    # --- Extract Final Map from JSON Payload ---
    request_data = request.get_json()
    final_map = request_data.get("final_speaker_map")

    # Validate that 'final_speaker_map' exists and is a dictionary
    if not isinstance(final_map, dict):
        log(f"API Error: 'final_speaker_map' missing or not a dictionary in JSON payload for job '{job_id}'.", "WARNING")
        return jsonify({"error": "Invalid or missing 'final_speaker_map' (must be a JSON object/dictionary)"}), 400 # Bad Request

    log(f"API: Received final speaker map for job {job_id}: {final_map}", "DEBUG")

    # --- Start Part 2 Thread ---
    try:
        # Start Part 2 in a background thread, passing the job_id and the received final_map
        pipeline_thread_part2 = threading.Thread(
            target=run_part2,
            args=(job_id, final_map), # Pass the map from the user
            daemon=True
        )
        pipeline_thread_part2.start()
        log(f"API: Started Part 2 thread for job {job_id} after review.", "INFO")

        # Return '202 Accepted' to indicate the request was received and processing started
        return jsonify({"message": "Review submitted successfully. Continuing pipeline."}), 202

    except Exception as e:
        # Catch potential errors during thread creation/start
        log(f"API Error: Failed to start Part 2 thread for job {job_id}: {e}", "CRITICAL")
        log(traceback.format_exc(), "ERROR")
        # Attempt to update the job status to reflect this failure
        job_manager.set_error(job_id, "Failed to start pipeline Part 2 after review submission")
        # Return 500 Internal Server Error
        return jsonify({"error": "Failed to continue pipeline job after review"}), 500

# --- End of src/routes/review_routes.py ---