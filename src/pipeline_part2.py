# src/pipeline_part2.py
# Begin van src/pipeline_part2.py

import time
import os
import json
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional, TypedDict, Tuple # Tuple was al correct hier

# Import application components
from src.job_manager import job_manager
# Importeer ALLE benodigde constanten
from src.constants import (
    STATUS_MAPPING_SPEAKERS, STATUS_REFORMATTING, STATUS_ANALYZING,
    STATUS_COMPLETED, STATUS_FAILED, STATUS_STOPPED, STATUS_UNKNOWN, # Statuses
    RESULTS_FOLDER_NAME, TRANSCRIPTS_FOLDER_NAME, AUDIO_FOLDER_NAME, # Folder names
    INTERMEDIATE_PROPOSED_MAP_FILENAME, INTERMEDIATE_CONTEXT_SNIPPETS_FILENAME,
    INTERMEDIATE_TRANSCRIPT_JSON_FILENAME,
    FINAL_TRANSCRIPT_JSON_FILENAME, FINAL_HTML_TRANSCRIPT_FILENAME,
    FINAL_SUMMARY_FILENAME, FINAL_ADVANCED_ANALYSIS_FILENAME, # Final File names
    PROGRESS_AFTER_MAPPING, PROGRESS_AFTER_REFORMAT, PROGRESS_AFTER_ANALYSIS,
    PROGRESS_COMPLETE, # PROGRESS_WAITING_REVIEW (niet direct gebruikt in part2, maar voor context)
    LLM_TASK_SUMMARY, LLM_ADVANCED_TASK_KEYS, LLM_TASK_FINAL_ANALYSIS,
    LLM_TASK_INTENT, LLM_TASK_ACTIONS, LLM_TASK_EMOTION, LLM_TASK_QUESTIONS, LLM_TASK_LEGAL
)

# Import core processing functions
from src.speaker_mapping import apply_speaker_mapping
from src.transcript_reformatter import format_transcript_html

# Import LLM functions/modules
# from src.utils.llm import run_with_fallback # run_with_fallback wordt niet direct gebruikt in de refactored versie
from src.analysis_tasks import advanced_tasks

# Import helpers and utilities
from src.utils.pipeline_helpers import check_stop
from src.utils.config_schema import PROJECT_ROOT
from src.database_logger import log_job_to_db, get_db_path # get_db_path is niet gebruikt, maar kan blijven
from src.utils.log import log

# Log module load
log("Loaded src/pipeline_part2.py", "DEBUG")

# --- Define Folder Paths using constants ---
RESULTS_DIR = PROJECT_ROOT / RESULTS_FOLDER_NAME
TRANSCRIPTS_DIR = PROJECT_ROOT / TRANSCRIPTS_FOLDER_NAME
# AUDIO_DIR = PROJECT_ROOT / AUDIO_FOLDER_NAME # AUDIO_DIR is hier niet direct nodig

# --- Type Hint for Segment Structure ---
class TranscriptSegment(TypedDict, total=False):
    start: float
    end: float
    text: str
    speaker: str
    words: List[Dict[str, Any]]
    speaker_name: str # Toegevoegd door speaker_mapping

# --- Helper Function: Prepare Initial Job Data ---
def _prepare_part2(job_id: str) -> Tuple[Dict[str, Any], Path, Optional[float]]:
    """
    Retrieves essential job data and validates paths before starting Part 2 processing.
    """
    log(f"Preparing for Part 2 for job {job_id}...", "DEBUG", job_id=job_id)
    job_data = job_manager.get_status(job_id)
    if not job_data:
         raise ValueError(f"Job {job_id} not found in JobManager. Aborting Part 2 initialization.")

    job_config = job_data.get("config")
    if not isinstance(job_config, dict):
        raise ValueError(f"Job config missing or invalid for job {job_id}.")

    review_paths = job_data.get("review_data_paths", {})
    intermediate_transcript_rel_path_str = review_paths.get("intermediate_transcript_path")
    if not intermediate_transcript_rel_path_str:
        raise ValueError(f"Intermediate transcript path missing in job data for job {job_id}.")

    intermediate_transcript_path_abs = (PROJECT_ROOT / Path(intermediate_transcript_rel_path_str)).resolve()
    if not intermediate_transcript_path_abs.is_file():
         raise FileNotFoundError(f"Intermediate transcript file not found at: {intermediate_transcript_path_abs} for job {job_id}")

    start_time_total = job_data.get("start_time") # Dit is de starttijd van de *hele* job (Part 1)
    if start_time_total is None:
         log(f"Warning: Job start time not found in job data for {job_id}.", "WARNING", job_id=job_id)

    log(f"Initialization for Part 2 complete for job {job_id}. Intermediate transcript: {intermediate_transcript_path_abs.name}", "DEBUG", job_id=job_id)
    return job_config, intermediate_transcript_path_abs, start_time_total

