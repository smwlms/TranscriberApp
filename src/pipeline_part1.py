# src/pipeline_part1.py
import time
import os
import json
import traceback
# Removed unused yaml import
from pathlib import Path
# Ensure Tuple is imported from typing
from typing import Dict, Any, List, Optional, Tuple

# Import necessary application components
from src.job_manager import job_manager, STATUS_RUNNING, STATUS_PROCESSING_AUDIO, \
    STATUS_DETECTING_NAMES, STATUS_WAITING_FOR_REVIEW, \
    STATUS_STOPPED, STATUS_FAILED # Adjusted status constants
# Import the main audio processing function (interface is stable after its refactor)
from src.transcriber import transcribe_and_diarize, DEFAULT_WHISPER_MODEL, \
     DEFAULT_COMPUTE_TYPE, DEFAULT_PYANNOTE_PIPELINE
# Safely import the optional speaker name detector
try:
    from src.speaker_name_detector import detect_speaker_names
    NAME_DETECTOR_AVAILABLE = True
except ImportError:
    # Log warning if module not found
    # Need log defined first, but log isn't available globally here yet.
    # Use print for this specific bootstrap warning.
    print("[PipelinePart1 WARNING] Speaker name detector module (src.speaker_name_detector) not found, disabling automatic name detection.")
    NAME_DETECTOR_AVAILABLE = False
    # Define a dummy function with the correct signature and type hints to prevent runtime errors
    def detect_speaker_names(*args, **kwargs) -> Tuple[Dict[str, Optional[str]], Dict[int, str]]:
        """Dummy function for when speaker_name_detector is unavailable."""
        return {}, {} # Return empty dicts

# Import Utilities
from src.utils.load_config import load_config
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log # Now log is imported
from src.utils.pipeline_helpers import check_stop, merge_configs

# Constants for directory names relative to project root
RESULTS_DIR_NAME = "results"
TRANSCRIPTS_DIR_NAME = "transcripts"
# Define standard intermediate filenames
DEFAULT_INTERMEDIATE_JSON_FILENAME = "intermediate_transcript.json"
DEFAULT_PROPOSED_MAP_FILENAME = "intermediate_proposed_map.json"
DEFAULT_CONTEXT_SNIPPETS_FILENAME = "intermediate_context.json"

# Constants for reporting progress milestones (0-100 scale)
PROGRESS_START = 5
PROGRESS_AFTER_AUDIO_PROCESSING = 35 # After transcription & diarization complete
PROGRESS_AFTER_NAME_DETECT = 45      # After optional name detection
PROGRESS_WAITING_REVIEW = 48         # Final progress state for Part 1

