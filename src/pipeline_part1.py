# src/pipeline_part1.py (Gebaseerd op "werkende" versie, met debug prints)
import time
import os
import json
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.job_manager import job_manager, STATUS_RUNNING, STATUS_PROCESSING_AUDIO, \
    STATUS_DETECTING_NAMES, STATUS_WAITING_FOR_REVIEW, \
    STATUS_STOPPED, STATUS_FAILED
from src.transcriber import transcribe_and_diarize, DEFAULT_WHISPER_MODEL, \
     DEFAULT_COMPUTE_TYPE, DEFAULT_PYANNOTE_PIPELINE

try:
    from src.speaker_name_detector import detect_speaker_names
    NAME_DETECTOR_AVAILABLE = True
except ImportError:
    print("[PipelinePart1 WARNING] Speaker name detector module (src.speaker_name_detector) not found, disabling automatic name detection.")
    NAME_DETECTOR_AVAILABLE = False
    def detect_speaker_names(*args, **kwargs) -> Tuple[Dict[str, Optional[str]], Dict[int, str]]: # Aangepast voor de "werkende" versie signature
        return {}, {}

from src.utils.load_config import load_config
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log
from src.utils.pipeline_helpers import check_stop, merge_configs
from src.constants import ( # Importeren van constants.py
    PROGRESS_START as APP_PROGRESS_START, # Alias om conflicten te vermijden als lokaal ook zo genoemd
    PROGRESS_AFTER_AUDIO_PROCESSING as APP_PROGRESS_AFTER_AUDIO_PROCESSING,
    PROGRESS_AFTER_NAME_DETECT as APP_PROGRESS_AFTER_NAME_DETECT,
    PROGRESS_WAITING_REVIEW as APP_PROGRESS_WAITING_REVIEW
)


# Gebruik de geimporteerde constantes met hun alias
PROGRESS_START = APP_PROGRESS_START
PROGRESS_AFTER_AUDIO_PROCESSING = APP_PROGRESS_AFTER_AUDIO_PROCESSING
PROGRESS_AFTER_NAME_DETECT = APP_PROGRESS_AFTER_NAME_DETECT
PROGRESS_WAITING_REVIEW = APP_PROGRESS_WAITING_REVIEW

# Constants for directory names relative to project root
RESULTS_DIR_NAME = "results"
TRANSCRIPTS_DIR_NAME = "transcripts"
# Define standard intermediate filenames
DEFAULT_INTERMEDIATE_JSON_FILENAME = "intermediate_transcript.json"
DEFAULT_PROPOSED_MAP_FILENAME = "intermediate_proposed_map.json"
DEFAULT_CONTEXT_SNIPPETS_FILENAME = "intermediate_context.json"