# --- Helper Function: Load Intermediate Segments ---
def _load_intermediate_segments(intermediate_transcript_path_abs: Path, job_id: str) -> List[TranscriptSegment]:
    """
    Loads transcript segments from the intermediate JSON file.
    """
    log(f"Step 1: Loading intermediate segments from {intermediate_transcript_path_abs.name} for job {job_id}", "INFO", job_id=job_id)
    try:
        with open(intermediate_transcript_path_abs, "r", encoding='utf-8') as f:
            segments_to_process = json.load(f)
        if not isinstance(segments_to_process, list):
             raise ValueError(f"Loaded intermediate transcript data is not a list for job {job_id}.")
        log(f"Loaded {len(segments_to_process)} intermediate segments for job {job_id}.", "DEBUG", job_id=job_id)
        return segments_to_process
    except FileNotFoundError:
        raise FileNotFoundError(f"Intermediate transcript file not found: {intermediate_transcript_path_abs} for job {job_id}")
    except json.JSONDecodeError as e:
         raise RuntimeError(f"Failed to decode JSON from intermediate transcript file '{intermediate_transcript_path_abs.name}' for job {job_id}: {e}") from e
    except Exception as e:
         raise RuntimeError(f"Error loading intermediate transcript from '{intermediate_transcript_path_abs.name}' for job {job_id}: {e}") from e

# --- Helper Function: Apply Final Speaker Mapping ---
def _apply_speaker_mapping_step(segments_to_process: List[TranscriptSegment], final_speaker_map: Dict[str, Optional[str]], job_id: str) -> List[TranscriptSegment]:
    """
    Applies the final speaker names based on the user-provided map.
    """
    job_manager.update_status(job_id, STATUS_MAPPING_SPEAKERS) # STATUS UPDATE
    log(f"Step 2: Applying final speaker map for job {job_id}...", "INFO", job_id=job_id)

    if not isinstance(final_speaker_map, dict):
         raise ValueError(f"Invalid final speaker map provided for job {job_id}. Expected dictionary.")

    final_segments = apply_speaker_mapping(segments_to_process, final_speaker_map)
    if final_segments is None: # apply_speaker_mapping zou geen None moeten returnen
         raise RuntimeError(f"Applying final speaker mapping failed unexpectedly for job {job_id}.")

    log(f"Final speaker name assignment complete. Processed {len(final_segments)} segments for job {job_id}.", "SUCCESS", job_id=job_id)
    job_manager.update_progress(job_id, PROGRESS_AFTER_MAPPING)
    check_stop(job_id, "applying speaker mapping")
    return final_segments

# --- Helper Function: Save Final Transcript JSON ---
def _save_final_transcript_json(final_segments: List[TranscriptSegment], job_id: str) -> Tuple[Path, Path]:
    """
    Saves the final transcript segments (with speaker names) to a JSON file.
    """
    final_transcript_path_abs = (TRANSCRIPTS_DIR / FINAL_TRANSCRIPT_JSON_FILENAME).resolve()
    final_transcript_path_rel = final_transcript_path_abs.relative_to(PROJECT_ROOT)

    log(f"Step 3: Saving final transcript JSON to {final_transcript_path_rel} for job {job_id}...", "INFO", job_id=job_id)
    try:
        final_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        with open(final_transcript_path_abs, "w", encoding='utf-8') as f:
             json.dump(final_segments, f, indent=2, ensure_ascii=False)
        log(f"Final transcript JSON saved: {final_transcript_path_rel} for job {job_id}", "INFO", job_id=job_id)
        return final_transcript_path_abs, final_transcript_path_rel
    except TypeError as e:
         error_msg = f"Failed to serialize final transcript data to '{final_transcript_path_abs.name}' for job {job_id}: {e}. Data structure issue detected."
         log(error_msg, "CRITICAL", job_id=job_id)
         log(traceback.format_exc(), "DEBUG", job_id=job_id)
         raise RuntimeError(error_msg) from e
    except Exception as e:
         error_msg = f"Failed to save final transcript JSON to '{final_transcript_path_abs.name}' for job {job_id}: {e}"
         log(error_msg, "CRITICAL", job_id=job_id)
         log(traceback.format_exc(), "DEBUG", job_id=job_id)
         raise RuntimeError(error_msg) from e

