# File: src/pipeline_part2.py (Refactored with Helper Functions and Corrected Imports)

import time
import os
import json
import traceback
from pathlib import Path
# GECORRIGEERDE IMPORT: Voeg Tuple toe
from typing import Dict, Any, List, Optional, TypedDict, Tuple

# Import application components
from src.job_manager import job_manager
# GECORRIGEERDE IMPORT: Importeer ALLE benodigde constanten
from src.constants import (
    STATUS_MAPPING_SPEAKERS, STATUS_REFORMATTING, STATUS_ANALYZING,
    STATUS_COMPLETED, STATUS_FAILED, STATUS_STOPPED, STATUS_UNKNOWN, # Statuses
    RESULTS_FOLDER_NAME, TRANSCRIPTS_FOLDER_NAME, AUDIO_FOLDER_NAME, # Folder names
    INTERMEDIATE_PROPOSED_MAP_FILENAME, INTERMEDIATE_CONTEXT_SNIPPETS_FILENAME, # Intermediate cleanup files
    INTERMEDIATE_TRANSCRIPT_JSON_FILENAME, # <-- GECORRIGEERDE IMPORT
    FINAL_TRANSCRIPT_JSON_FILENAME, FINAL_HTML_TRANSCRIPT_FILENAME,
    FINAL_SUMMARY_FILENAME, FINAL_ADVANCED_ANALYSIS_FILENAME, # Final File names
    PROGRESS_AFTER_MAPPING, PROGRESS_AFTER_REFORMAT, PROGRESS_AFTER_ANALYSIS,
    PROGRESS_COMPLETE, PROGRESS_WAITING_REVIEW, # Progress markers
    LLM_TASK_SUMMARY, LLM_ADVANCED_TASK_KEYS, LLM_TASK_FINAL_ANALYSIS, # LLM Tasks
    LLM_TASK_INTENT, LLM_TASK_ACTIONS, LLM_TASK_EMOTION, LLM_TASK_QUESTIONS, LLM_TASK_LEGAL # <-- GECORRIGEERDE IMPORTS
)

# Import core processing functions
from src.speaker_mapping import apply_speaker_mapping
from src.transcript_reformatter import format_transcript_html

# Import LLM functions/modules
from src.utils.llm import run_with_fallback # Keep run_with_fallback if needed for generic calls
from src.analysis_tasks import advanced_tasks # Keep import for advanced tasks module

# Import helpers and utilities
from src.utils.pipeline_helpers import check_stop # merge_configs is in utils, not pipeline_helpers
from src.utils.config_schema import PROJECT_ROOT # Assuming PROJECT_ROOT is here or utils.__init__
from src.database_logger import log_job_to_db, get_db_path
from src.utils.log import log

# --- Define Folder Paths using constants ---
RESULTS_DIR = PROJECT_ROOT / RESULTS_FOLDER_NAME
TRANSCRIPTS_DIR = PROJECT_ROOT / TRANSCRIPTS_FOLDER_NAME
AUDIO_DIR = PROJECT_ROOT / AUDIO_FOLDER_NAME # Define audio dir path as well

# --- Type Hint for Segment Structure (based on merge.py output) ---
# This helps with clarity when working with segment lists
class TranscriptSegment(TypedDict, total=False):
    start: float
    end: float
    text: str
    speaker: str # Original speaker ID from diarization/merge
    words: List[Dict[str, Any]] # Word-level timestamps and data
    speaker_name: str # Added by speaker_mapping

# --- Helper Function: Prepare Initial Job Data ---
def _prepare_part2(job_id: str) -> Tuple[Dict[str, Any], Path, Optional[float]]:
    """
    Retrieves essential job data and validates paths before starting Part 2 processing.
    """
    log(f"Preparing for Part 2 for job {job_id}...", "DEBUG", job_id=job_id)
    job_data = job_manager.get_status(job_id)
    if not job_data:
         # Return None/empty for config and paths so finally block doesn't crash
         # This init helper should ideally raise, the caller handles the final error set
         raise ValueError(f"Job {job_id} not found in JobManager. Aborting Part 2 initialization.")

    job_config = job_data.get("config")
    if not isinstance(job_config, dict):
        raise ValueError(f"Job config missing or invalid for job {job_id}.")

    review_paths = job_data.get("review_data_paths", {})
    intermediate_transcript_rel_path_str = review_paths.get("intermediate_transcript_path")
    if not intermediate_transcript_rel_path_str:
        raise ValueError("Intermediate transcript path missing in job data.")

    # Construct absolute path for intermediate transcript
    intermediate_transcript_path_abs = (PROJECT_ROOT / Path(intermediate_transcript_rel_path_str)).resolve()
    if not intermediate_transcript_path_abs.is_file():
         raise FileNotFoundError(f"Intermediate transcript file not found at: {intermediate_transcript_path_abs}")

    start_time_total = job_data.get("start_time")
    if start_time_total is None:
         log(f"Warning: Job start time not found in job data for {job_id}.", "WARNING", job_id=job_id)
         # Can still proceed, but total duration won't be logged

    log(f"Initialization for Part 2 complete for job {job_id}. Intermediate transcript: {intermediate_transcript_path_abs.name}", "DEBUG", job_id=job_id)
    return job_config, intermediate_transcript_path_abs, start_time_total

