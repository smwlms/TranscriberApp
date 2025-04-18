# File: src/pipeline_part1.py

import time
import os
import json
import traceback
from pathlib import Path
# Updated type hints for proposed map and function signature
from typing import Dict, Any, List, Optional, Tuple

# --- Application Component Imports ---
from src.job_manager import job_manager, STATUS_RUNNING, STATUS_PROCESSING_AUDIO, \
    STATUS_DETECTING_NAMES, STATUS_WAITING_FOR_REVIEW, \
    STATUS_STOPPED, STATUS_FAILED

# *** CORRECTED/UPDATED IMPORTS ***
# Import the main audio processing function and its related defaults from transcriber
from src.transcriber import transcribe_and_diarize, DEFAULT_WHISPER_MODEL, \
     DEFAULT_COMPUTE_TYPE
# Import the Pyannote default pipeline name from its new location in model_loader
from src.core.model_loader import DEFAULT_PYANNOTE_PIPELINE # <-- IMPORT FROM CORRECT MODULE

# Safely import the optional speaker name detector
try:
    from src.speaker_name_detector import detect_speaker_names
    NAME_DETECTOR_AVAILABLE = True
except ImportError:
    # Use print as log might not be configured yet at import time
    print("[PipelinePart1 WARNING] Speaker name detector module not found, disabling automatic name detection.")
    NAME_DETECTOR_AVAILABLE = False
    # Define a fallback function that matches the expected return signature (map, snippets)
    def detect_speaker_names(*args, **kwargs) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, str]]:
        """Fallback function when speaker_name_detector is not available."""
        return {}, {}

# --- Utility Imports ---
from src.utils.load_config import load_config
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log
from src.utils.pipeline_helpers import check_stop, merge_configs

# --- Constants ---
# Directory names (consider moving to a central config/constants file later)
RESULTS_DIR_NAME = "results"
TRANSCRIPTS_DIR_NAME = "transcripts"
# Define standard intermediate filenames
DEFAULT_INTERMEDIATE_JSON_FILENAME = "intermediate_transcript.json"
DEFAULT_PROPOSED_MAP_FILENAME = "intermediate_proposed_map.json"
DEFAULT_CONTEXT_SNIPPETS_FILENAME = "intermediate_context.json"

# Constants for progress reporting (percentages)
PROGRESS_START = 5
PROGRESS_AFTER_CONFIG = 10
PROGRESS_AFTER_VALIDATION = 15
PROGRESS_AFTER_AUDIO_PROCESSING = 75 # Increased as this is the main work
PROGRESS_AFTER_NAME_DETECT = 90
PROGRESS_WAITING_REVIEW = 95 # Progress before waiting

# --- Main Pipeline Function ---

