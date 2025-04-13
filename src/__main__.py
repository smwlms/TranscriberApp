# src/__main__.py
import argparse
import time
import json
import traceback
from pathlib import Path
from typing import Dict, Any

# Load environment variables from .env file first
from dotenv import load_dotenv # type: ignore
load_dotenv()

# Setup logging next - Call setup_logging early
# Assuming log.py handles config loading failures gracefully for defaults
from src.utils.log import setup_logging, log
setup_logging()

# Import necessary components AFTER logging is setup
from src.database_logger import initialize_database
from src.job_manager import job_manager # Use the singleton instance
# --- Import the NEW CLI pipeline runner ---
from src.pipeline_cli import run_full_pipeline_cli
# ----------------------------------------
from src.utils.load_config import load_config # Still needed for fallback input_audio

def main():
    """Command-Line Interface entry point."""
    # Initialize database (can happen after logging is setup)
    initialize_database()

    parser = argparse.ArgumentParser(description="Run the Real Estate Transcriber pipeline via CLI.")
    # Argument parsing (mostly unchanged, added notes)
    parser.add_argument("-i", "--input-audio", type=str, help="Relative path to input audio.")
    parser.add_argument("-m", "--mode", choices=["fast", "advanced"], help="Processing mode.")
    parser.add_argument("--whisper-model", type=str, help="Whisper model size.")
    parser.add_argument("--compute-type", type=str, help="Whisper compute type.")
    parser.add_argument("-l", "--language", type=str, help="Language code (leave empty for auto).")
    parser.add_argument("--speaker-map", type=str, help="Path to speaker map YAML (NOTE: Overridden by auto-detection in CLI).")
    parser.add_argument("--context", type=str, help="Extra context prompt.")
    # Example for adding a boolean flag if needed later:
    # parser.add_argument("--no-name-detect", action="store_false", dest="speaker_name_detection_enabled", help="Disable speaker name detection")
    args = parser.parse_args()

    log("INFO", "--- Starting New CLI Run ---")

    # --- Process Config Overrides ---
    config_overrides: Dict[str, Any] = {}
    if args.input_audio: config_overrides["input_audio"] = args.input_audio
    if args.mode: config_overrides["mode"] = args.mode
    if args.whisper_model: config_overrides["whisper_model"] = args.whisper_model
    if args.compute_type: config_overrides["compute_type"] = args.compute_type
    # Handle language: empty string from CLI should mean None (auto-detect)
    if args.language is not None: config_overrides["language"] = args.language if args.language else None
    # Explicitly log that --speaker-map is ignored in CLI mode
    if args.speaker_map: log("WARNING", "CLI ignoring --speaker-map argument; uses auto-detection result or empty map.", "WARNING")
    if args.context: config_overrides["extra_context_prompt"] = args.context
    # Example for boolean flag processing:
    # if 'speaker_name_detection_enabled' in vars(args): config_overrides["speaker_name_detection_enabled"] = args.speaker_name_detection_enabled

    # --- Ensure Input Audio Path is Set ---
    if not config_overrides.get("input_audio"):
        try:
            # Load base config only if needed for input_audio fallback
            base_config = load_config()
            input_from_config = base_config.get("input_audio")
            if input_from_config:
                config_overrides["input_audio"] = input_from_config
                log("INFO", f"Using input audio from config.yaml: {input_from_config}")
            else:
                log("ERROR", "Input audio path must be specified via --input-audio argument or set in config.yaml.")
                parser.print_help()
                return # Exit if no audio path is found
        except Exception as e:
             log(f"ERROR", f"Failed to load base config to check for input_audio: {e}")
             parser.print_help(); return

    log("INFO", f"Using CLI configuration overrides: {config_overrides}")

    # --- Create Job ---
    try:
        # Use the gathered overrides when creating the job
        actual_job_id = job_manager.create_job(initial_config=config_overrides)
        log("INFO", f"Created job entry with ID: {actual_job_id}")
    except Exception as e:
        log("CRITICAL", f"Failed to create job in JobManager: {e}")
        traceback.print_exc()
        return # Exit if job creation fails

    # --- Run the Full CLI Pipeline ---
    try:
        log("INFO", f"Calling run_full_pipeline_cli for job {actual_job_id}...")
        # *** REPLACE THE OLD run_pipeline_job CALL WITH THE NEW ONE ***
        run_full_pipeline_cli(job_id=actual_job_id, config_overrides=config_overrides)
        # The function above handles internal logging and status updates.
        log("INFO", f"run_full_pipeline_cli function call completed for job {actual_job_id}.")

    except Exception as e:
        # Catch potential errors during the *call* to the pipeline function itself
        log("CRITICAL", f"(__main__) Unexpected error occurred while calling run_full_pipeline_cli for job {actual_job_id}: {e}")
        log("CRITICAL", traceback.format_exc())
        try:
            # Ensure the job is marked as FAILED in JobManager if the runner itself crashed
            if job_manager.get_status(actual_job_id):
                job_manager.set_error(actual_job_id, f"Critical error in main __main__ during pipeline execution: {e}")
        except Exception as log_err:
            log("ERROR", f"(__main__) Additionally failed to set error status for {actual_job_id} after critical failure: {log_err}")
        log("ERROR", f"--- CLI Pipeline Run Failed Critically in __main__ (Job: {actual_job_id}) ---")

    # --- Display Final Status ---
    # The CLI function runs synchronously, so we can check status immediately after.
    log("INFO", f"--- Final Job Status Check (Job ID: {actual_job_id}) ---")
    final_status_data = job_manager.get_status(actual_job_id)

    if final_status_data:
        status = final_status_data.get('status', 'UNKNOWN')
        log("INFO", f"Final Status reported by JobManager: {status}")

        # Display results path or error message based on status
        if status == "COMPLETED":
             results = final_status_data.get("result", {})
             log("INFO", "Output Files / Data pointers:")
             for key, value in results.items():
                  # Display paths and direct content concisely
                  if value and isinstance(value, str) and ("path" in key or key.endswith("_content") or "result" in key):
                       log("INFO", f"  - {key}: {value}")
                  # Optionally display speaker mapping used
                  elif key == "speaker_mapping_used":
                       log("INFO", f"  - speaker_mapping_used: {value}")
        elif status == "FAILED":
            error_msg = final_status_data.get("error_message", "No specific error details provided.")
            log("ERROR", f"Pipeline failed: {error_msg}")
        elif status == "STOPPED":
            log("WARNING", "Pipeline run was stopped by user request.")
        else:
            # Should ideally not happen if pipeline logic is correct
            log("WARNING", f"Pipeline finished with an unexpected final status: {status}")
    else:
        # This indicates an issue retrieving status even after the sync run
        log("ERROR", f"Could not retrieve final status for job {actual_job_id} from JobManager after CLI pipeline completion.")

if __name__ == "__main__":
    main()