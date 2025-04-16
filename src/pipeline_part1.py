# File: src/pipeline_part1.py

import time
import os
import json
import traceback
from pathlib import Path
# Updated type hints for proposed map
from typing import Dict, Any, List, Optional, Tuple

# Import necessary application components
from src.job_manager import job_manager, STATUS_RUNNING, STATUS_PROCESSING_AUDIO, \
    STATUS_DETECTING_NAMES, STATUS_WAITING_FOR_REVIEW, \
    STATUS_STOPPED, STATUS_FAILED
# Import the main audio processing function
from src.transcriber import transcribe_and_diarize, DEFAULT_WHISPER_MODEL, \
     DEFAULT_COMPUTE_TYPE, DEFAULT_PYANNOTE_PIPELINE
# Safely import the optional speaker name detector
try:
    from src.speaker_name_detector import detect_speaker_names
    NAME_DETECTOR_AVAILABLE = True
except ImportError:
    # Use print as log might not be configured yet at import time
    print("[PipelinePart1 WARNING] Speaker name detector module not found, disabling automatic name detection.")
    NAME_DETECTOR_AVAILABLE = False
    # Define a fallback function that matches the expected return signature (new structure)
    def detect_speaker_names(*args, **kwargs) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, str]]: return {}, {}

# Import Utilities
from src.utils.load_config import load_config
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log
from src.utils.pipeline_helpers import check_stop, merge_configs

# Constants for directory names
RESULTS_DIR_NAME = "results"
TRANSCRIPTS_DIR_NAME = "transcripts"
# Define standard intermediate filenames
DEFAULT_INTERMEDIATE_JSON_FILENAME = "intermediate_transcript.json"
DEFAULT_PROPOSED_MAP_FILENAME = "intermediate_proposed_map.json"
DEFAULT_CONTEXT_SNIPPETS_FILENAME = "intermediate_context.json"

# Constants for progress reporting
PROGRESS_START = 5
PROGRESS_AFTER_AUDIO_PROCESSING = 35 # Assume transcription/diarization are combined here
PROGRESS_AFTER_NAME_DETECT = 45
PROGRESS_WAITING_REVIEW = 48