# *** ADDED Type hint for function signature ***
def run_part1(job_id: str, config_overrides: Dict[str, Any]) -> None:
    """
    Runs Part 1: Configuration, Audio Processing, Intermediate Save, Optional Name Detection.
    Sets job status to WAITING_FOR_REVIEW upon successful completion, or FAILED/STOPPED on error.
    """
    job_config: Dict[str, Any] = {} # Holds the final merged config for this job
    # Absolute paths for file operations
    intermediate_transcript_path_abs: Optional[Path] = None
    proposed_map_path_abs: Optional[Path] = None
    context_snippets_path_abs: Optional[Path] = None
    # Relative paths to store in job state
    intermediate_transcript_path_rel: Optional[Path] = None
    proposed_map_path_rel: Optional[Path] = None
    context_snippets_path_rel: Optional[Path] = None

    job_manager.update_progress(job_id, PROGRESS_START, status=STATUS_RUNNING)
    job_manager.add_log(job_id, "Pipeline Part 1 started.", "INFO")

    try:
        # --- Step 1: Load and Merge Configuration ---
        log(f"Step 1: Loading and merging configuration...", "DEBUG", job_id=job_id)
        base_config = load_config() # Load base config (incl. defaults from schema)
        job_config = merge_configs(base_config, config_overrides) # Apply job-specific overrides
        # Store the final config used for this job in the job manager state
        job_manager._update_job_state(job_id, {"config": job_config})
        log(f"Part 1 Config prepared. Mode: {job_config.get('mode', 'N/A')}, Word Timestamps: {job_config.get('word_timestamps_enabled', False)}", "INFO", job_id=job_id)
        job_manager.update_progress(job_id, PROGRESS_AFTER_CONFIG)
        check_stop(job_id, "config loading") # Check if stop requested early

        # --- Step 2: Validate Inputs ---
        log(f"Step 2: Validating inputs...", "DEBUG", job_id=job_id)
        input_audio_rel_path_str = job_config.get("input_audio")
        if not input_audio_rel_path_str: # More explicit check
            raise ValueError("Configuration Error: 'input_audio' path missing.")

        input_audio_rel_path = Path(input_audio_rel_path_str)
        # Resolve the absolute path relative to the project root
        abs_input_path = (PROJECT_ROOT / input_audio_rel_path).resolve()
        if not abs_input_path.is_file():
             # Ensure the file actually exists at the resolved path
             raise FileNotFoundError(f"Input audio file not found at resolved path: {abs_input_path}")
        log(f"Input audio validated: {abs_input_path.name}", "INFO", job_id=job_id)
        job_manager.update_progress(job_id, PROGRESS_AFTER_VALIDATION)

        # --- Step 3: Prepare Intermediate File Paths ---
        log(f"Step 3: Preparing intermediate file paths...", "DEBUG", job_id=job_id)
        # Use path from config or generate default path relative to project root
        int_transcript_rel_str = job_config.get(
            "intermediate_transcript_path",
            str(Path(TRANSCRIPTS_DIR_NAME) / DEFAULT_INTERMEDIATE_JSON_FILENAME)
        )
        intermediate_transcript_path_rel = Path(int_transcript_rel_str)
        # Derive paths for optional map/context files based on transcript path's name/location
        proposed_map_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_PROPOSED_MAP_FILENAME)
        context_snippets_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_CONTEXT_SNIPPETS_FILENAME)
        # Create absolute paths for file operations
        intermediate_transcript_path_abs = (PROJECT_ROOT / intermediate_transcript_path_rel).resolve()
        proposed_map_path_abs = (PROJECT_ROOT / proposed_map_path_rel).resolve()
        context_snippets_path_abs = (PROJECT_ROOT / context_snippets_path_rel).resolve()
        # Ensure parent directory exists (e.g., 'transcripts/')
        intermediate_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        log(f"Intermediate transcript path: {intermediate_transcript_path_rel}", "DEBUG", job_id=job_id)
        log(f"Proposed map path: {proposed_map_path_rel}", "DEBUG", job_id=job_id)
        log(f"Context snippets path: {context_snippets_path_rel}", "DEBUG", job_id=job_id)


        # --- Step 4: Extract Relevant Config Values for Processing ---
        log(f"Step 4: Extracting processing parameters from config...", "DEBUG", job_id=job_id)
        whisper_model = job_config.get("whisper_model", DEFAULT_WHISPER_MODEL)
        compute_type = job_config.get("compute_type", DEFAULT_COMPUTE_TYPE)
        language = job_config.get("language") # None means auto-detect
        pyannote_pipeline = job_config.get("pyannote_pipeline", DEFAULT_PYANNOTE_PIPELINE) # Use corrected default import
        hf_token = os.environ.get("HUGGING_FACE_TOKEN") # Check env var first
        if not hf_token:
            hf_token = job_config.get("hf_token") # Fallback to config if needed
            if not hf_token: log("Hugging Face Token (HUGGING_FACE_TOKEN env var or hf_token in config) not found. Pyannote may fail.", "WARNING", job_id=job_id)
        name_detection_enabled = job_config.get("speaker_name_detection_enabled", False)
        word_timestamps_enabled = job_config.get("word_timestamps_enabled", False)

        # --- Step 5: Audio Processing (Transcription & Diarization) ---
        log(f"Step 5: Starting audio processing (Whisper: {whisper_model}, Pyannote: {pyannote_pipeline}, Words: {word_timestamps_enabled})...", "INFO", job_id=job_id)
        job_manager.update_status(job_id, STATUS_PROCESSING_AUDIO)
        start_time_audio = time.time()

        # Call the main function from the refactored transcriber module
        intermediate_segments = transcribe_and_diarize(
            input_audio_path=abs_input_path, # Use absolute path here
            whisper_model_size=whisper_model,
            compute_type=compute_type,
            language=language,
            hf_token=hf_token,
            pyannote_pipeline_name=pyannote_pipeline,
            word_timestamps_enabled=word_timestamps_enabled # Pass setting
            # Pass diarization hints if they exist in config (add later if needed)
            # num_speakers=job_config.get("num_speakers"),
            # min_speakers=job_config.get("min_speakers"),
            # max_speakers=job_config.get("max_speakers"),
        )

        # Check if transcribe_and_diarize returned None, indicating failure
        if intermediate_segments is None:
            # Error should have been logged within transcribe_and_diarize or its sub-modules
            raise RuntimeError("Audio processing (transcription/diarization) failed.")

        elapsed_audio = round(time.time() - start_time_audio, 2)
        job_manager.add_log(job_id, f"Audio processing finished ({elapsed_audio}s). {len(intermediate_segments)} segments generated.", "SUCCESS")

        # Save intermediate results to JSON file
        log(f"Saving intermediate transcript to {intermediate_transcript_path_abs}...", "DEBUG", job_id=job_id)
        try:
            with open(intermediate_transcript_path_abs, "w", encoding='utf-8') as f:
                 json.dump(intermediate_segments, f, indent=2, ensure_ascii=False)
            job_manager.add_log(job_id, f"Intermediate transcript saved: {intermediate_transcript_path_rel}", "INFO")
        except Exception as e:
            # Treat failure to save intermediate transcript as critical for review step
            raise RuntimeError(f"Failed to save intermediate transcript to '{intermediate_transcript_path_abs}': {e}") from e

        # Update progress and check for stop request
        job_manager.update_progress(job_id, PROGRESS_AFTER_AUDIO_PROCESSING)
        check_stop(job_id, "audio processing completion")

        # --- Step 6: Speaker Name Detection (Optional LLM step) ---
        # Initialize results for this step
        proposed_map_with_context: Dict[str, Dict[str, Any]] = {}
        detection_context_snippets: Dict[int, str] = {}
        next_status_after_step6 = STATUS_WAITING_FOR_REVIEW # Default next status

        if name_detection_enabled:
            if NAME_DETECTOR_AVAILABLE:
                log(f"Step 6: Attempting speaker name detection (LLM)...", "INFO", job_id=job_id)
                job_manager.update_status(job_id, STATUS_DETECTING_NAMES)
                start_time_detect = time.time()
                try:
                     # Call the name detection function
                     proposed_map_with_context, context_snippets_result = detect_speaker_names(
                         transcript_segments=intermediate_segments, # Pass the processed segments
                         config=job_config                     # Pass the job config for LLM models/settings
                     )
                     # Ensure the function didn't return None for the map (indicates critical failure)
                     if proposed_map_with_context is None:
                          raise RuntimeError("Speaker name detection function returned None map, likely LLM parsing error.")

                     elapsed_detect = round(time.time() - start_time_detect, 2)
                     # proposed_map_with_context holds {SPEAKER_ID: {"name": ..., "reasoning_indices": [...]}}
                     detection_context_snippets = context_snippets_result or {} # Ensure it's a dict if None was returned

                     job_manager.add_log(job_id, f"Name detection finished ({elapsed_detect}s). {len(proposed_map_with_context)} speakers identified.", "SUCCESS")
                     log(f"Proposed map content: {proposed_map_with_context}", "DEBUG", job_id=job_id) # Log content for debug

                     # Save detection results to intermediate files (non-critical if saving fails)
                     try:
                          # Save the map (which includes context indices)
                          with open(proposed_map_path_abs, "w", encoding='utf-8') as f:
                               json.dump(proposed_map_with_context, f, indent=2, ensure_ascii=False)
                          job_manager.add_log(job_id, f"Proposed speaker map (with context) saved: {proposed_map_path_rel}", "INFO")

                          # Save the actual context snippets if generated
                          if detection_context_snippets:
                               with open(context_snippets_path_abs, "w", encoding='utf-8') as f:
                                    json.dump(detection_context_snippets, f, indent=2, ensure_ascii=False)
                               job_manager.add_log(job_id, f"Context snippets saved: {context_snippets_path_rel}", "INFO")
                          else:
                               # Ensure file doesn't exist if no snippets were generated
                               proposed_map_path_abs.unlink(missing_ok=True) # Remove proposed map if empty? Maybe not.
                               context_snippets_path_abs.unlink(missing_ok=True) # Remove snippets file if empty
                               log("No context snippets generated by LLM.", "DEBUG", job_id=job_id)

                     except Exception as e:
                         job_manager.add_log(job_id, f"Warning: Failed save name detection results: {e}", "WARNING")
                         log(traceback.format_exc(), "DEBUG", job_id=job_id) # Log traceback on save failure

                except Exception as e: # Catch errors during detection call or processing
                     log(f"Speaker name detection step encountered an error: {e}", "ERROR", job_id=job_id)
                     log(traceback.format_exc(), "DEBUG", job_id=job_id)
                     # Don't raise, allow proceeding to review without proposals, but log error
                     job_manager.add_log(job_id, "Speaker name detection failed, proceeding without proposed names.", "WARNING")
                     # Ensure files from potentially failed runs are cleared
                     proposed_map_path_abs.unlink(missing_ok=True)
                     context_snippets_path_abs.unlink(missing_ok=True)
                     proposed_map_with_context = {} # Reset to empty
                     detection_context_snippets = {} # Reset to empty

                # Update progress after name detection attempt (success or fail)
                job_manager.update_progress(job_id, PROGRESS_AFTER_NAME_DETECT)
                check_stop(job_id, "speaker name detection") # Check for stop again after LLM call
            else: # Name detector module wasn't available
                 job_manager.add_log(job_id, "Speaker name detector module unavailable, skipping.", "WARNING")
        else: # Name detection disabled in config
            job_manager.add_log(job_id, "Automatic speaker name detection disabled in config, skipping.", "INFO")
        # If skipped or disabled, map/snippets remain empty, status proceeds to WAITING_FOR_REVIEW

        # --- Step 7: Finalize Part 1 ---
        # Set status to WAITING_FOR_REVIEW and store paths to intermediate data for review UI / Part 2
        log(f"Step 7: Finalizing Part 1, setting status to '{next_status_after_step6}'...", "DEBUG", job_id=job_id)
        job_manager.add_log(job_id, "Part 1 processing complete. Ready for review.", "INFO")

        # Store relative paths for Part 2 / Review API
        # Check if files exist before adding their paths to avoid issues if saving failed
        review_info = {
            "intermediate_transcript_path": str(intermediate_transcript_path_rel), # Assume this always exists if we got here
            "proposed_map_path": str(proposed_map_path_rel) if proposed_map_path_abs and proposed_map_path_abs.exists() else None,
            "context_snippets_path": str(context_snippets_path_rel) if context_snippets_path_abs and context_snippets_path_abs.exists() else None,
        }
        log(f"Final review_info paths to store in job state: {review_info}", "DEBUG", job_id=job_id)

        # Update the job state atomically with final status, progress, and paths
        update_payload = {
            "status": next_status_after_step6,
            "progress": PROGRESS_WAITING_REVIEW,
            "review_data_paths": review_info # Store the dict containing the relative paths
        }
        update_successful = job_manager._update_job_state(job_id, update_payload)

        # If the update failed (e.g., job removed concurrently), raise an error to be caught below
        if not update_successful:
             # Job might have been deleted or stopped externally between last check and now
             log(f"Job {job_id} state could not be updated at end of Part 1 (maybe deleted externally?). Aborting.", "WARNING")
             # No need to raise an error here, just finish gracefully if possible
        else:
            log(f"Final state for Part 1 set successfully for job {job_id}.", "DEBUG")

    # --- Exception Handling for the Entire Part 1 ---
    except (FileNotFoundError, ValueError, AssertionError, RuntimeError, InterruptedError) as e:
        # Handle known processing errors and stop requests cleanly
        status_to_set = STATUS_STOPPED if isinstance(e, InterruptedError) else STATUS_FAILED
        log_level = "WARNING" if status_to_set == STATUS_STOPPED else "ERROR"
        error_msg_detail = str(e)

        # Provide slightly more context in the error message
        if isinstance(e, FileNotFoundError): error_msg_prefix = "Required file not found"
        elif isinstance(e, ValueError): error_msg_prefix = "Invalid configuration or value"
        elif isinstance(e, AssertionError): error_msg_prefix = "Processing assertion failed"
        elif isinstance(e, RuntimeError): error_msg_prefix = "Processing step runtime error"
        elif isinstance(e, InterruptedError): error_msg_prefix = "Stopped by user request during"
        else: error_msg_prefix = "Pipeline error" # Should not happen with specific catches

        # Combine for final message
        error_msg = f"Pipeline Part 1 {status_to_set.lower()}: {error_msg_prefix} - {error_msg_detail}"

        log(error_msg, log_level, job_id=job_id)
        log(traceback.format_exc(), "DEBUG", job_id=job_id) # Log full traceback at DEBUG level
        # Use the dedicated function to set error status and message
        job_manager.set_error(job_id, error_msg)
    except Exception as e:
        # Catch any other unexpected critical errors
        error_msg = f"Unexpected critical error in Pipeline Part 1: {e.__class__.__name__}"
        log(error_msg, "CRITICAL", job_id=job_id)
        log(traceback.format_exc(), "ERROR", job_id=job_id) # Log full traceback for critical errors
        # Set final error state
        job_manager.set_error(job_id, f"{error_msg}: {e}")

# --- End of pipeline_part1.py ---