def run_part1(job_id: str, config_overrides: Dict[str, Any]):
    job_config: Dict[str, Any] = {}
    intermediate_segments: Optional[List[Dict[str, Any]]] = None
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
        log(f"Step 1: Loading and merging configuration...", "DEBUG", job_id=job_id)
        base_config = load_config()
        job_config = merge_configs(base_config, config_overrides)
        job_manager._update_job_state(job_id, {"config": job_config})
        log(f"Part 1: Configuration prepared. Mode: {job_config.get('mode', 'N/A')}", "INFO", job_id=job_id)
        check_stop(job_id, "configuration loading")

        # --- Step 2: Validate Input Paths and Parameters ---
        log(f"Step 2: Validating inputs...", "DEBUG", job_id=job_id)
        input_audio_rel_path_str = job_config.get("input_audio")
        if not input_audio_rel_path_str:
            raise ValueError("Configuration Error: 'input_audio' path missing.")
        input_audio_rel_path = Path(input_audio_rel_path_str)
        input_audio_abs_path = (PROJECT_ROOT / input_audio_rel_path).resolve()
        if not input_audio_abs_path.is_file():
             raise FileNotFoundError(f"Input audio file not found at resolved path: {input_audio_abs_path}")
        log(f"Input audio validated: {input_audio_abs_path.name}", "INFO", job_id=job_id)

        int_transcript_rel_str = job_config.get("intermediate_transcript_path", str(Path(TRANSCRIPTS_DIR_NAME) / DEFAULT_INTERMEDIATE_JSON_FILENAME))
        intermediate_transcript_path_rel = Path(int_transcript_rel_str)
        proposed_map_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_PROPOSED_MAP_FILENAME)
        context_snippets_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_CONTEXT_SNIPPETS_FILENAME)
        intermediate_transcript_path_abs = PROJECT_ROOT / intermediate_transcript_path_rel
        proposed_map_path_abs = PROJECT_ROOT / proposed_map_path_rel
        context_snippets_path_abs = PROJECT_ROOT / context_snippets_path_rel
        intermediate_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        log(f"Intermediate transcript relative path: {intermediate_transcript_path_rel}", "DEBUG", job_id=job_id)

        whisper_model = job_config.get("whisper_model", DEFAULT_WHISPER_MODEL)
        compute_type = job_config.get("compute_type", DEFAULT_COMPUTE_TYPE)
        language = job_config.get("language")
        pyannote_pipeline_name_from_config = job_config.get("pyannote_pipeline") # Haal expliciet op
        pyannote_pipeline = pyannote_pipeline_name_from_config or DEFAULT_PYANNOTE_PIPELINE # Gebruik default als niet in config

        hf_token = os.environ.get("HUGGING_FACE_TOKEN") or job_config.get("hf_token")
        name_detection_enabled = job_config.get("speaker_name_detection_enabled", True) # Default True in "werkende" versie?
        word_timestamps_enabled = job_config.get("word_timestamps_enabled", False) # Toevoegen voor transcribe_and_diarize

        # --- Step 3: Audio Processing (Transcription & Diarization) ---
        log(f"Step 3: Starting audio processing (Transcription & Diarization)...", "INFO", job_id=job_id)
        job_manager.update_status(job_id, STATUS_PROCESSING_AUDIO)
        start_time_audio = time.time()

        intermediate_segments = transcribe_and_diarize(
            input_audio_path=input_audio_abs_path,
            whisper_model_size=whisper_model,
            compute_type=compute_type,
            language=language,
            hf_token=hf_token,
            pyannote_pipeline_name=pyannote_pipeline,
            word_timestamps_enabled=word_timestamps_enabled # Hier doorgeven
        )
        print(f"--- PRINT DEBUG (pipeline_part1): Returned from transcribe_and_diarize for job {job_id} ---", flush=True) # TOEGEVOEGD

        if intermediate_segments is None:
            raise RuntimeError("Audio processing (transcription and diarization) failed.")

        elapsed_audio = round(time.time() - start_time_audio, 2)
        job_manager.add_log(job_id, f"Audio processing finished in {elapsed_audio}s.", "SUCCESS")
        print(f"--- PRINT DEBUG (pipeline_part1): After audio processing finished log for job {job_id} ---", flush=True) # TOEGEVOEGD


        try:
            print(f"--- PRINT DEBUG (pipeline_part1): Trying to save intermediate transcript for job {job_id} ---", flush=True) # TOEGEVOEGD
            with open(intermediate_transcript_path_abs, "w", encoding='utf-8') as f:
                json.dump(intermediate_segments, f, indent=2, ensure_ascii=False)
            job_manager.add_log(job_id, f"Intermediate transcript saved: {intermediate_transcript_path_rel}", "INFO")
            print(f"--- PRINT DEBUG (pipeline_part1): Intermediate transcript SAVED for job {job_id} ---", flush=True) # TOEGEVOEGD
        except Exception as e:
            raise RuntimeError(f"Failed to save intermediate transcript to '{intermediate_transcript_path_abs}': {e}")

        job_manager.update_progress(job_id, PROGRESS_AFTER_AUDIO_PROCESSING)
        check_stop(job_id, "audio processing")
        print(f"--- PRINT DEBUG (pipeline_part1): After check_stop post audio processing for job {job_id} ---", flush=True) # TOEGEVOEGD


        # --- Step 4: Speaker Name Detection (Optional LLM step) ---
        detected_speaker_map: Dict[str, Optional[str]] = {} # Signature in werkende versie was Dict[str, Optional[str]]
        detection_context_snippets: Dict[int, str] = {}
        next_status_after_step4 = STATUS_WAITING_FOR_REVIEW
        print(f"--- PRINT DEBUG (pipeline_part1): Reached beginning of Step 4 (Name Detection) for job {job_id} ---", flush=True) # TOEGEVOEGD

        if name_detection_enabled and NAME_DETECTOR_AVAILABLE:
            log(f"Step 4: Attempting speaker name detection (LLM)...", "INFO", job_id=job_id)
            job_manager.update_status(job_id, STATUS_DETECTING_NAMES)
            start_time_detect = time.time()
            try:
                if intermediate_segments is None: # Noodzakelijke check
                     raise RuntimeError("Cannot run name detection: intermediate_segments is None.")
                # De "werkende" versie gaf Tuple[Dict[str, Optional[str]], Dict[int, str]] terug
                # De nieuwe `detect_speaker_names` geeft Tuple[Optional[Dict[str, Dict[str, Any]]], Optional[Dict[int, str]]]
                # We moeten hier consistent zijn. Laten we aannemen dat de dummy en de echte
                # nu de nieuwe structuur (met "reasoning_indices") moeten volgen.
                # Voor nu casten we of passen we de dummy aan. De dummy hierboven is al aangepast.
                proposed_map_from_detector, context_snippets_result = detect_speaker_names(
                    transcript_segments=intermediate_segments,
                    config=job_config
                )
                elapsed_detect = round(time.time() - start_time_detect, 2)

                if proposed_map_from_detector is None: # Kan None zijn bij een LLM fout
                    log("Speaker name detection function returned None (LLM error likely). Using empty map.", "WARNING", job_id=job_id)
                    detected_speaker_map = {} # Fallback
                else:
                    # De "werkende" `detect_speaker_names` gaf Dict[str, Optional[str]] terug.
                    # Als de nieuwe een Dict[str, Dict[str,Any]] teruggeeft, moeten we hier de 'name' uit halen.
                    # Voor nu gaan we uit van de *oude* return signature voor `detected_speaker_map`
                    # omdat de "werkende" versie daarmee werkte. Dit is een potentieel conflictpunt.
                    # Laten we aannemen dat de dummy en de echte `detect_speaker_names` nu een map teruggeven
                    # die direct bruikbaar is als `Dict[str, Optional[str]]` voor compatibiliteit met deze "werkende" flow.
                    # OF we passen hier de verwerking aan:
                    temp_map_for_logic = {}
                    if isinstance(proposed_map_from_detector, dict):
                        for spk_id, name_obj in proposed_map_from_detector.items():
                            if isinstance(name_obj, dict):
                                temp_map_for_logic[spk_id] = name_obj.get("name")
                            else: # Als het al de oude structuur is
                                temp_map_for_logic[spk_id] = name_obj
                    detected_speaker_map = temp_map_for_logic


                detection_context_snippets = context_snippets_result or {}
                job_manager.add_log(job_id, f"Speaker name detection finished in {elapsed_detect}s. Proposed map: {detected_speaker_map}", "SUCCESS")

                try:
                    if proposed_map_path_abs is None: raise ValueError("proposed_map_path_abs is None before saving map")
                    with open(proposed_map_path_abs, "w", encoding='utf-8') as f:
                        json.dump(detected_speaker_map, f, indent=2, ensure_ascii=False)
                    job_manager.add_log(job_id, f"Proposed speaker map saved: {proposed_map_path_rel}", "INFO")

                    if detection_context_snippets:
                        if context_snippets_path_abs is None: raise ValueError("context_snippets_path_abs is None before saving snippets")
                        with open(context_snippets_path_abs, "w", encoding='utf-8') as f:
                            json.dump(detection_context_snippets, f, indent=2, ensure_ascii=False)
                        job_manager.add_log(job_id, f"Context snippets saved: {context_snippets_path_rel}", "INFO")
                    elif context_snippets_path_abs:
                        context_snippets_path_abs.unlink(missing_ok=True)
                except Exception as e:
                    job_manager.add_log(job_id, f"Warning: Failed to save name detection results: {e}", "WARNING", job_id=job_id)
            except Exception as e:
                # De "werkende" versie had hier geen RuntimeError, maar ging door.
                # Laten we dat voor nu nabootsen, maar wel loggen.
                log(f"Speaker name detection step encountered an error: {e}. Proceeding without proposed names.", "ERROR", job_id=job_id)
                log(traceback.format_exc(), "DEBUG", job_id=job_id)
                job_manager.add_log(job_id, "Speaker name detection failed, proceeding without proposed names.", "WARNING")
                if proposed_map_path_abs: proposed_map_path_abs.unlink(missing_ok=True) # Probeer op te ruimen
                if context_snippets_path_abs: context_snippets_path_abs.unlink(missing_ok=True)
                detected_speaker_map = {} # Reset

            job_manager.update_progress(job_id, PROGRESS_AFTER_NAME_DETECT)
            # Geen check_stop hier in de "werkende" versie.
        elif not NAME_DETECTOR_AVAILABLE:
            job_manager.add_log(job_id, "Speaker name detector module not found, skipping.", "WARNING")
        else:
            job_manager.add_log(job_id, "Automatic speaker name detection disabled in config.", "INFO")
        print(f"--- PRINT DEBUG (pipeline_part1): Finished Step 4 (Name Detection) for job {job_id} ---", flush=True) # TOEGEVOEGD

        # --- Step 5: Finalize Part 1 and Set State for Review ---
        print(f"--- PRINT DEBUG (pipeline_part1): Reached Step 5 (Finalize Part 1) for job {job_id} ---", flush=True) # TOEGEVOEGD
        log(f"Step 5: Finalizing Part 1. Next status: '{next_status_after_step4}'", "DEBUG", job_id=job_id)
        job_manager.add_log(job_id, "Part 1 processing complete. Preparing for review.", "INFO")

        review_info = {}
        try:
            log(f"Step 5 Checkpoint 2a: Creating review_info dict...", "DEBUG", job_id=job_id)
            transcript_exists = intermediate_transcript_path_abs is not None and intermediate_transcript_path_abs.exists()
            map_exists = proposed_map_path_abs is not None and proposed_map_path_abs.exists()
            snippets_exist = context_snippets_path_abs is not None and context_snippets_path_abs.exists()

            review_info = {
                "intermediate_transcript_path": str(intermediate_transcript_path_rel) if transcript_exists else None,
                "proposed_map_path": str(proposed_map_path_rel) if map_exists else None,
                "context_snippets_path": str(context_snippets_path_rel) if snippets_exist else None,
            }
            if review_info["intermediate_transcript_path"] is None:
                 raise RuntimeError("Intermediate transcript file missing before finalization of Part 1.")
            log(f"Step 5 Checkpoint 3: Successfully created review_info: {review_info}", "DEBUG", job_id=job_id)
        except Exception as e_info:
             log(f"CRITICAL ERROR creating review_info dictionary: {e_info}", "CRITICAL", job_id=job_id)
             raise RuntimeError("Failed to create review_info dictionary") from e_info

        try:
            log(f"Step 5 Checkpoint 3a: Running check_stop (before final state update)...", "DEBUG", job_id=job_id)
            check_stop(job_id, "before final state update in Part 1") # Check hier, zoals in debug-versie
            log(f"Step 5 Checkpoint 4: Passed check_stop.", "DEBUG", job_id=job_id)
        except InterruptedError as ie:
            raise ie
        except Exception as e_stop:
            log(f"CRITICAL ERROR during check_stop call: {e_stop}", "CRITICAL", job_id=job_id)
            raise RuntimeError("Failed during stop check") from e_stop

        log(f"Step 5 Checkpoint 5: Attempting final state update call to JobManager...", "DEBUG", job_id=job_id)
        update_successful = False
        try:
            update_payload = {
                "status": next_status_after_step4,
                "progress": PROGRESS_WAITING_REVIEW,
                "review_data_paths": review_info
            }
            update_successful = job_manager._update_job_state(job_id, update_payload)
        except Exception as e_update:
            log(f"CRITICAL ERROR during final _update_job_state call: {e_update}", "CRITICAL", job_id=job_id)
            log(traceback.format_exc(), "ERROR", job_id=job_id)
            raise RuntimeError("Failed during final job state update") from e_update

        log(f"Step 5 Checkpoint 6: Result of final state update call was: {update_successful}", "DEBUG", job_id=job_id)
        if not update_successful:
            log(f"CRITICAL WARNING: Final state update call for Part 1 failed. Job: {job_id}", "CRITICAL", job_id=job_id)
            raise RuntimeError(f"Job Manager failed to update final state for job {job_id} in Part 1.")
        else:
            log(f"Step 5 Checkpoint 7: Final state for Part 1 set successfully.", "DEBUG", job_id=job_id)

        print(f"--- PRINT DEBUG (pipeline_part1): Part 1 COMPLETED for job {job_id} ---", flush=True) # TOEGEVOEGD

    except (FileNotFoundError, ValueError, RuntimeError, InterruptedError) as e: #AssertionError verwijderd
        status_to_set = STATUS_STOPPED if isinstance(e, InterruptedError) else STATUS_FAILED
        log_level = "WARNING" if status_to_set == STATUS_STOPPED else "ERROR"
        error_msg_detail = str(e)

        if isinstance(e, FileNotFoundError): error_msg_prefix = "Required file not found"
        elif isinstance(e, ValueError): error_msg_prefix = "Invalid configuration or value"
        # elif isinstance(e, AssertionError): error_msg_prefix = "Processing assertion failed" # Verwijderd
        elif isinstance(e, RuntimeError): error_msg_prefix = "Processing step runtime error"
        elif isinstance(e, InterruptedError): error_msg_prefix = f"Stopped by user request" # Detail zit al in e
        else: error_msg_prefix = "Pipeline error"

        error_msg = f"Pipeline Part 1 {status_to_set.lower()}: {error_msg_prefix}"
        if not isinstance(e, InterruptedError): # Voeg detail toe als het geen InterruptedError is
             error_msg += f" - {error_msg_detail}"

        log(error_msg, log_level, job_id=job_id)
        if not isinstance(e, InterruptedError): # Log traceback niet voor normale stops
            log(traceback.format_exc(), "DEBUG", job_id=job_id)

        try:
            if status_to_set == STATUS_STOPPED:
                 # Specifieke update voor gestopte status zonder error_message te overschrijven als die er al was
                 current_data = job_manager.get_status(job_id)
                 if current_data and current_data.get("status") != STATUS_STOPPED : # Alleen updaten als niet al STOPPED
                      job_manager.update_status(job_id, STATUS_STOPPED)
                      job_manager.add_log(job_id, "Job flagged as STOPPED due to interruption.", "INFO")
            else: # STATUS_FAILED
                 job_manager.set_error(job_id, error_msg)
        except Exception as set_err_ex:
            log(f"Failed to set final error/stopped status in JobManager for job {job_id}: {set_err_ex}", "ERROR", job_id=job_id)

    except Exception as e:
        error_msg = f"Unexpected critical error in Pipeline Part 1: {e.__class__.__name__} - {e}"
        log(error_msg, "CRITICAL", job_id=job_id)
        log(traceback.format_exc(), "ERROR", job_id=job_id)
        try:
            job_manager.set_error(job_id, error_msg)
        except Exception as set_err_ex:
             log(f"Failed to set final CRITICAL error status in JobManager for job {job_id}: {set_err_ex}", "ERROR", job_id=job_id)
    finally:
        log(f"--- Exiting run_part1 function for Job ID: {job_id} ---", "DEBUG", job_id=job_id)

# --- End of pipeline_part1.py ---