def run_part1(job_id: str, config_overrides: Dict[str, Any]):
    """
    Runs the first part of the processing pipeline:
    1. Loads and merges configuration.
    2. Validates input paths and parameters.
    3. Performs audio processing (transcription and diarization).
    4. Saves the intermediate (raw) transcript.
    5. Optionally runs speaker name detection and saves its results.
    6. Sets the job status to WAITING_FOR_REVIEW and stores intermediate file paths.

    Args:
        job_id: The unique identifier for this job.
        config_overrides: Dictionary of configuration settings overriding defaults,
                          typically from the API request.
    """
    # Initialize local variables for clarity
    job_config: Dict[str, Any] = {}
    intermediate_segments: Optional[List[Dict[str, Any]]] = None
    # Define paths as Path objects for easier manipulation
    intermediate_transcript_path_abs: Optional[Path] = None
    proposed_map_path_abs: Optional[Path] = None
    context_snippets_path_abs: Optional[Path] = None
    intermediate_transcript_path_rel: Optional[Path] = None
    proposed_map_path_rel: Optional[Path] = None
    context_snippets_path_rel: Optional[Path] = None

    # --- Start Processing ---
    job_manager.update_progress(job_id, PROGRESS_START, status=STATUS_RUNNING)
    job_manager.add_log(job_id, "Pipeline Part 1 started.", "INFO")

    try:
        # --- Step 1: Load and Merge Configuration ---
        log(f"Step 1: Loading and merging configuration...", "DEBUG")
        base_config = load_config() # Handles default generation & schema updates
        job_config = merge_configs(base_config, config_overrides) # Apply job-specific overrides
        # Store the final configuration used for this job run in the Job Manager
        job_manager._update_job_state(job_id, {"config": job_config})
        log(f"Part 1: Configuration prepared. Mode: {job_config.get('mode', 'N/A')}", "INFO")
        check_stop(job_id, "configuration loading") # Check for stop request


        # --- Step 2: Validate Input Paths and Parameters ---
        log(f"Step 2: Validating inputs...", "DEBUG")
        input_audio_rel_path_str = job_config.get("input_audio")
        if not input_audio_rel_path_str:
            raise ValueError("Configuration Error: 'input_audio' path missing.")
        input_audio_rel_path = Path(input_audio_rel_path_str)
        input_audio_abs_path = (PROJECT_ROOT / input_audio_rel_path).resolve()
        # Final check: Does the resolved file exist?
        if not input_audio_abs_path.is_file():
             raise FileNotFoundError(f"Input audio file not found at resolved path: {input_audio_abs_path}")
        log(f"Input audio validated: {input_audio_abs_path.name}", "INFO")


        # --- Define and Prepare Intermediate File Paths ---
        # Construct relative paths first (for storage in job state)
        int_transcript_rel_str = job_config.get(
            "intermediate_transcript_path", # Check if user specified a path in config
            str(Path(TRANSCRIPTS_DIR_NAME) / DEFAULT_INTERMEDIATE_JSON_FILENAME) # Default path
        )
        intermediate_transcript_path_rel = Path(int_transcript_rel_str)
        proposed_map_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_PROPOSED_MAP_FILENAME)
        context_snippets_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_CONTEXT_SNIPPETS_FILENAME)

        # Construct absolute paths (for file I/O)
        intermediate_transcript_path_abs = PROJECT_ROOT / intermediate_transcript_path_rel
        proposed_map_path_abs = PROJECT_ROOT / proposed_map_path_rel
        context_snippets_path_abs = PROJECT_ROOT / context_snippets_path_rel

        # Ensure parent directory for these intermediate files exists
        intermediate_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        log(f"Intermediate transcript relative path: {intermediate_transcript_path_rel}", "DEBUG")


        # --- Extract Relevant Config Values ---
        whisper_model = job_config.get("whisper_model", DEFAULT_WHISPER_MODEL)
        compute_type = job_config.get("compute_type", DEFAULT_COMPUTE_TYPE)
        language = job_config.get("language") # None is valid for auto-detect
        pyannote_pipeline = job_config.get("pyannote_pipeline", DEFAULT_PYANNOTE_PIPELINE)
        hf_token = os.environ.get("HUGGING_FACE_TOKEN") or job_config.get("hf_token")
        name_detection_enabled = job_config.get("speaker_name_detection_enabled", True)


        # --- Step 3: Audio Processing (Transcription & Diarization) ---
        log(f"Step 3: Starting audio processing (Transcription & Diarization)...", "INFO")
        job_manager.update_status(job_id, STATUS_PROCESSING_AUDIO) # Single status for combined step
        start_time_audio = time.time()

        intermediate_segments = transcribe_and_diarize(
            input_audio_path=input_audio_abs_path,
            whisper_model_size=whisper_model,
            compute_type=compute_type,
            language=language,
            hf_token=hf_token,
            pyannote_pipeline_name=pyannote_pipeline
        )
        # Check for failure
        if intermediate_segments is None:
             raise RuntimeError("Audio processing (transcription and diarization) failed.")

        elapsed_audio = round(time.time() - start_time_audio, 2)
        job_manager.add_log(job_id, f"Audio processing finished in {elapsed_audio}s.", "SUCCESS")

        # Save the intermediate result (raw transcript with speaker IDs)
        try:
            with open(intermediate_transcript_path_abs, "w", encoding='utf-8') as f:
                 json.dump(intermediate_segments, f, indent=2, ensure_ascii=False)
            job_manager.add_log(job_id, f"Intermediate transcript saved: {intermediate_transcript_path_rel}", "INFO")
        except Exception as e:
            raise RuntimeError(f"Failed to save intermediate transcript to '{intermediate_transcript_path_abs}': {e}")

        # Update progress after this significant step
        job_manager.update_progress(job_id, PROGRESS_AFTER_AUDIO_PROCESSING)
        check_stop(job_id, "audio processing") # Check for stop request


        # --- Step 4: Speaker Name Detection (Optional LLM step) ---
        detected_speaker_map: Dict[str, Optional[str]] = {}
        detection_context_snippets: Dict[int, str] = {}
        # Determine the status to transition to after this section
        next_status_after_step4 = STATUS_WAITING_FOR_REVIEW

        if name_detection_enabled and NAME_DETECTOR_AVAILABLE:
            log(f"Step 4: Attempting speaker name detection (LLM)...", "INFO")
            job_manager.update_status(job_id, STATUS_DETECTING_NAMES)
            start_time_detect = time.time()
            try:
                 detected_map_result, context_snippets_result = detect_speaker_names(
                     transcript_segments=intermediate_segments, # Use the result from step 3
                     config=job_config                     # Pass job config for LLM settings
                 )
                 elapsed_detect = round(time.time() - start_time_detect, 2)

                 # Handle detector failure
                 if detected_map_result is None:
                      raise RuntimeError("Speaker name detection function failed.")

                 detected_speaker_map = detected_map_result
                 detection_context_snippets = context_snippets_result or {}
                 job_manager.add_log(job_id, f"Speaker name detection finished in {elapsed_detect}s. Proposed map: {detected_speaker_map}", "SUCCESS")

                 # Save detection results to files for the review API
                 try:
                      # Save proposed map (using absolute path)
                      with open(proposed_map_path_abs, "w", encoding='utf-8') as f:
                           json.dump(detected_speaker_map, f, indent=2, ensure_ascii=False)
                      job_manager.add_log(job_id, f"Proposed speaker map saved: {proposed_map_path_rel}", "INFO")
                      # Save context snippets if generated (using absolute path)
                      if detection_context_snippets:
                           with open(context_snippets_path_abs, "w", encoding='utf-8') as f:
                                json.dump(detection_context_snippets, f, indent=2, ensure_ascii=False)
                           job_manager.add_log(job_id, f"Context snippets saved: {context_snippets_path_rel}", "INFO")
                 except Exception as e:
                      # Log saving error but don't necessarily fail the pipeline
                      job_manager.add_log(job_id, f"Warning: Failed to save name detection results (map/context files): {e}", "WARNING")

            except Exception as e:
                 # Treat errors during the detection step itself as critical? Let's assume yes.
                 raise RuntimeError(f"Speaker name detection step encountered an error: {e}")

            # Update progress after name detection step completes
            job_manager.update_progress(job_id, PROGRESS_AFTER_NAME_DETECT)
            # check_stop removed from here, moved below

        elif not NAME_DETECTOR_AVAILABLE:
             job_manager.add_log(job_id, "Speaker name detector module not found, skipping.", "WARNING")
        else: # Name detection disabled in config
            job_manager.add_log(job_id, "Automatic speaker name detection disabled in config.", "INFO")
        # If skipped, map/snippets remain empty dicts, next status is still WAITING_FOR_REVIEW

        # --- !! START DEBUG BLOCK !! ---
        # Log entry into the finalization step
        log(f"--- DEBUG: Checkpoint A - Passed Name Detection Block ---", "ERROR") # Use ERROR level for visibility

        # --- Step 5: Finalize Part 1 and Set State for Review ---
        log(f"--- DEBUG: Checkpoint B - Entering Step 5 ---", "ERROR")
        # Variable should be set based on whether detection ran etc, but here it's always WAITING_FOR_REVIEW
        # next_status_after_step4 = STATUS_WAITING_FOR_REVIEW # Already set
        log(f"Step 5 Checkpoint 1: Preparing to finalize. Next status should be: '{next_status_after_step4}'", "DEBUG")
        job_manager.add_log(job_id, "Part 1 processing complete. Preparing for review.", "INFO")
        log(f"Step 5 Checkpoint 2: Added 'Part 1 complete' job log.", "DEBUG")

        # --- Attempt to create review_info dictionary ---
        review_info = {} # Initialize
        try:
            log(f"Step 5 Checkpoint 2a: Creating review_info dict...", "DEBUG")
            # Ensure paths used here are defined and valid Path objects
            review_info = {
                "intermediate_transcript_path": str(intermediate_transcript_path_rel), # Relative path for API
                "proposed_map_path": str(proposed_map_path_rel) if proposed_map_path_abs and proposed_map_path_abs.exists() else None,
                "context_snippets_path": str(context_snippets_path_rel) if context_snippets_path_abs and context_snippets_path_abs.exists() else None,
            }
            log(f"Step 5 Checkpoint 3: Successfully created review_info: {review_info}", "DEBUG")
        except Exception as e_info:
             log(f"CRITICAL ERROR creating review_info dictionary: {e_info}", "CRITICAL")
             # Re-raise to be caught by the main exception handler for Part 1
             raise RuntimeError("Failed to create review_info dictionary") from e_info

        # --- Move check_stop here, after potentially problematic code ---
        try:
             log(f"Step 5 Checkpoint 3a: Running check_stop...", "DEBUG")
             check_stop(job_id, "before final state update") # Check for stop request here
             log(f"Step 5 Checkpoint 4: Passed check_stop.", "DEBUG")
        except InterruptedError as ie:
              # Re-raise immediately if stop was requested here to trigger correct handling
              raise ie
        except Exception as e_stop:
             log(f"CRITICAL ERROR during check_stop call: {e_stop}", "CRITICAL")
             raise RuntimeError("Failed during stop check") from e_stop


        # --- Attempt the final state update ---
        log(f"Step 5 Checkpoint 5: Attempting final state update call to JobManager...", "DEBUG")
        update_successful = False # Initialize
        try:
             # Use the internal method for atomic update
             update_successful = job_manager._update_job_state(job_id, {
                 "status": next_status_after_step4, # Should be STATUS_WAITING_FOR_REVIEW
                 "progress": PROGRESS_WAITING_REVIEW,
                 "review_data_paths": review_info # The dictionary created above
             })
        except Exception as e_update:
             log(f"CRITICAL ERROR during final _update_job_state call: {e_update}", "CRITICAL")
             log(traceback.format_exc(), "ERROR")
             # Raise error to be caught by the main handler, ensuring job status becomes FAILED
             raise RuntimeError("Failed during final job state update") from e_update

        # --- Log result of update ---
        log(f"Step 5 Checkpoint 6: Result of final state update call was: {update_successful}", "DEBUG")
        if not update_successful:
             # This might happen if the job was somehow removed, log critically.
             log(f"CRITICAL WARNING: Final state update call for Part 1 failed (returned False). Job might be stuck (job_id: {job_id})!", "CRITICAL")
             # Raise an error to ensure the job status becomes FAILED
             raise RuntimeError(f"Job Manager failed to update final state for job {job_id} in Part 1.")
        else:
             log(f"Step 5 Checkpoint 7: Final state for Part 1 set successfully in Job Manager.", "DEBUG")

        log(f"--- DEBUG: Checkpoint C - Exiting Step 5 successfully ---", "ERROR") # Final success log for try block
        # --- !! END DEBUG BLOCK !! ---

    # --- Exception Handling for the Entire Part 1 ---
    except FileNotFoundError as e:
        error_msg = f"Pipeline Part 1 Error: Required file not found - {e}"
        log(error_msg, "ERROR")
        job_manager.set_error(job_id, error_msg) # Mark job as failed
    except ValueError as e: # Catch configuration or path validation errors
        error_msg = f"Pipeline Part 1 Error: Invalid configuration or value - {e}"
        log(error_msg, "ERROR")
        job_manager.set_error(job_id, error_msg)
    except InterruptedError as e:
        # Stop requested via check_stop() helper
        error_msg = f"Pipeline Part 1 stopped by user request." # Simple message
        job_manager.update_status(job_id, STATUS_STOPPED) # Set final status
        job_manager.add_log(job_id, error_msg, "WARNING") # Log the interruption
        log(f"Job {job_id} operation stopped cleanly via request: {e}", "INFO") # General log
    except RuntimeError as e:
        # Catch failures explicitly raised from specific steps within Part 1
        error_msg = f"Pipeline Part 1 failed during processing step: {e}"
        log(error_msg, "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log traceback for runtime errors
        job_manager.set_error(job_id, error_msg)
    except Exception as e:
        # Catch any other unexpected critical errors during execution
        error_msg = f"Unexpected critical error in Pipeline Part 1: {e}"
        log(error_msg, "CRITICAL")
        log(traceback.format_exc(), "ERROR") # Log full traceback for critical errors
        job_manager.set_error(job_id, error_msg)

# --- End of pipeline_part1.py ---