# src/pipeline_part2.py
import time
import os
import json
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import application components
from src.job_manager import job_manager, STATUS_MAPPING_SPEAKERS, \
    STATUS_REFORMATTING, STATUS_ANALYZING, STATUS_COMPLETED, \
    STATUS_FAILED, STATUS_STOPPED # Import needed statuses
# Import core processing functions
from src.speaker_mapping import apply_speaker_mapping
from src.transcript_reformatter import format_transcript_html
# Import LLM functions/modules (these now expect text input)
from src.utils.llm import summarize_transcript
from src.analysis_tasks import advanced_tasks
# Import helpers and utilities
from src.utils.pipeline_helpers import check_stop
from src.utils.config_schema import PROJECT_ROOT
from src.database_logger import log_job_to_db, get_db_path
from src.utils.log import log

# --- Constants ---
RESULTS_DIR_NAME = "results"
TRANSCRIPTS_DIR_NAME = "transcripts"
RESULTS_DIR = PROJECT_ROOT / RESULTS_DIR_NAME
TRANSCRIPTS_DIR = PROJECT_ROOT / TRANSCRIPTS_DIR_NAME
DEFAULT_FINAL_JSON_FILENAME = "final_transcript.json"
DEFAULT_HTML_TRANSCRIPT_FILENAME = "transcript.html"
DEFAULT_SUMMARY_FILENAME = "summary.txt"
DEFAULT_ADVANCED_ANALYSIS_FILENAME = "advanced_analysis.json"

# Progress constants
PROGRESS_AFTER_MAPPING = 50
PROGRESS_AFTER_REFORMAT = 55
PROGRESS_AFTER_ANALYSIS = 95
PROGRESS_COMPLETE = 100