# --- Helper Function: Generate and Save HTML Transcript ---
def _generate_and_save_html(final_segments: List[TranscriptSegment], job_id: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Generates HTML transcript and saves it. Returns paths or None if failed.
    """
    job_manager.update_status(job_id, STATUS_REFORMATTING) # STATUS UPDATE
    log(f"Step 4: Generating HTML transcript for job {job_id}...", "INFO", job_id=job_id)

    html_transcript_path_abs = (RESULTS_DIR / FINAL_HTML_TRANSCRIPT_FILENAME).resolve()
    html_transcript_path_rel = html_transcript_path_abs.relative_to(PROJECT_ROOT)

    try:
        html_output_string = format_transcript_html(final_segments)
        if html_output_string:
             html_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
             with open(html_transcript_path_abs, "w", encoding='utf-8') as f: f.write(html_output_string)
             log(f"HTML transcript saved: {html_transcript_path_rel} for job {job_id}", "SUCCESS", job_id=job_id)
             job_manager.update_progress(job_id, PROGRESS_AFTER_REFORMAT) # Progress na succesvolle reformat
             return html_transcript_path_abs, html_transcript_path_rel
        else:
             log(f"HTML generation returned empty string for job {job_id}. Skipping save.", "WARNING", job_id=job_id)
             return None, None
    except Exception as e:
        log(f"Warning: HTML transcript generation/saving failed for job {job_id}: {e}", "WARNING", job_id=job_id)
        log(traceback.format_exc(), "DEBUG", job_id=job_id)
        return None, None

# --- Helper Function: Prepare Text for LLM Analysis ---
def _prepare_text_for_llm(final_transcript_json_path_abs: Optional[Path], job_id: str) -> Optional[str]:
    """
    Loads the final transcript JSON and formats the text for LLM analysis.
    """
    if not final_transcript_json_path_abs or not final_transcript_json_path_abs.is_file():
        log(
            f"Final transcript JSON file not found at {final_transcript_json_path_abs} for job {job_id}. Cannot prepare text for LLM.",
            "ERROR",
            job_id=job_id,
        )
        return None
    try:
        log(f"Loading text from {final_transcript_json_path_abs.name} for LLM analysis (job {job_id})...", "DEBUG", job_id=job_id)
        with open(final_transcript_json_path_abs, "r", encoding='utf-8') as f:
            loaded_final_segments_for_text = json.load(f)
        if not isinstance(loaded_final_segments_for_text, list):
             raise ValueError(f"Invalid format in final transcript JSON (expected list) for job {job_id}.")
        text_lines = [
            f"{segment.get('speaker_name', 'Unknown')}: {segment.get('text', '').strip()}"
            for segment in loaded_final_segments_for_text if isinstance(segment, dict) and segment.get('text') is not None
        ]
        analysis_input_text = "\n".join(text_lines).strip()
        if not analysis_input_text:
            log(
                f"No text content found in final transcript JSON for job {job_id}. Skipping LLM analysis.",
                "WARNING",
                job_id=job_id,
            )
            return None
        log(f"Prepared text input for LLM analysis ({len(analysis_input_text)} chars) for job {job_id}.", "DEBUG", job_id=job_id)
        return analysis_input_text
    except Exception as e:
        log(
            f"Unexpected error loading/preparing text from final transcript '{final_transcript_json_path_abs.name}' for job {job_id}: {e}. Skipping LLM.",
            "ERROR",
            job_id=job_id,
        )
        log(traceback.format_exc(), "DEBUG", job_id=job_id)
        return None

# --- Helper Function: Run LLM Analysis Steps ---
def _run_llm_analysis_step(
    analysis_input_text: Optional[str],
    job_config: Dict[str, Any],
    job_id: str
    ) -> Tuple[Optional[str], Dict[str, Optional[str]], Optional[Path], Optional[Path]]:
    """
    Orchestrates LLM analysis based on mode.
    """
    job_manager.update_status(job_id, STATUS_ANALYZING) # STATUS UPDATE
    mode = job_config.get("mode", "fast")
    log(f"Step 5: Starting LLM analysis (Mode: {mode}) for job {job_id}...", "INFO", job_id=job_id)
    start_time_analysis = time.time()

    summary_result: Optional[str] = None
    advanced_results: Dict[str, Optional[str]] = {}
    summary_path_abs: Optional[Path] = None
    advanced_analysis_path_abs: Optional[Path] = None

    if not analysis_input_text:
         log(f"LLM analysis skipped for job {job_id} because transcript text was not prepared or was empty.", "WARNING", job_id=job_id)
         return None, {}, None, None
    llm_models_config = job_config.get("llm_models")
    if not isinstance(llm_models_config, dict) or not llm_models_config:
        log(f"LLM analysis requires 'llm_models' config. Skipping LLM for job {job_id}.", "WARNING", job_id=job_id)
        return None, {}, None, None

    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        summary_path_abs = (RESULTS_DIR / FINAL_SUMMARY_FILENAME).resolve()
        advanced_analysis_path_abs = (RESULTS_DIR / FINAL_ADVANCED_ANALYSIS_FILENAME).resolve()
        extra_context = job_config.get("extra_context_prompt", "")

        if mode == "fast":
             log(f"Running LLM 'fast' mode ({LLM_TASK_SUMMARY}) for job {job_id}...", "INFO", job_id=job_id)
             summary_result = advanced_tasks.summary(analysis_input_text, job_config, extra_context)
             if summary_result is not None:
                 try:
                      with open(summary_path_abs, "w", encoding='utf-8') as f: f.write(summary_result)
                      log(f"Summary saved: {summary_path_abs.relative_to(PROJECT_ROOT)} for job {job_id}", "SUCCESS", job_id=job_id)
                 except IOError as e_save_sum:
                     log(f"Failed to save summary file '{summary_path_abs.name}' for job {job_id}: {e_save_sum}", "ERROR", job_id=job_id)
                     summary_path_abs = None # Mark as not saved
             else:
                 log(f"Summary generation returned None for job {job_id}.", "WARNING", job_id=job_id)
        elif mode == "advanced":
             log(f"Running LLM 'advanced' mode for job {job_id}...", "INFO", job_id=job_id)
             temp_intermediate_results: Dict[str, Optional[str]] = {}
             task_functions = {
                 LLM_TASK_SUMMARY: advanced_tasks.summary, LLM_TASK_INTENT: advanced_tasks.intent,
                 LLM_TASK_ACTIONS: advanced_tasks.actions, LLM_TASK_EMOTION: advanced_tasks.emotion,
                 LLM_TASK_QUESTIONS: advanced_tasks.questions, LLM_TASK_LEGAL: advanced_tasks.legal,
             }
             tasks_to_run_keys = LLM_ADVANCED_TASK_KEYS
             total_tasks = len(tasks_to_run_keys) + 1 # +1 for final aggregation
             completed_tasks = 0

             for task_name in tasks_to_run_keys:
                  check_stop(job_id, f"advanced LLM task '{task_name}'")
                  job_manager.add_log(job_id, f"Running LLM task: {task_name} for job {job_id}...", "INFO")
                  task_func = task_functions.get(task_name)
                  if not task_func:
                      log(f"Warning: No function for LLM task key '{task_name}'. Skipping for job {job_id}.", "WARNING", job_id=job_id)
                      temp_intermediate_results[task_name] = f"Error: Task function missing for '{task_name}'"
                      continue
                  try:
                      task_result = task_func(analysis_input_text, job_config, extra_context)
                      temp_intermediate_results[task_name] = task_result
                      log(f"LLM task '{task_name}' finished for job {job_id}.", "SUCCESS" if task_result is not None else "WARNING", job_id=job_id)
                  except Exception as task_e:
                      log(f"Error during LLM task '{task_name}' for job {job_id}: {task_e}", "ERROR", job_id=job_id)
                      temp_intermediate_results[task_name] = f"Error: {task_e}"
                  finally:
                      completed_tasks += 1
                      current_progress = PROGRESS_AFTER_REFORMAT + int((completed_tasks / total_tasks) * (PROGRESS_AFTER_ANALYSIS - PROGRESS_AFTER_REFORMAT))
                      job_manager.update_progress(job_id, current_progress)
             check_stop(job_id, "final LLM analysis aggregation")
             job_manager.add_log(job_id, "Running final aggregating LLM analysis for job {job_id}...", "INFO")
             try:
                 final_agg_result = advanced_tasks.run_final_analysis(temp_intermediate_results, job_config, extra_context)
                 advanced_results = temp_intermediate_results.copy()
                 advanced_results[LLM_TASK_FINAL_ANALYSIS] = final_agg_result
                 log(f"Final aggregating analysis completed for job {job_id}.", "SUCCESS", job_id=job_id)
             except Exception as final_agg_e:
                 log(f"Error during final aggregating analysis task for job {job_id}: {final_agg_e}", "ERROR", job_id=job_id)
                 advanced_results = temp_intermediate_results.copy()
                 advanced_results[LLM_TASK_FINAL_ANALYSIS] = f"Error during final aggregation: {final_agg_e}"
             try:
                  with open(advanced_analysis_path_abs, "w", encoding='utf-8') as f:
                      json.dump(advanced_results, f, indent=2, ensure_ascii=False)
                  log(f"Advanced analysis results saved: {advanced_analysis_path_abs.relative_to(PROJECT_ROOT)} for job {job_id}", "SUCCESS", job_id=job_id)
             except TypeError as e_type_adv:
                 error_msg_adv = f"Failed to serialize advanced analysis results for job {job_id}: {e_type_adv}."
                 log(error_msg_adv, "CRITICAL", job_id=job_id)
                 raise RuntimeError(error_msg_adv) from e_type_adv
             except Exception as e_save_adv:
                  error_msg_adv_save = f"Failed to save advanced analysis JSON for job {job_id}: {e_save_adv}"
                  log(error_msg_adv_save, "ERROR", job_id=job_id)
                  raise RuntimeError(error_msg_adv_save) from e_save_adv
        else:
             log(f"Unknown analysis mode '{mode}' for job {job_id}. Skipping LLM analysis.", "WARNING", job_id=job_id)
             return None, {}, None, None # Return empty/None for non-matching mode

        elapsed_analysis = round(time.time() - start_time_analysis, 2)
        log(f"LLM analysis step finished in {elapsed_analysis}s for job {job_id}.", "SUCCESS", job_id=job_id)
        job_manager.update_progress(job_id, PROGRESS_AFTER_ANALYSIS) # Progress after all LLM analysis
        return summary_result, advanced_results, summary_path_abs, advanced_analysis_path_abs
    except Exception as e: # Catch errors during the overall LLM analysis phase
         # This includes directory creation or unhandled issues in mode logic
         raise RuntimeError(f"LLM analysis phase for job {job_id} encountered an error: {e}") from e


# --- New: Run only the LLM analysis using existing or provided final transcript ---
def run_analysis_only(job_id: str, transcript_override_rel: Optional[Path] = None) -> None:
    """Re-runs only the analysis step for a completed job.

    If `transcript_override_rel` is provided (relative to PROJECT_ROOT), it is used
    as the source for final_transcript.json (and will overwrite the default file).
    Otherwise, uses transcripts/final_transcript.json already on disk.
    """
    try:
        job_config, _, _ = _prepare_part2(job_id)  # gets config and validates intermediate path, but we won't use it further here
    except Exception as e:
        log(f"run_analysis_only: Could not prepare Part 2 for job {job_id}: {e}", "ERROR", job_id=job_id)
        raise

    final_transcript_path_abs = (PROJECT_ROOT / TRANSCRIPTS_FOLDER_NAME / FINAL_TRANSCRIPT_JSON_FILENAME).resolve()
    if transcript_override_rel:
        try:
            # Write override JSON into final_transcript.json
            override_abs = (PROJECT_ROOT / transcript_override_rel).resolve()
            with open(override_abs, "r", encoding='utf-8') as f:
                override_data = json.load(f)
            final_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
            with open(final_transcript_path_abs, "w", encoding='utf-8') as f:
                json.dump(override_data, f, ensure_ascii=False, indent=2)
            log(f"run_analysis_only: Overwrote final_transcript.json from {override_abs.name} for job {job_id}", "INFO", job_id=job_id)
        except Exception as e:
            log(f"run_analysis_only: Failed to apply transcript override for job {job_id}: {e}", "ERROR", job_id=job_id)
            raise

    analysis_text = _prepare_text_for_llm(final_transcript_path_abs, job_id)
    if not analysis_text:
        raise RuntimeError(f"run_analysis_only: No analysis text available for job {job_id}")

    summary_result, advanced_results, summary_path_abs, advanced_json_path_abs = _run_llm_analysis_step(
        analysis_text, job_config, job_id
    )

    # Finalize job state
    try:
        job_manager.update_progress(job_id, PROGRESS_AFTER_ANALYSIS)
        job_manager.set_result(job_id, {
            "summary_path": str(summary_path_abs.relative_to(PROJECT_ROOT)) if summary_path_abs else None,
            "advanced_analysis_path": str(advanced_json_path_abs.relative_to(PROJECT_ROOT)) if advanced_json_path_abs else None,
        })
        job_manager.update_status(job_id, STATUS_COMPLETED)
        log(f"run_analysis_only: Completed re-analysis for job {job_id}.", "SUCCESS", job_id=job_id)
    except Exception as e:
        log(f"run_analysis_only: Failed to finalize job {job_id}: {e}", "ERROR", job_id=job_id)
        raise

# --- Helper Function: Finalize Job Results ---
def _finalize_job_results(
    job_id: str, intermediate_transcript_path_abs: Optional[Path],
    final_transcript_path_abs: Optional[Path], html_transcript_path_abs: Optional[Path],
    summary_path_abs: Optional[Path], advanced_analysis_path_abs: Optional[Path],
    summary_result: Optional[str], advanced_results: Dict[str, Optional[str]],
    final_segments: Optional[List[TranscriptSegment]], final_speaker_map: Dict[str, Optional[str]],
    start_time_total: Optional[float]
    ) -> Dict[str, Any]:
    """
    Gathers all results and paths into the final result dictionary.
    """
    log(f"Step 6: Finalizing job results for {job_id}...", "INFO", job_id=job_id)
    final_result_data: Dict[str, Any] = {
        # Relative Paths
        key.replace('.json', '_path').replace('.html', '_path').replace('.txt', '_path'):
            str(p.relative_to(PROJECT_ROOT)) if p and p.exists() else None
        for key, p in [
            (INTERMEDIATE_TRANSCRIPT_JSON_FILENAME, intermediate_transcript_path_abs),
            (FINAL_TRANSCRIPT_JSON_FILENAME, final_transcript_path_abs),
            (FINAL_HTML_TRANSCRIPT_FILENAME, html_transcript_path_abs),
            (FINAL_SUMMARY_FILENAME, summary_path_abs),
            (FINAL_ADVANCED_ANALYSIS_FILENAME, advanced_analysis_path_abs),
        ]
    }
    # LLM Content Results
    final_result_data.update({
        LLM_TASK_SUMMARY: summary_result if summary_result is not None else advanced_results.get(LLM_TASK_SUMMARY),
        LLM_TASK_INTENT: advanced_results.get(LLM_TASK_INTENT),
        LLM_TASK_ACTIONS: advanced_results.get(LLM_TASK_ACTIONS),
        LLM_TASK_EMOTION: advanced_results.get(LLM_TASK_EMOTION),
        LLM_TASK_QUESTIONS: advanced_results.get(LLM_TASK_QUESTIONS),
        LLM_TASK_LEGAL: advanced_results.get(LLM_TASK_LEGAL),
        LLM_TASK_FINAL_ANALYSIS: advanced_results.get(LLM_TASK_FINAL_ANALYSIS),
    })
    # Actual Data Structures (ensure they are serializable if set directly in job_manager)
    final_result_data["final_transcript_segments_data"] = final_segments # Key changed for clarity
    final_result_data["speaker_mapping_used_data"] = final_speaker_map     # Key changed for clarity

    elapsed_total_str = f"{round(time.time() - start_time_total, 2)}s" if start_time_total is not None else 'N/A'
    log(f"Job results finalized for {job_id}. Total processing time (approx): {elapsed_total_str}.", "INFO", job_id=job_id)
    return final_result_data

# --- Helper Function: Clean Up Intermediate Files ---
def _cleanup_intermediate_files(job_id: str):
    """
    Cleans up specific intermediate files generated during Part 1.
    """
    log(f"Cleaning up intermediate files for job {job_id}...", "DEBUG", job_id=job_id)
    files_to_clean = [
        TRANSCRIPTS_DIR / INTERMEDIATE_PROPOSED_MAP_FILENAME,
        TRANSCRIPTS_DIR / INTERMEDIATE_CONTEXT_SNIPPETS_FILENAME,
        TRANSCRIPTS_DIR / INTERMEDIATE_TRANSCRIPT_JSON_FILENAME, # Also clean up the intermediate transcript now
    ]
    for file_path_abs in files_to_clean:
        resolved_path = file_path_abs.resolve() # Resolve before checking existence
        if resolved_path.is_file():
            try:
                resolved_path.unlink()
                log(f"Removed intermediate file: {resolved_path.name} for job {job_id}", "DEBUG", job_id=job_id)
            except Exception as e_unlink:
                log(f"Warning: Failed to unlink '{resolved_path.name}' for job {job_id}: {e_unlink}", "WARNING", job_id=job_id)
        else:
            log(f"Intermediate file not found for cleanup (expected): {resolved_path.name} for job {job_id}", "DEBUG", job_id=job_id)


# --- Main Pipeline Part 2 Function (Orchestrator) ---
def run_part2(
    job_id: str,
    final_speaker_map: Dict[str, Optional[str]], # This is the map from the user review
    ):
    """
    Runs the second part of the pipeline after user speaker review.
    """
    # ALLEREERSTE LOG IN DEZE FUNCTIE (toegevoegd voor debugging)
    log(f"PIPELINE_PART2_ENTRYPOINT: run_part2 CALLED for job_id: {job_id}. Received final_speaker_map: {final_speaker_map}", "CRITICAL", job_id=job_id)
    try:
        initial_status_at_part2_call = job_manager.get_status(job_id).get('status')
        log(f"PIPELINE_PART2_ENTRYPOINT: Initial status for job {job_id} at the moment run_part2 is called: '{initial_status_at_part2_call}'", "WARNING", job_id=job_id)
    except Exception as e_status_fetch:
        log(f"PIPELINE_PART2_ENTRYPOINT: Could not fetch initial status for job {job_id}: {e_status_fetch}", "ERROR", job_id=job_id)

    job_manager.add_log(job_id, "Pipeline Part 2 processing started.", "INFO")

    job_config: Optional[Dict[str, Any]] = None
    start_time_total: Optional[float] = None # Start time of the entire job (from Part 1)
    intermediate_transcript_path_abs: Optional[Path] = None
    final_segments: Optional[List[TranscriptSegment]] = None
    final_transcript_path_abs: Optional[Path] = None # Path to final transcript JSON
    html_transcript_path_abs: Optional[Path] = None  # Path to HTML transcript
    summary_result: Optional[str] = None
    advanced_results: Dict[str, Optional[str]] = {}
    summary_path_abs: Optional[Path] = None          # Path to summary text file
    advanced_analysis_path_abs: Optional[Path] = None # Path to advanced analysis JSON

    try:
        job_config, intermediate_transcript_path_abs, start_time_total = _prepare_part2(job_id)
        # check_stop(job_id, "initialization") # Optioneel hier

        intermediate_segments = _load_intermediate_segments(intermediate_transcript_path_abs, job_id)
        check_stop(job_id, "loading intermediate segments")

        final_segments = _apply_speaker_mapping_step(intermediate_segments, final_speaker_map, job_id)
        # status is now MAPPING_SPEAKERS
        check_stop(job_id, "applying speaker mapping")

        final_transcript_path_abs, _ = _save_final_transcript_json(final_segments, job_id)
        check_stop(job_id, "saving final transcript JSON")

        html_transcript_path_abs, _ = _generate_and_save_html(final_segments, job_id)
        # status is now REFORMATTING (als HTML generatie start)
        check_stop(job_id, "HTML reformatting")

        analysis_input_text = _prepare_text_for_llm(final_transcript_path_abs, job_id)
        if analysis_input_text and job_config: # Zorg dat job_config ook bestaat
             summary_result, advanced_results, summary_path_abs, advanced_analysis_path_abs = _run_llm_analysis_step(
                 analysis_input_text, job_config, job_id
             )
             # status is now ANALYZING (als LLM analyse start)
             check_stop(job_id, "LLM analysis completion")
        else:
             log(f"Skipping LLM analysis for job {job_id} due to missing text or config.", "INFO", job_id=job_id)


        final_result_data = _finalize_job_results(
             job_id, intermediate_transcript_path_abs,
             final_transcript_path_abs, html_transcript_path_abs,
             summary_path_abs, advanced_analysis_path_abs,
             summary_result, advanced_results,
             final_segments, final_speaker_map, start_time_total
         )
        job_manager.set_result(job_id, final_result_data) # Dit zet status naar COMPLETED en progress 100
        log(f"Pipeline Part 2 completed successfully for job {job_id}.", "SUCCESS", job_id=job_id)

    except InterruptedError as e_interrupt: # Specifiek voor user stop
        log(f"Pipeline Part 2 for job {job_id} stopped by user request: {e_interrupt}", "INFO", job_id=job_id)
        job_manager.update_status(job_id, STATUS_STOPPED) # Zet status expliciet
        # Geen error message nodig voor normale stop
    except (RuntimeError, ValueError, FileNotFoundError) as e_pipeline:
        error_msg = f"Pipeline Part 2 failed for job {job_id}: {e_pipeline}"
        log(error_msg, "ERROR", job_id=job_id)
        log(traceback.format_exc(), "DEBUG", job_id=job_id)
        job_manager.set_error(job_id, error_msg) # set_error zet status op FAILED
    except Exception as e_unexpected:
        error_msg = f"Unexpected critical error in Pipeline Part 2 for job {job_id}: {e_unexpected.__class__.__name__} - {e_unexpected}"
        log(error_msg, "CRITICAL", job_id=job_id)
        log(traceback.format_exc(), "ERROR", job_id=job_id)
        job_manager.set_error(job_id, "An unexpected critical error occurred in the pipeline.") # Algemene melding
    finally:
        # Database logging gebeurt ongeacht succes of falen van de try block
        # Deze moet na set_result of set_error komen zodat de finale status wordt gelogd.
        try:
            if job_config and 'database_logging_enabled' in job_config and job_config['database_logging_enabled']:
                final_job_status_for_db = job_manager.get_status(job_id) # Haal de allerlaatste status op
                if final_job_status_for_db: # Alleen loggen als de job nog bestaat
                    log_job_to_db(final_job_status_for_db) # Gebruik de volledige job data
                else:
                    log(f"Could not log job {job_id} to DB: job data not found in JobManager (possibly already cleaned up).", "WARNING", job_id=job_id)

            # Cleanup intermediate files (map, context, and intermediate transcript)
            # Doe dit alleen als de job NIET FAILED is, zodat debug info behouden blijft bij een error.
            # Of maak het configureerbaar. Voor nu, ruim altijd op als de status niet FAILED is.
            current_final_status = job_manager.get_status(job_id).get("status") if job_manager.get_status(job_id) else None
            if current_final_status and current_final_status != STATUS_FAILED:
                _cleanup_intermediate_files(job_id)
            else:
                log(f"Skipping intermediate file cleanup for job {job_id} due to FAILED status or job not found.", "INFO", job_id=job_id)

        except Exception as e_finally:
            log(f"Error during finally block (DB logging/cleanup) for job {job_id}: {e_finally}", "ERROR", job_id=job_id)
            log(traceback.format_exc(), "DEBUG", job_id=job_id)

        log(f"--- Exiting run_part2 function (finally block) for Job ID: {job_id} ---", "DEBUG", job_id=job_id)

# --- End of pipeline_part2.py ---