# --- Helper Function: Load Intermediate Segments ---
def _load_intermediate_segments(intermediate_transcript_path_abs: Path, job_id: str) -> List[TranscriptSegment]:
    """
    Loads transcript segments from the intermediate JSON file.
    """
    log(f"Step 1: Loading intermediate segments from {intermediate_transcript_path_abs.name}", "INFO", job_id=job_id)
    try:
        with open(intermediate_transcript_path_abs, "r", encoding='utf-8') as f:
            # json.load will raise JSONDecodeError on invalid JSON
            segments_to_process = json.load(f)
        # Validate that the loaded data is a list
        if not isinstance(segments_to_process, list):
             raise ValueError("Loaded intermediate transcript data is not a list.")
        # Optional: Add more specific validation here for segment structure if needed

        log(f"Loaded {len(segments_to_process)} intermediate segments.", "DEBUG", job_id=job_id)
        return segments_to_process # Return the loaded list
    except FileNotFoundError:
        raise FileNotFoundError(f"Intermediate transcript file not found: {intermediate_transcript_path_abs}") # Re-raise if file disappeared
    except json.JSONDecodeError as e:
         raise RuntimeError(f"Failed to decode JSON from intermediate transcript file '{intermediate_transcript_path_abs.name}': {e}") from e
    except Exception as e:
         raise RuntimeError(f"Error loading intermediate transcript from '{intermediate_transcript_path_abs.name}': {e}") from e

# --- Helper Function: Apply Final Speaker Mapping ---
def _apply_speaker_mapping_step(segments_to_process: List[TranscriptSegment], final_speaker_map: Dict[str, Optional[str]], job_id: str) -> List[TranscriptSegment]:
    """
    Applies the final speaker names based on the user-provided map.
    """
    job_manager.update_status(job_id, STATUS_MAPPING_SPEAKERS)
    log(f"Step 2: Applying final speaker map...", "INFO", job_id=job_id)

    # final_speaker_map is received as argument, should be a dictionary
    if not isinstance(final_speaker_map, dict):
         raise ValueError(f"Invalid final speaker map provided for job {job_id}. Expected dictionary.")

    final_segments = apply_speaker_mapping(segments_to_process, final_speaker_map)
    if final_segments is None:
         # apply_speaker_mapping shouldn't return None based on its code, but defensive check
         raise RuntimeError("Applying final speaker mapping failed unexpectedly.")

    log(f"Final speaker name assignment complete. Processed {len(final_segments)} segments.", "SUCCESS", job_id=job_id)
    job_manager.update_progress(job_id, PROGRESS_AFTER_MAPPING)
    check_stop(job_id, "applying speaker mapping")

    return final_segments # Return the segments with speaker names

# --- Helper Function: Save Final Transcript JSON ---
def _save_final_transcript_json(final_segments: List[TranscriptSegment], job_id: str) -> Tuple[Path, Path]:
    """
    Saves the final transcript segments (with speaker names) to a JSON file.
    """
    # Construct absolute path for the final transcript JSON
    final_transcript_path_abs = (TRANSCRIPTS_DIR / FINAL_TRANSCRIPT_JSON_FILENAME).resolve()
    final_transcript_path_rel = final_transcript_path_abs.relative_to(PROJECT_ROOT)

    log(f"Step 3: Saving final transcript JSON to {final_transcript_path_rel}...", "INFO", job_id=job_id)
    try:
        # Ensure directory exists
        final_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        # Save the segments list as JSON
        with open(final_transcript_path_abs, "w", encoding='utf-8') as f:
             # This is a point where JSON serialization can fail - EXPLICITLY CATCH TypeError
             json.dump(final_segments, f, indent=2, ensure_ascii=False)
        log(f"Final transcript JSON saved: {final_transcript_path_rel}", "INFO", job_id=job_id)
        return final_transcript_path_abs, final_transcript_path_rel
    except TypeError as e:
         # Explicitly catch TypeError - indicates data structure issue in final_segments
         error_msg = f"Failed to serialize final transcript data to '{final_transcript_path_abs.name}': {e}. Data structure issue detected."
         log(error_msg, "CRITICAL", job_id=job_id)
         log(traceback.format_exc(), "DEBUG", job_id=job_id)
         # Treat as critical error, subsequent steps depend on this file
         raise RuntimeError(error_msg) from e
    except Exception as e:
         # Catch other save errors (disk full, permissions etc.)
         error_msg = f"Failed to save final transcript JSON to '{final_transcript_path_abs.name}': {e}"
         log(error_msg, "CRITICAL", job_id=job_id)
         log(traceback.format_exc(), "DEBUG", job_id=job_id)
         # Treat as critical error
         raise RuntimeError(error_msg) from e