# --- Pipeline Part 2 Function ---
def run_part2(
    job_id: str,
    final_speaker_map: Dict[str, Optional[str]],
    ):
    """
    Runs the second part of the pipeline after user speaker review.
    Loads intermediate data, applies mapping, formats outputs, runs LLM analysis
    on the final transcript text, and logs results.

    Args:
        job_id: The unique ID for this job run.
        final_speaker_map: The speaker map confirmed/edited by the user.
    """
    # Initialize variables
    job_config: Optional[Dict[str, Any]] = None
    final_segments: Optional[List[Dict[str, Any]]] = None
    intermediate_transcript_path: Optional[Path] = None
    start_time_total: Optional[float] = None
    final_transcript_path: Optional[Path] = None
    html_transcript_path: Optional[Path] = None
    summary_path: Optional[Path] = None
    advanced_analysis_path: Optional[Path] = None
    summary_result: Optional[str] = None
    advanced_results: Optional[Dict[str, Any]] = None


    # --- Retrieve Job Info and Prepare ---
    try:
        job_data = job_manager.get_status(job_id)
        if not job_data: raise ValueError(f"Job {job_id} not found in JobManager.")
        job_config = job_data.get("config")
        if not isinstance(job_config, dict): raise ValueError(f"Job config missing or invalid for job {job_id}.")
        review_paths = job_data.get("review_data_paths", {})
        intermediate_transcript_rel_path_str = review_paths.get("intermediate_transcript_path")
        if not intermediate_transcript_rel_path_str: raise ValueError("Intermediate transcript path missing.")
        intermediate_transcript_path = (PROJECT_ROOT / Path(intermediate_transcript_rel_path_str)).resolve()
        if not intermediate_transcript_path.is_file(): raise FileNotFoundError(f"Intermediate transcript file not found: {intermediate_transcript_path}")
        start_time_total = job_data.get("start_time")
    except (ValueError, FileNotFoundError, Exception) as e:
         log(f"Error preparing for Part 2 for job {job_id}: {e}", "ERROR")
         job_manager.set_error(job_id, f"Failed to initialize Part 2: {e}")
         # Attempt DB log even on init failure
         final_job_data_for_db = job_manager.get_status(job_id); db_path=get_db_path(job_config)
         if final_job_data_for_db: log_job_to_db(final_job_data_for_db, db_path)
         return


    # --- Start Part 2 Processing ---
    job_manager.add_log(job_id, "Pipeline Part 2 started.", "INFO")
    try:
        # --- Step 1: Load Intermediate Transcript ---
        log(f"Step 1: Loading intermediate segments from {intermediate_transcript_path.name}", "INFO")
        with open(intermediate_transcript_path, "r", encoding='utf-8') as f:
            segments_to_process = json.load(f)
        if not segments_to_process or not isinstance(segments_to_process, list):
            raise RuntimeError("Loaded intermediate transcript data is empty or invalid.")

        # --- Step 2: Apply Final Speaker Mapping ---
        job_manager.update_status(job_id, STATUS_MAPPING_SPEAKERS)
        log(f"Step 2: Applying final speaker map...", "INFO") # Map details logged in job manager if needed
        final_segments = apply_speaker_mapping(segments_to_process, final_speaker_map)
        if final_segments is None: raise RuntimeError("Applying final speaker mapping failed.")
        job_manager.add_log(job_id, "Final speaker name assignment complete.", "SUCCESS")
        job_manager.update_progress(job_id, PROGRESS_AFTER_MAPPING)

        # --- Step 3: Save Final Transcript JSON ---
        # Construct relative and absolute paths
        final_transcript_path_rel = intermediate_transcript_path.relative_to(PROJECT_ROOT).parent / DEFAULT_FINAL_JSON_FILENAME
        final_transcript_path = PROJECT_ROOT / final_transcript_path_rel
        log(f"Step 3: Saving final transcript to {final_transcript_path_rel}...", "INFO")
        try:
            final_transcript_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
            with open(final_transcript_path, "w", encoding='utf-8') as f:
                 json.dump(final_segments, f, indent=2, ensure_ascii=False)
            job_manager.add_log(job_id, f"Final transcript JSON saved: {final_transcript_path_rel}", "INFO")
        except Exception as e:
            job_manager.add_log(job_id, f"Warning: Failed to save final transcript JSON: {e}", "WARNING")
            # Consider if this should be a critical error
        check_stop(job_id, "saving final transcript")

        # --- Step 4: Generate and Save HTML Transcript ---
        job_manager.update_status(job_id, STATUS_REFORMATTING)
        log(f"Step 4: Generating HTML transcript...", "INFO")
        html_transcript_path_rel = Path(RESULTS_DIR_NAME) / DEFAULT_HTML_TRANSCRIPT_FILENAME
        html_transcript_path = PROJECT_ROOT / html_transcript_path_rel
        try:
            html_output_string = format_transcript_html(final_segments)
            if html_output_string:
                 html_transcript_path.parent.mkdir(parents=True, exist_ok=True)
                 with open(html_transcript_path, "w", encoding='utf-8') as f: f.write(html_output_string)
                 job_manager.add_log(job_id, f"HTML transcript saved: {html_transcript_path_rel}", "SUCCESS")
            else: job_manager.add_log(job_id, "HTML generation returned empty string.", "WARNING")
        except Exception as e:
            job_manager.add_log(job_id, f"Warning: HTML transcript generation/saving failed: {e}", "WARNING")
            log(traceback.format_exc(), "DEBUG")
        job_manager.update_progress(job_id, PROGRESS_AFTER_REFORMAT)
        check_stop(job_id, "HTML reformatting")

        # --- Step 5: LLM Analysis ---
        job_manager.update_status(job_id, STATUS_ANALYZING)
        mode = job_config.get("mode", "fast")
        log(f"Step 5: Starting LLM analysis (Mode: {mode})...", "INFO")
        start_time_analysis = time.time()

        # --- Load and Prepare Transcript Text (Once) ---
        analysis_input_text: Optional[str] = None
        try:
            # Ensure the final transcript file (with names) was created successfully
            if not final_transcript_path or not final_transcript_path.is_file():
                 raise FileNotFoundError(f"Final transcript JSON for analysis not found at {final_transcript_path}")

            log(f"Loading text from {final_transcript_path.name} for LLM analysis...", "DEBUG")
            with open(final_transcript_path, "r", encoding='utf-8') as f:
                 # Reload segments (could optimize by reusing 'final_segments' if guaranteed valid)
                 loaded_final_segments = json.load(f)
            if not isinstance(loaded_final_segments, list):
                 raise ValueError("Invalid format in final transcript JSON (expected list).")

            # Construct text string including speaker names (important for context)
            text_lines = [
                f"{segment.get('speaker_name', 'Unknown')}: {segment.get('text', '')}"
                for segment in loaded_final_segments if isinstance(segment, dict) and segment.get('text')
            ]
            analysis_input_text = "\n".join(text_lines).strip()

            if not analysis_input_text:
                 log("No text content found in final transcript JSON. Skipping LLM analysis.", "WARNING")
                 analysis_input_text = None # Ensure it's None to skip analysis block
            else:
                 log(f"Prepared text input for LLM analysis ({len(analysis_input_text)} chars).", "DEBUG")

        except Exception as e:
             log(f"Failed to load/prepare text from final transcript '{final_transcript_path.name}' for analysis: {e}. Skipping analysis.", "ERROR")
             analysis_input_text = None # Set to None to skip analysis

        # --- Run Analysis (Only if text preparation succeeded) ---
        if analysis_input_text:
            # Validate LLM Config section
            llm_models_config = job_config.get("llm_models")
            if not isinstance(llm_models_config, dict):
                raise ValueError("LLM analysis requires 'llm_models' dictionary in config.")

            try: # Inner try for the analysis execution block
                extra_context = job_config.get("extra_context_prompt", "")
                # Define output paths
                summary_path_rel = Path(RESULTS_DIR_NAME) / DEFAULT_SUMMARY_FILENAME
                advanced_analysis_path_rel = Path(RESULTS_DIR_NAME) / DEFAULT_ADVANCED_ANALYSIS_FILENAME
                summary_path = PROJECT_ROOT / summary_path_rel
                advanced_analysis_path = PROJECT_ROOT / advanced_analysis_path_rel
                # Ensure results directory exists
                advanced_analysis_path.parent.mkdir(parents=True, exist_ok=True)

                if mode == "fast":
                     log(f"Running LLM 'fast' mode (Summary)...", "INFO")
                     # --- Pass text string to summarize_transcript ---
                     summary_result = summarize_transcript(analysis_input_text, job_config, extra_context)
                     # -------------------------------------------------
                     if summary_result is None: raise RuntimeError("Summary generation failed.")
                     try:
                          with open(summary_path, "w", encoding='utf-8') as f: f.write(summary_result)
                          job_manager.add_log(job_id, f"Summary saved: {summary_path_rel}", "SUCCESS")
                     except IOError as e: job_manager.add_log(job_id, f"Failed to save summary file: {e}", "ERROR")

                elif mode == "advanced":
                     log(f"Running LLM 'advanced' mode...", "INFO")
                     results_dict: Dict[str, Any] = {}
                     tasks_to_run = { "summary": advanced_tasks.summary, "intent": advanced_tasks.intent, "actions": advanced_tasks.actions, "emotion": advanced_tasks.emotion, "questions": advanced_tasks.questions, "legal": advanced_tasks.legal }
                     total_tasks = len(tasks_to_run) + 1; completed_tasks = 0

                     for task_name, task_func in tasks_to_run.items():
                          check_stop(job_id, f"advanced LLM task '{task_name}'")
                          job_manager.add_log(job_id, f"Running LLM task: {task_name}...", "INFO")
                          # --- Pass text string to advanced task functions ---
                          task_result = task_func(analysis_input_text, job_config, extra_context)
                          # ---------------------------------------------------
                          results_dict[task_name] = task_result
                          log_level = "SUCCESS" if task_result is not None else "WARNING"
                          job_manager.add_log(job_id, f"LLM task '{task_name}' finished.", log_level)
                          completed_tasks += 1
                          # Update progress incrementally
                          current_progress = PROGRESS_AFTER_REFORMAT + int((completed_tasks / total_tasks) * (PROGRESS_AFTER_ANALYSIS - PROGRESS_AFTER_REFORMAT))
                          job_manager.update_progress(job_id, current_progress)

                     check_stop(job_id, "final LLM analysis")
                     job_manager.add_log(job_id, "Running final aggregating LLM analysis...", "INFO")
                     final_agg_result = advanced_tasks.run_final_analysis(results_dict, job_config, extra_context)
                     if final_agg_result is None: raise RuntimeError("Final aggregating analysis task failed.")
                     results_dict["final_analysis"] = final_agg_result
                     job_manager.add_log(job_id, "Final aggregating analysis completed.", "SUCCESS")
                     advanced_results = results_dict

                     try: # Save advanced results JSON
                          with open(advanced_analysis_path, "w", encoding='utf-8') as f:
                              json.dump(advanced_results, f, indent=2, ensure_ascii=False)
                          job_manager.add_log(job_id, f"Advanced analysis results saved: {advanced_analysis_path_rel}", "SUCCESS")
                     except Exception as e:
                          job_manager.add_log(job_id, f"Failed to save advanced analysis JSON: {e}", "ERROR")
                          log(traceback.format_exc(), "DEBUG")
                else:
                     job_manager.add_log(job_id, f"Unknown analysis mode '{mode}'. Skipping LLM analysis.", "WARNING")

                elapsed_analysis = round(time.time() - start_time_analysis, 2)
                job_manager.add_log(job_id, f"LLM analysis step finished in {elapsed_analysis}s.", "SUCCESS")
            except Exception as e: # Catch errors during LLM analysis phase
                raise RuntimeError(f"LLM analysis step failed: {e}") from e
        else:
             # Case where analysis_input_text was None
             log("Skipping LLM analysis because transcript text could not be prepared.", "WARNING")

        job_manager.update_progress(job_id, PROGRESS_AFTER_ANALYSIS)
        check_stop(job_id, "LLM analysis completion")


        # --- Step 6: Finalize Job ---
        log(f"Step 6: Finalizing job results for {job_id}...", "INFO")
        # Prepare the final result dictionary for JobManager and DB logging
        final_result_data = {
            "intermediate_transcript_path": str(intermediate_transcript_path.relative_to(PROJECT_ROOT)) if intermediate_transcript_path else None,
            "final_transcript_json_path": str(final_transcript_path_rel) if final_transcript_path and final_transcript_path.exists() else None,
            "html_transcript_path": str(html_transcript_path_rel) if html_transcript_path and html_transcript_path.exists() else None,
            "summary_path": str(summary_path_rel) if mode == "fast" and summary_path and summary_path.exists() else None,
            "advanced_analysis_path": str(advanced_analysis_path_rel) if mode == "advanced" and advanced_analysis_path and advanced_analysis_path.exists() else None,
            # Include direct content
            "summary_content": summary_result if mode == "fast" else (advanced_results.get("summary") if advanced_results else None),
            "intent_result": advanced_results.get("intent") if advanced_results else None,
            "actions_result": advanced_results.get("actions") if advanced_results else None,
            "emotion_result": advanced_results.get("emotion") if advanced_results else None,
            "questions_result": advanced_results.get("questions") if advanced_results else None,
            "legal_result": advanced_results.get("legal") if advanced_results else None,
            "final_analysis_result": advanced_results.get("final_analysis") if advanced_results else None,
            # Include actual data used/produced for DB logging
            "final_transcript_segments": final_segments, # Transcript with names
            "speaker_mapping_used": final_speaker_map, # Map applied
         }
        # Set final result and mark job as COMPLETED
        job_manager.set_result(job_id, final_result_data)
        elapsed_total = round(time.time() - start_time_total, 2) if start_time_total else 'N/A'
        job_manager.add_log(job_id, f"Pipeline completed successfully. Total time: {elapsed_total}s.", "SUCCESS")


    # --- Outer Exception Handling for Part 2 ---
    except InterruptedError as e:
        error_msg = f"Pipeline Part 2 stopped by user request."
        job_manager.update_status(job_id, STATUS_STOPPED)
        job_manager.add_log(job_id, error_msg, "WARNING")
        log(f"Job {job_id} operation stopped cleanly via request during Part 2: {e}", "INFO")
    except (RuntimeError, ValueError, FileNotFoundError) as e: # Catch specific expected errors
        error_msg = f"Pipeline Part 2 failed: {e}"
        log(error_msg, "ERROR")
        log(traceback.format_exc(), "DEBUG")
        job_manager.set_error(job_id, error_msg)
    except Exception as e: # Catch unexpected errors
        error_msg = f"Unexpected critical error in Pipeline Part 2: {e}"
        log(error_msg, "CRITICAL")
        log(traceback.format_exc(), "ERROR")
        job_manager.set_error(job_id, error_msg)

    # --- Database Logging (Always Attempted) ---
    finally:
        log(f"Pipeline Part 2 execution finished for job {job_id}. Attempting database logging...", "INFO")
        final_job_data_for_db = job_manager.get_status(job_id)
        if final_job_data_for_db:
            log(f"Final job status for DB logging: {final_job_data_for_db.get('status')}", "DEBUG")
            # Pass config retrieved at start of Part 2 to get correct DB path
            db_path = get_db_path(job_config if job_config else None)
            logged_ok = log_job_to_db(final_job_data_for_db, db_path)
            job_manager.add_log(job_id, f"Database logging attempt complete (Success: {logged_ok}).", "INFO" if logged_ok else "WARNING")
        else:
            log(f"CRITICAL: Could not retrieve final job data for {job_id} in Part 2 finally block! DB log skipped.", "CRITICAL")

# --- End of pipeline_part2.py ---