def run_part1(job_id: str, config_overrides: Dict[str, Any]):
    """
    Runs Part 1: Configuration, Audio Processing, Intermediate Save, Optional Name Detection.
    Sets job status to WAITING_FOR_REVIEW upon successful completion.
    """
    job_config: Dict[str, Any] = {}
    intermediate_transcript_path_abs: Optional[Path] = None
    proposed_map_path_abs: Optional[Path] = None
    context_snippets_path_abs: Optional[Path] = None
    intermediate_transcript_path_rel: Optional[Path] = None
    proposed_map_path_rel: Optional[Path] = None
    context_snippets_path_rel: Optional[Path] = None

    job_manager.update_progress(job_id, PROGRESS_START, status=STATUS_RUNNING)
    job_manager.add_log(job_id, "Pipeline Part 1 started.", "INFO")

    try:
        # --- Step 1: Load and Merge Configuration ---
        log(f"Step 1: Loading and merging configuration...", "DEBUG")
        base_config = load_config() # Load base config (incl. defaults from schema)
        job_config = merge_configs(base_config, config_overrides) # Apply overrides
        job_manager._update_job_state(job_id, {"config": job_config}) # Store final config used
        log(f"Part 1: Config prepared. Mode: {job_config.get('mode', 'N/A')}", "INFO")
        check_stop(job_id, "config loading") # Check if stop requested

        # --- Step 2: Validate Inputs ---
        log(f"Step 2: Validating inputs...", "DEBUG")
        input_audio_rel_path_str = job_config.get("input_audio")
        assert input_audio_rel_path_str, "Configuration Error: 'input_audio' path missing."
        input_audio_rel_path = Path(input_audio_rel_path_str)
        # Use the validated absolute path from pipeline_routes for safety
        # Assuming validation already happened there, but double-checking existence is good
        abs_input_path = (PROJECT_ROOT / input_audio_rel_path).resolve()
        if not abs_input_path.is_file():
             # Re-validate here just in case
             raise FileNotFoundError(f"Input audio file not found at resolved path: {abs_input_path}")
        log(f"Input audio validated: {abs_input_path.name}", "INFO")

        # --- Prepare Intermediate File Paths ---
        # Use path from config or generate default path
        int_transcript_rel_str = job_config.get("intermediate_transcript_path", str(Path(TRANSCRIPTS_DIR_NAME) / DEFAULT_INTERMEDIATE_JSON_FILENAME))
        intermediate_transcript_path_rel = Path(int_transcript_rel_str)
        # Derive paths for optional map/context files based on transcript path
        proposed_map_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_PROPOSED_MAP_FILENAME)
        context_snippets_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_CONTEXT_SNIPPETS_FILENAME)
        # Create absolute paths for file operations
        intermediate_transcript_path_abs = PROJECT_ROOT / intermediate_transcript_path_rel
        proposed_map_path_abs = PROJECT_ROOT / proposed_map_path_rel
        context_snippets_path_abs = PROJECT_ROOT / context_snippets_path_rel
        # Ensure parent directory exists (e.g., 'transcripts/')
        intermediate_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        log(f"Intermediate transcript path: {intermediate_transcript_path_rel}", "DEBUG")
        log(f"Proposed map path: {proposed_map_path_rel}", "DEBUG")
        log(f"Context snippets path: {context_snippets_path_rel}", "DEBUG")

        # --- Extract Relevant Config Values for Processing ---
        whisper_model = job_config.get("whisper_model", DEFAULT_WHISPER_MODEL)
        compute_type = job_config.get("compute_type", DEFAULT_COMPUTE_TYPE)
        language = job_config.get("language") # None means auto-detect
        pyannote_pipeline = job_config.get("pyannote_pipeline", DEFAULT_PYANNOTE_PIPELINE)
        hf_token = os.environ.get("HUGGING_FACE_TOKEN")
        if not hf_token: log("Hugging Face Token (HUGGING_FACE_TOKEN) not found in environment. Pyannote may fail.", "WARNING")
        name_detection_enabled = job_config.get("speaker_name_detection_enabled", False)
        # Get word timestamp setting from config (passed to transcriber)
        word_timestamps_enabled = job_config.get("word_timestamps_enabled", False)

        # --- Step 3: Audio Processing (Transcription & Diarization) ---
        log(f"Step 3: Starting audio processing (Whisper: {whisper_model}, Pyannote: {pyannote_pipeline}, Word Timestamps: {word_timestamps_enabled})...", "INFO")
        job_manager.update_status(job_id, STATUS_PROCESSING_AUDIO)
        start_time_audio = time.time()
        # Pass word_timestamps_enabled setting to the main function
        intermediate_segments = transcribe_and_diarize(
            input_audio_path=abs_input_path, # Use absolute path here
            whisper_model_size=whisper_model,
            compute_type=compute_type,
            language=language,
            hf_token=hf_token,
            pyannote_pipeline_name=pyannote_pipeline,
            word_timestamps_enabled=word_timestamps_enabled # Pass setting
        )
        # Check if transcribe_and_diarize returned None, indicating failure
        assert intermediate_segments is not None, "Audio processing (transcription/diarization) failed."
        elapsed_audio = round(time.time() - start_time_audio, 2)
        job_manager.add_log(job_id, f"Audio processing finished ({elapsed_audio}s).", "SUCCESS")

        # Save intermediate results (which now include word timestamps if enabled) to JSON file
        try:
            with open(intermediate_transcript_path_abs, "w", encoding='utf-8') as f:
                 json.dump(intermediate_segments, f, indent=2, ensure_ascii=False)
            job_manager.add_log(job_id, f"Intermediate transcript saved: {intermediate_transcript_path_rel}", "INFO")
        except Exception as e:
            raise RuntimeError(f"Failed to save intermediate transcript to '{intermediate_transcript_path_abs}': {e}") from e

        # Update progress and check for stop request
        job_manager.update_progress(job_id, PROGRESS_AFTER_AUDIO_PROCESSING)
        check_stop(job_id, "audio processing completion")

        # --- Step 4: Speaker Name Detection (Optional LLM step) ---
        # *** MODIFICATION: Update type hint and variable name for clarity ***
        proposed_map_with_context: Optional[Dict[str, Dict[str, Any]]] = {} # Renamed & updated type
        detection_context_snippets: Dict[int, str] = {}
        next_status_after_step4 = STATUS_WAITING_FOR_REVIEW # Default next status

        if name_detection_enabled and NAME_DETECTOR_AVAILABLE:
            log(f"Step 4: Attempting speaker name detection (LLM)...", "INFO")
            job_manager.update_status(job_id, STATUS_DETECTING_NAMES)
            start_time_detect = time.time()
            try:
                 # Call the name detection function (now returns map with context indices)
                 # *** MODIFICATION: Use renamed variable ***
                 proposed_map_with_context, context_snippets_result = detect_speaker_names(
                     transcript_segments=intermediate_segments, # Pass the processed segments
                     config=job_config                     # Pass the job config for LLM models/settings
                 )
                 # Check if the function indicated failure (e.g., map is None)
                 assert proposed_map_with_context is not None, "Speaker name detection function failed (returned None map, likely LLM parsing error)."
                 elapsed_detect = round(time.time() - start_time_detect, 2)
                 # proposed_map_with_context now holds the structure {SPEAKER_ID: {"name": ..., "reasoning_indices": [...]}}
                 detection_context_snippets = context_snippets_result or {} # Ensure it's a dict
                 # *** MODIFICATION: Update log message ***
                 job_manager.add_log(job_id, f"Name detection finished ({elapsed_detect}s). Proposed map (with context info) generated.", "SUCCESS")
                 # Optionally log the content at DEBUG level if needed:
                 # log(f"Proposed map content: {proposed_map_with_context}", "DEBUG")

                 # Save detection results to intermediate files (non-critical if saving fails)
                 try:
                      # json.dump correctly handles the nested dictionary structure
                      with open(proposed_map_path_abs, "w", encoding='utf-8') as f:
                           # *** MODIFICATION: Use renamed variable ***
                           json.dump(proposed_map_with_context, f, indent=2, ensure_ascii=False)
                      # *** MODIFICATION: Update log message ***
                      job_manager.add_log(job_id, f"Proposed speaker map (with context) saved: {proposed_map_path_rel}", "INFO")

                      # Saving context snippets remains the same
                      if detection_context_snippets:
                           with open(context_snippets_path_abs, "w", encoding='utf-8') as f:
                                json.dump(detection_context_snippets, f, indent=2, ensure_ascii=False)
                           job_manager.add_log(job_id, f"Context snippets saved: {context_snippets_path_rel}", "INFO")
                 except Exception as e:
                     job_manager.add_log(job_id, f"Warning: Failed save name detection results: {e}", "WARNING")
                     log(traceback.format_exc(), "DEBUG") # Log traceback on save failure

            except AssertionError as e: # Catch failure from assert check
                 # Log specific assertion error
                 log(f"Speaker name detection step failed assertion: {e}", "ERROR")
                 raise RuntimeError(f"Speaker name detection step failed: {e}") # Re-raise as RuntimeError
            except Exception as e: # Catch other unexpected errors during detection
                 log(f"Speaker name detection step encountered an unexpected error: {e}", "ERROR")
                 log(traceback.format_exc(), "DEBUG")
                 raise RuntimeError(f"Speaker name detection step encountered an error: {e}") from e

            # Update progress after successful name detection
            job_manager.update_progress(job_id, PROGRESS_AFTER_NAME_DETECT)
            check_stop(job_id, "speaker name detection") # Check for stop again after LLM call
        elif not NAME_DETECTOR_AVAILABLE:
             job_manager.add_log(job_id, "Speaker name detector module unavailable, skipping.", "WARNING")
        else: # Name detection disabled in config
            job_manager.add_log(job_id, "Automatic speaker name detection disabled in config, skipping.", "INFO")
        # If skipped or disabled, map/snippets remain empty, status goes to WAITING_FOR_REVIEW

        # --- Step 5: Finalize Part 1 ---
        # Set status to WAITING_FOR_REVIEW and store paths to intermediate data
        log(f"Step 5: Finalizing Part 1, setting status to '{next_status_after_step4}'...", "DEBUG")
        job_manager.add_log(job_id, "Part 1 processing complete. Ready for review.", "INFO")
        # Store relative paths for Part 2 / Review API
        review_info = {
            "intermediate_transcript_path": str(intermediate_transcript_path_rel),
            # Store path only if file actually exists after the attempt
            "proposed_map_path": str(proposed_map_path_rel) if proposed_map_path_abs and proposed_map_path_abs.exists() else None,
            "context_snippets_path": str(context_snippets_path_rel) if context_snippets_path_abs and context_snippets_path_abs.exists() else None,
        }
        log(f"Final review_info paths to store in job state: {review_info}", "DEBUG")
        # Update the job state atomically with final status, progress, and paths
        update_successful = job_manager._update_job_state(job_id, {
            "status": next_status_after_step4,
            "progress": PROGRESS_WAITING_REVIEW,
            "review_data_paths": review_info # Store the dict containing the relative paths
        })
        # If the update failed (e.g., job removed concurrently), raise an error to be caught below
        assert update_successful, f"Job Manager failed to update final state for job {job_id} in Part 1."
        log(f"Final state for Part 1 set successfully.", "DEBUG")

    # --- Exception Handling for the Entire Part 1 ---
    except (FileNotFoundError, ValueError, AssertionError, RuntimeError, InterruptedError) as e:
        # Handle known errors and stop requests cleanly
        status_to_set = STATUS_STOPPED if isinstance(e, InterruptedError) else STATUS_FAILED
        log_level = "WARNING" if status_to_set == STATUS_STOPPED else "ERROR"
        error_msg_detail = str(e)
        # Provide slightly more context in the error message
        if isinstance(e, FileNotFoundError): error_msg_prefix = "Required file not found"
        elif isinstance(e, ValueError): error_msg_prefix = "Invalid config or value"
        elif isinstance(e, AssertionError): error_msg_prefix = "Processing assertion failed"
        elif isinstance(e, RuntimeError): error_msg_prefix = "Processing step failed"
        elif isinstance(e, InterruptedError): error_msg_prefix = "Stopped by user request during"
        else: error_msg_prefix = "Pipeline error"
        # Combine for final message
        error_msg = f"Pipeline Part 1 {status_to_set.lower()}: {error_msg_prefix} - {error_msg_detail}"

        log(error_msg, log_level)
        log(traceback.format_exc(), "DEBUG") # Log full traceback at DEBUG level
        job_manager.set_error(job_id, error_msg) # Set final error state (will set status FAILED/STOPPED)
    except Exception as e:
        # Catch any other unexpected critical errors
        error_msg = f"Unexpected critical error in Pipeline Part 1: {e}"
        log(error_msg, "CRITICAL")
        log(traceback.format_exc(), "ERROR") # Log full traceback for critical errors
        job_manager.set_error(job_id, error_msg) # Sets status to FAILED

# --- End of pipeline_part1.py ---