# --- Helper Function: Generate and Save HTML Transcript ---
def _generate_and_save_html(final_segments: List[TranscriptSegment], job_id: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Generates HTML transcript and saves it. Returns paths or None if failed.
    """
    job_manager.update_status(job_id, STATUS_REFORMATTING)
    log(f"Step 4: Generating HTML transcript...", "INFO", job_id=job_id)

    html_transcript_path_abs = (RESULTS_DIR / FINAL_HTML_TRANSCRIPT_FILENAME).resolve()
    html_transcript_path_rel = html_transcript_path_abs.relative_to(PROJECT_ROOT)

    try:
        # format_transcript_html works with the final_segments list (which should be serializable)
        html_output_string = format_transcript_html(final_segments)
        if html_output_string:
             # Ensure results directory exists before saving
             html_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
             # Save the generated HTML string
             with open(html_transcript_path_abs, "w", encoding='utf-8') as f: f.write(html_output_string)
             log(f"HTML transcript saved: {html_transcript_path_rel}", "SUCCESS", job_id=job_id)
             return html_transcript_path_abs, html_transcript_path_rel
        else:
             log("HTML generation returned empty string. Skipping save.", "WARNING", job_id=job_id)
             return None, None # Indicate save was skipped
    except Exception as e:
        # HTML generation/save failure is less critical, log warning but return None paths
        log(f"Warning: HTML transcript generation/saving failed: {e}", "WARNING", job_id=job_id)
        log(traceback.format_exc(), "DEBUG", job_id=job_id)
        return None, None # Indicate failure

# --- Helper Function: Prepare Text for LLM Analysis ---
def _prepare_text_for_llm(final_transcript_json_path_abs: Optional[Path], job_id: str) -> Optional[str]:
    """
    Loads the final transcript JSON and formats the text for LLM analysis.
    Returns the prepared text string or None if preparation failed.
    """
    # Ensure the final transcript JSON file was created successfully
    if not final_transcript_json_path_abs or not final_transcript_json_path_abs.is_file():
         log(f"Final transcript JSON file not found at {final_transcript_json_path_abs}. Cannot prepare text for LLM analysis.", "ERROR", job_id=job_id)
         return None # Cannot proceed without the file

    try:
        log(f"Loading text from {final_transcript_json_path_abs.name} for LLM analysis...", "DEBUG", job_id=job_id)
        with open(final_transcript_json_path_abs, "r", encoding='utf-8') as f:
             # Reload segments - safer than relying on a potentially modified in-memory list
             loaded_final_segments_for_text = json.load(f)

        if not isinstance(loaded_final_segments_for_text, list):
             raise ValueError("Invalid format in final transcript JSON (expected list) when loading for text prep.")

        # Construct text string including speaker names for LLM context
        text_lines = []
        if loaded_final_segments_for_text: # Only process if list is not empty
            text_lines = [
                f"{segment.get('speaker_name', 'Unknown')}: {segment.get('text', '').strip()}" # Use stripped text
                for segment in loaded_final_segments_for_text if isinstance(segment, dict) and segment.get('text') is not None
            ]

        analysis_input_text = "\n".join(text_lines).strip()

        if not analysis_input_text:
             log("No text content found in final transcript JSON after loading for text prep. Skipping LLM analysis.", "WARNING", job_id=job_id)
             return None # Indicate no text was found
        else:
             log(f"Prepared text input for LLM analysis ({len(analysis_input_text)} chars).", "DEBUG", job_id=job_id)
             return analysis_input_text # Return the prepared text string

    except FileNotFoundError:
         log(f"Final transcript JSON file disappeared during text preparation: {final_transcript_json_path_abs.name}.", "ERROR", job_id=job_id)
         return None
    except json.JSONDecodeError as e:
         log(f"Failed to decode JSON from final transcript file '{final_transcript_json_path_abs.name}' during text preparation: {e}.", "ERROR", job_id=job_id)
         return None
    except Exception as e:
         log(f"Unexpected error loading/preparing text from final transcript '{final_transcript_json_path_abs.name}' for analysis: {e}. Skipping analysis.", "ERROR", job_id=job_id)
         log(traceback.format_exc(), "DEBUG", job_id=job_id)
         return None

# --- Helper Function: Run LLM Analysis Steps ---
def _run_llm_analysis_step(
    analysis_input_text: Optional[str], # Accepts Optional[str] as text prep might fail
    job_config: Dict[str, Any],
    job_id: str
    ) -> Tuple[Optional[str], Dict[str, Optional[str]], Optional[Path], Optional[Path]]:
    """
    Orchestrates LLM analysis based on mode (fast or advanced).
    Returns summary result, advanced results dictionary, and paths to saved files.
    Returns (None, {}, None, None) if analysis is skipped or fails critically.
    """
    job_manager.update_status(job_id, STATUS_ANALYZING)
    mode = job_config.get("mode", "fast")
    log(f"Step 5: Starting LLM analysis (Mode: {mode})...", "INFO", job_id=job_id)
    start_time_analysis = time.time()

    # Initialize results and paths
    summary_result: Optional[str] = None
    advanced_results: Dict[str, Optional[str]] = {} # Stores results as strings or None
    summary_path_abs: Optional[Path] = None
    advanced_analysis_path_abs: Optional[Path] = None

    # Check if analysis is possible/needed
    if not analysis_input_text:
         log(f"LLM analysis skipped because transcript text could not be prepared or was empty.", "WARNING", job_id=job_id)
         # Return initial None/empty results
         return None, {}, None, None

    # Validate LLM Config section before proceeding
    llm_models_config = job_config.get("llm_models")
    if not isinstance(llm_models_config, dict) or not llm_models_config:
        log("LLM analysis requires 'llm_models' dictionary in config with models defined. Skipping LLM analysis execution.", "WARNING", job_id=job_id)
        # Return initial None/empty results
        return None, {}, None, None

    try: # Inner try block for the actual LLM analysis execution

        extra_context = job_config.get("extra_context_prompt", "")

        # Define output paths using constants and ensure results directory exists
        try:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            summary_path_abs = (RESULTS_DIR / FINAL_SUMMARY_FILENAME).resolve()
            advanced_analysis_path_abs = (RESULTS_DIR / FINAL_ADVANCED_ANALYSIS_FILENAME).resolve()
        except OSError as e:
            raise RuntimeError(f"Failed to create results directory '{RESULTS_DIR}' for analysis output: {e}") from e


        if mode == "fast":
             log(f"Running LLM 'fast' mode ({LLM_TASK_SUMMARY})...", "INFO", job_id=job_id)
             # --- Call summarize_transcript with text ---
             summary_result = advanced_tasks.summary(analysis_input_text, job_config, extra_context)
             # ------------------------------------------
             if summary_result is None:
                 log(f"Summary generation failed for job {job_id}.", "ERROR", job_id=job_id)
                 # summary_result remains None, will be reflected in final_result_data
             else: # Only save if summary result is not None
                 try:
                      with open(summary_path_abs, "w", encoding='utf-8') as f: f.write(summary_result)
                      log(f"Summary saved: {summary_path_abs.relative_to(PROJECT_ROOT)}", "SUCCESS", job_id=job_id) # Log relative path
                 except IOError as e:
                     log(f"Failed to save summary file '{summary_path_abs.name}': {e}", "ERROR", job_id=job_id)
                     log(traceback.format_exc(), "DEBUG", job_id=job_id)
                     summary_path_abs = None # Mark path as None if save failed

        elif mode == "advanced":
             log(f"Running LLM 'advanced' mode...", "INFO", job_id=job_id)
             # Use dictionary to store results from individual tasks (expected string/None)
             temp_intermediate_results: Dict[str, Optional[str]] = {}

             # Use the list of task keys from constants
             tasks_to_run_keys = LLM_ADVANCED_TASK_KEYS
             total_tasks = len(tasks_to_run_keys) + 1 # +1 for the final aggregation
             completed_tasks = 0

             # Map task keys to function calls
             task_functions = {
                 LLM_TASK_SUMMARY: advanced_tasks.summary,
                 LLM_TASK_INTENT: advanced_tasks.intent,
                 LLM_TASK_ACTIONS: advanced_tasks.actions,
                 LLM_TASK_EMOTION: advanced_tasks.emotion,
                 LLM_TASK_QUESTIONS: advanced_tasks.questions,
                 LLM_TASK_LEGAL: advanced_tasks.legal,
             }

             for task_name in tasks_to_run_keys:
                  check_stop(job_id, f"advanced LLM task '{task_name}'")
                  job_manager.add_log(job_id, f"Running LLM task: {task_name}...", "INFO")

                  task_func = task_functions.get(task_name)
                  if not task_func:
                      log(f"Warning: No function found for LLM task key '{task_name}'. Skipping.", "WARNING", job_id=job_id)
                      temp_intermediate_results[task_name] = f"Error: Task function missing for '{task_name}'" # Store error message string
                      continue # Skip to next task key

                  try:
                      # --- Call advanced task function with text ---
                      task_result = task_func(analysis_input_text, job_config, extra_context)
                      # --------------------------------------------
                      # Store the result (should be string or None based on advanced_tasks.py)
                      temp_intermediate_results[task_name] = task_result
                      log_level = "SUCCESS" if task_result is not None else "WARNING"
                      log(f"LLM task '{task_name}' finished.", log_level, job_id=job_id)
                  except Exception as task_e:
                      # Catch errors *within* a single task execution
                      log(f"Error during LLM task '{task_name}': {task_e}", "ERROR", job_id=job_id)
                      log(traceback.format_exc(), "DEBUG", job_id=job_id)
                      # Store an error message string in the results
                      temp_intermediate_results[task_name] = f"Error: {task_e}"
                  finally:
                      completed_tasks += 1 # Increment count even if task failed
                      # Update progress incrementally based on completed tasks
                      # Progress update happens even if task failed, reflecting effort spent
                      current_progress = PROGRESS_AFTER_REFORMAT + int((completed_tasks / total_tasks) * (PROGRESS_AFTER_ANALYSIS - PROGRESS_AFTER_REFORMAT))
                      job_manager.update_progress(job_id, current_progress)


             # --- Run Final Aggregating Analysis ---
             check_stop(job_id, "final LLM analysis aggregation")
             job_manager.add_log(job_id, "Running final aggregating LLM analysis...", "INFO")
             try:
                 # --- Call run_final_analysis with intermediate string results ---
                 # temp_intermediate_results dictionary contains strings/None/error strings - should be serializable
                 final_agg_result = advanced_tasks.run_final_analysis(temp_intermediate_results, job_config, extra_context)
                 # -----------------------------------------------------------
                 advanced_results = temp_intermediate_results.copy() # Copy intermediate results
                 # Add final aggregation result (should be string or None)
                 advanced_results[LLM_TASK_FINAL_ANALYSIS] = final_agg_result

                 log(f"Final aggregating analysis completed.", "SUCCESS", job_id=job_id)
             except Exception as final_agg_e:
                 log(f"Error during final aggregating analysis task: {final_agg_e}", "ERROR", job_id=job_id)
                 log(traceback.format_exc(), "DEBUG", job_id=job_id)
                 # Store an error message string in the final result
                 advanced_results = temp_intermediate_results.copy() # Ensure intermediate results are included
                 advanced_results[LLM_TASK_FINAL_ANALYSIS] = f"Error during final aggregation: {final_agg_e}"

             # Save advanced results JSON
             try:
                  # advanced_results dictionary contains strings/None/error strings - should be serializable
                  with open(advanced_analysis_path_abs, "w", encoding='utf-8') as f:
                      # THIS IS A POTENTIAL SOURCE OF TypeError if advanced_results contains non-serializable objects
                      json.dump(advanced_results, f, indent=2, ensure_ascii=False)
                  log(f"Advanced analysis results saved: {advanced_analysis_path_abs.relative_to(PROJECT_ROOT)}", "SUCCESS", job_id=job_id) # Log relative path
             except TypeError as e:
                 # Explicitly catch TypeError - indicates data structure issue in advanced_results
                 error_msg = f"Failed to serialize advanced analysis results to '{advanced_analysis_path_abs.name}': {e}. Data structure issue detected."
                 log(error_msg, "CRITICAL", job_id=job_id)
                 log(traceback.format_exc(), "DEBUG", job_id=job_id)
                 # This is a critical failure if results cannot be saved
                 raise RuntimeError(error_msg) from e
             except Exception as e: # Other save errors (disk full, permissions etc.)
                  error_msg = f"Failed to save advanced analysis JSON '{advanced_analysis_path_abs.name}': {e}"
                  log(error_msg, "ERROR", job_id=job_id) # Log as Error, but still critical for this step
                  log(traceback.format_exc(), "DEBUG", job_id=job_id)
                  # This is a critical failure if results cannot be saved
                  raise RuntimeError(error_msg) from e

        else:
             # mode is not 'fast' or 'advanced'
             log(f"Unknown analysis mode '{mode}'. Skipping LLM analysis execution.", "WARNING", job_id=job_id)
             # analysis_input_text was None or config was invalid, log was already issued.
             # Return initial None/empty results
             return None, {}, None, None


        elapsed_analysis = round(time.time() - start_time_analysis, 2)
        log(f"LLM analysis step finished in {elapsed_analysis}s.", "SUCCESS", job_id=job_id)
        # Return collected results and paths
        return summary_result, advanced_results, summary_path_abs, advanced_analysis_path_abs

    except Exception as e: # Catch errors during the *overall* LLM analysis phase (after text prep and initial checks)
         # This catches errors from mode handling, result saving (if not caught internally), or aggregation if not caught internally
         raise RuntimeError(f"LLM analysis phase encountered an error: {e}") from e


# --- Helper Function: Finalize Job Results ---
def _finalize_job_results(
    job_id: str,
    # Inputs gathered from previous steps and initial preparation
    intermediate_transcript_path_abs: Optional[Path], # Absolute path
    final_transcript_path_abs: Optional[Path],       # Absolute path
    html_transcript_path_abs: Optional[Path],        # Absolute path
    summary_path_abs: Optional[Path],                # Absolute path
    advanced_analysis_path_abs: Optional[Path],      # Absolute path
    summary_result: Optional[str],                   # Direct summary content (fast mode)
    advanced_results: Dict[str, Optional[str]],      # Advanced results dictionary (advanced mode)
    final_segments: Optional[List[TranscriptSegment]], # Final segments list
    final_speaker_map: Dict[str, Optional[str]],      # Final speaker map used
    start_time_total: Optional[float]                # Job start time
    ) -> Dict[str, Any]:
    """
    Gathers all results and paths into the final result dictionary for JobManager/DB.
    Constructs relative paths where needed.
    """
    log(f"Step 6: Finalizing job results for {job_id}...", "INFO", job_id=job_id)

    # Convert absolute paths to relative paths for storage in JobManager/DB
    # Check if path exists before trying to make it relative, in case saving failed
    intermediate_transcript_path_rel = str(intermediate_transcript_path_abs.relative_to(PROJECT_ROOT)) if intermediate_transcript_path_abs and intermediate_transcript_path_abs.exists() else None
    final_transcript_json_path_rel = str(final_transcript_path_abs.relative_to(PROJECT_ROOT)) if final_transcript_path_abs and final_transcript_path_abs.exists() else None
    html_transcript_path_rel = str(html_transcript_path_abs.relative_to(PROJECT_ROOT)) if html_transcript_path_abs and html_transcript_path_abs.exists() else None
    summary_path_rel = str(summary_path_abs.relative_to(PROJECT_ROOT)) if summary_path_abs and summary_path_abs.exists() else None
    advanced_analysis_path_rel = str(advanced_analysis_path_abs.relative_to(PROJECT_ROOT)) if advanced_analysis_path_abs and advanced_analysis_path_abs.exists() else None


    # Prepare the final result dictionary
    final_result_data: Dict[str, Any] = {
        # Paths to saved files (relative to PROJECT_ROOT)
        # Using consistent keys for paths based on filename constants
        INTERMEDIATE_TRANSCRIPT_JSON_FILENAME.replace('.json', '_path'): intermediate_transcript_path_rel, # Path to raw transcript used for analysis text prep
        FINAL_TRANSCRIPT_JSON_FILENAME.replace('.json', '_path'): final_transcript_json_path_rel,
        FINAL_HTML_TRANSCRIPT_FILENAME.replace('.html', '_path'): html_transcript_path_rel,
        FINAL_SUMMARY_FILENAME.replace('.txt', '_path'): summary_path_rel,
        FINAL_ADVANCED_ANALYSIS_FILENAME.replace('.json', '_path'): advanced_analysis_path_rel,

        # Include direct LLM content results in the main job result dict
        # Keys here should ideally match DB column names or expected API response keys
        # Using LLM task constants as keys
        LLM_TASK_SUMMARY: summary_result if summary_result is not None else advanced_results.get(LLM_TASK_SUMMARY), # Prefer direct summary if fast mode, else advanced summary
        LLM_TASK_INTENT: advanced_results.get(LLM_TASK_INTENT),
        LLM_TASK_ACTIONS: advanced_results.get(LLM_TASK_ACTIONS),
        LLM_TASK_EMOTION: advanced_results.get(LLM_TASK_EMOTION),
        LLM_TASK_QUESTIONS: advanced_results.get(LLM_TASK_QUESTIONS),
        LLM_TASK_LEGAL: advanced_results.get(LLM_TASK_LEGAL),
        LLM_TASK_FINAL_ANALYSIS: advanced_results.get(LLM_TASK_FINAL_ANALYSIS), # Final aggregated analysis string


        # Include actual data used/produced for DB logging / potential future use
        # These fields include the actual Python data structures
        # NOTE: These fields can potentially cause TypeErrors if not serializable!
        "final_transcript_segments": final_segments, # Transcript with names (List[Dict]) - Should be serializable
        "speaker_mapping_used": final_speaker_map, # Map applied (Dict[str, Optional[str]]) - Should be serializable
     }

    elapsed_total = round(time.time() - start_time_total, 2) if start_time_total is not None else 'N/A'
    log(f"Job results finalized. Total processing time (approx): {elapsed_total}s.", "INFO", job_id=job_id)

    # Return the prepared result dictionary. This dict is what's set in JobManager.
    return final_result_data

# --- Helper Function: Clean Up Intermediate Files ---
def _cleanup_intermediate_files(job_id: str):
    """
    Cleans up specific intermediate files generated during Part 1 that are
    no longer needed after Part 2 completes.
    """
    log(f"Cleaning up intermediate files for job {job_id}...", "DEBUG", job_id=job_id)
    try:
        # Intermediate files saved in the transcripts directory
        # Use constants for filenames
        intermediate_map_abs = (TRANSCRIPTS_DIR / INTERMEDIATE_PROPOSED_MAP_FILENAME).resolve()
        intermediate_context_abs = (TRANSCRIPTS_DIR / INTERMEDIATE_CONTEXT_SNIPPETS_FILENAME).resolve()
        intermediate_transcript_abs = (TRANSCRIPTS_DIR / INTERMEDIATE_TRANSCRIPT_JSON_FILENAME).resolve() # Clean up intermediate transcript JSON too

        # Attempt to delete files, ignoring errors if they don't exist
        # Check if the file exists before trying to unlink
        if intermediate_map_abs.is_file():
            try: intermediate_map_abs.unlink()
            except Exception as e: log(f"Warning: Failed to unlink '{intermediate_map_abs.name}': {e}", "WARNING", job_id=job_id)

        if intermediate_context_abs.is_file():
            try: intermediate_context_abs.unlink()
            except Exception as e: log(f"Warning: Failed to unlink '{intermediate_context_abs.name}': {e}", "WARNING", job_id=job_id)

        if intermediate_transcript_abs.is_file():
            try: intermediate_transcript_abs.unlink()
            except Exception as e: log(f"Warning: Failed to unlink '{intermediate_transcript_abs.name}': {e}", "WARNING", job_id=job_id)


        log("Intermediate map, context, and transcript files cleanup attempt complete.", "DEBUG", job_id=job_id)
    except Exception as e:
         # Catch any other unexpected errors during the cleanup process itself
         log(f"Warning: Unexpected error during intermediate file cleanup for job {job_id}: {e}", "WARNING", job_id=job_id)
         log(traceback.format_exc(), "DEBUG", job_id=job_id)


# --- Main Pipeline Part 2 Function (Orchestrator) ---
def run_part2(
    job_id: str,
    final_speaker_map: Dict[str, Optional[str]],
    ):
    """
    Runs the second part of the pipeline after user speaker review.
    Orchestrates loading, mapping, formatting, LLM analysis, and logging.
    Updates job status and sets final result in JobManager.
    Ensures database logging and cleanup happen regardless of success/failure.
    """
    job_manager.add_log(job_id, "Pipeline Part 2 started.", "INFO")

    # Initialize variables to hold results from steps (used in finally block)
    job_config: Optional[Dict[str, Any]] = None
    start_time_total: Optional[float] = None
    intermediate_transcript_path_abs: Optional[Path] = None
    final_segments: Optional[List[TranscriptSegment]] = None
    final_transcript_path_abs: Optional[Path] = None
    html_transcript_path_abs: Optional[Path] = None
    summary_result: Optional[str] = None
    advanced_results: Dict[str, Optional[str]] = {} # Ensure it's a dict for final_result_data
    summary_path_abs: Optional[Path] = None
    advanced_analysis_path_abs: Optional[Path] = None


    try: # Main try block for the entire Part 2 process

        # --- Preparation Step ---
        # Handles retrieving job data, config, intermediate path, start time
        # Will raise exception on critical init failure
        # The caller of run_part2 (e.g., pipeline_routes) should handle exceptions from here
        job_config, intermediate_transcript_path_abs, start_time_total = _prepare_part2(job_id)
        # check_stop(job_id, "initialization") # Check after preparation


        # --- Step 1: Load Intermediate Segments ---
        intermediate_segments = _load_intermediate_segments(intermediate_transcript_path_abs, job_id)
        check_stop(job_id, "loading intermediate segments")


        # --- Step 2: Apply Final Speaker Mapping ---
        final_segments = _apply_speaker_mapping_step(intermediate_segments, final_speaker_map, job_id)
        check_stop(job_id, "applying speaker mapping")


        # --- Step 3: Save Final Transcript JSON ---
        # Returns absolute and relative paths to the saved file. Raises on failure.
        final_transcript_path_abs, final_transcript_path_rel = _save_final_transcript_json(final_segments, job_id)
        check_stop(job_id, "saving final transcript JSON")


        # --- Step 4: Generate and Save HTML Transcript ---
        # Returns absolute and relative paths, or None if failed (non-critical)
        html_transcript_path_abs, html_transcript_path_rel = _generate_and_save_html(final_segments, job_id)
        check_stop(job_id, "HTML reformatting")


        # --- Step 5: LLM Analysis ---
        # Prepare text input for LLM from the final JSON file
        analysis_input_text = _prepare_text_for_llm(final_transcript_path_abs, job_id)

        # Run LLM analysis if text was prepared successfully and config is valid
        # This helper returns summary/advanced results and paths to saved files.
        # It handles LLM config checks internally.
        # Will raise RuntimeError if critical LLM phase step fails (like saving advanced JSON).
        if analysis_input_text: # Only attempt LLM execution if text prep was successful
             summary_result, advanced_results, summary_path_abs, advanced_analysis_path_abs = _run_llm_analysis_step(
                 analysis_input_text, job_config, job_id
             )
             check_stop(job_id, "LLM analysis completion") # Check again after LLM step


        # --- Step 6: Finalize Job ---
        # Collects all results and paths into the final dictionary
        # Passes all relevant variables, even if some are None due to skipped/failed steps
        final_result_data = _finalize_job_results(
             job_id,
             intermediate_transcript_path_abs, # Pass intermediate path for DB log/reference
             final_transcript_path_abs,
             html_transcript_path_abs,
             summary_path_abs,
             advanced_analysis_path_abs,
             summary_result,
             advanced_results,
             final_segments,
             final_speaker_map,
             start_time_total
         )

        # Set final result in JobManager and mark as COMPLETED
        # THIS IS A POTENTIAL SOURCE OF THE TypeERROR if final_result_data contains non-serializable objects!
        # The TypeErrors caught in pipeline_routes.py often happen *after* this point when fetching status.
        job_manager.set_result(job_id, final_result_data)
        log(f"Pipeline completed successfully for job {job_id}.", "SUCCESS", job_id=job_id)


    # --- Exception Handling for Part 2 ---
    # Specific error types are caught first, then a general Exception catch-all
    except InterruptedError as e:
        error_msg = f"Pipeline Part 2 stopped by user request."
        job_manager.update_status(job_id, STATUS_STOPPED)
        log(f"Job {job_id} operation stopped cleanly via request during Part 2: {e}", "INFO")
    except (RuntimeError, ValueError, FileNotFoundError) as e: # Catch specific expected errors
        # These exceptions are raised by our helper functions on known failures
        error_msg = f"Pipeline Part 2 failed: {e}"
        log(error_msg, "ERROR", job_id=job_id)
        log(traceback.format_exc(), "DEBUG", job_id=job_id)
        # Use the dedicated function to set error status
        job_manager.set_error(job_id, error_msg)
    except Exception as e: # Catch any other unexpected critical errors
        # This indicates a bug in the code or environment setup
        error_msg = f"Unexpected critical error in the pipeline. Please check the logs for more details."