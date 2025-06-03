# src/pipeline_part1.py

import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.job_manager import (
    job_manager,
    STATUS_RUNNING,
    STATUS_PROCESSING_AUDIO,
    STATUS_DETECTING_NAMES,
    STATUS_WAITING_FOR_REVIEW,
    STATUS_STOPPED,
    STATUS_FAILED,
)
from src.transcriber import (
    transcribe_and_diarize,
    DEFAULT_WHISPER_MODEL,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_PYANNOTE_PIPELINE,
)
from src.utils.load_config import load_config
from src.utils.config_schema import PROJECT_ROOT
from src.utils.log import log
from src.utils.pipeline_helpers import check_stop, merge_configs
from src.constants import (
    PROGRESS_START as APP_PROGRESS_START,
    PROGRESS_AFTER_AUDIO_PROCESSING as APP_PROGRESS_AFTER_AUDIO_PROCESSING,
    PROGRESS_AFTER_NAME_DETECT as APP_PROGRESS_AFTER_NAME_DETECT,
    PROGRESS_WAITING_REVIEW as APP_PROGRESS_WAITING_REVIEW,
)

try:
    from src.speaker_name_detector import detect_speaker_names
    NAME_DETECTOR_AVAILABLE = True
except ImportError:
    log(
        "[PipelinePart1 WARNING] Speaker name detector module (src.speaker_name_detector) not found, disabling automatic name detection.",
        "WARNING",
    )
    NAME_DETECTOR_AVAILABLE = False

    def detect_speaker_names(*args, **kwargs) -> Tuple[Dict[str, Any], Dict[int, str]]:
        return {}, {}

log("Loaded src/pipeline_part1.py", "DEBUG")

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
        job_manager._update_job_state(job_id, {"config": job_config}) # Sla de gebruikte config op
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

        # Paden voor intermediate bestanden bepalen
        int_transcript_rel_str = job_config.get("intermediate_transcript_path", str(Path(TRANSCRIPTS_DIR_NAME) / DEFAULT_INTERMEDIATE_JSON_FILENAME))
        intermediate_transcript_path_rel = Path(int_transcript_rel_str)
        # Afgeleide paden voor map en snippets, in dezelfde map als intermediate transcript
        proposed_map_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_PROPOSED_MAP_FILENAME)
        context_snippets_path_rel = intermediate_transcript_path_rel.with_name(DEFAULT_CONTEXT_SNIPPETS_FILENAME)

        intermediate_transcript_path_abs = (PROJECT_ROOT / intermediate_transcript_path_rel).resolve()
        proposed_map_path_abs = (PROJECT_ROOT / proposed_map_path_rel).resolve()
        context_snippets_path_abs = (PROJECT_ROOT / context_snippets_path_rel).resolve()

        # Zorg ervoor dat de map voor intermediate transcript bestaat
        intermediate_transcript_path_abs.parent.mkdir(parents=True, exist_ok=True)
        log(f"Intermediate transcript relative path: {intermediate_transcript_path_rel}", "DEBUG", job_id=job_id)
        log(f"Proposed map relative path: {proposed_map_path_rel}", "DEBUG", job_id=job_id)
        log(f"Context snippets relative path: {context_snippets_path_rel}", "DEBUG", job_id=job_id)

        # Parameters voor transcribe_and_diarize
        whisper_model = job_config.get("whisper_model", DEFAULT_WHISPER_MODEL)
        compute_type = job_config.get("compute_type", DEFAULT_COMPUTE_TYPE)
        language = job_config.get("language") # Kan None zijn voor auto-detect
        pyannote_pipeline_name_from_config = job_config.get("pyannote_pipeline")
        pyannote_pipeline = pyannote_pipeline_name_from_config or DEFAULT_PYANNOTE_PIPELINE
        hf_token = os.environ.get("HUGGING_FACE_TOKEN") or job_config.get("hf_token")
        name_detection_enabled = job_config.get("speaker_name_detection_enabled", True)
        word_timestamps_enabled = job_config.get("word_timestamps_enabled", True) # Was False, True is meestal beter voor review

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
            word_timestamps_enabled=word_timestamps_enabled
        )
        print(f"--- PRINT DEBUG (pipeline_part1): Returned from transcribe_and_diarize for job {job_id} ---", flush=True)

        if intermediate_segments is None: # transcribe_and_diarize kan None returnen bij een fout
            raise RuntimeError("Audio processing (transcription and diarization) failed and returned None.")

        elapsed_audio = round(time.time() - start_time_audio, 2)
        job_manager.add_log(job_id, f"Audio processing finished in {elapsed_audio}s.", "SUCCESS")
        print(f"--- PRINT DEBUG (pipeline_part1): After audio processing finished log for job {job_id} ---", flush=True)

        try:
            if intermediate_transcript_path_abs is None: # Moet hier gedefinieerd zijn
                raise ValueError("intermediate_transcript_path_abs is None before saving intermediate transcript")
            print(f"--- PRINT DEBUG (pipeline_part1): Trying to save intermediate transcript to {intermediate_transcript_path_abs} for job {job_id} ---", flush=True)
            with open(intermediate_transcript_path_abs, "w", encoding='utf-8') as f:
                json.dump(intermediate_segments, f, indent=2, ensure_ascii=False)
            job_manager.add_log(job_id, f"Intermediate transcript saved: {intermediate_transcript_path_rel}", "INFO")
            print(f"--- PRINT DEBUG (pipeline_part1): Intermediate transcript SAVED for job {job_id} ---", flush=True)
        except Exception as e:
            raise RuntimeError(f"Failed to save intermediate transcript to '{intermediate_transcript_path_abs}': {e}")

        job_manager.update_progress(job_id, PROGRESS_AFTER_AUDIO_PROCESSING)
        check_stop(job_id, "audio processing")
        print(f"--- PRINT DEBUG (pipeline_part1): After check_stop post audio processing for job {job_id} ---", flush=True)

        # --- Step 4: Speaker Name Detection (Optional LLM step) ---
        # De uiteindelijke map die wordt opgeslagen. Moet Dict[str, Dict] zijn als de nieuwe detector wordt gebruikt.
        # Of Dict[str, Optional[str]] als de oude logica wordt gevolgd.
        # Laten we voor nu de output van detect_speaker_names direct gebruiken.
        proposed_map_to_save: Dict[str, Any] = {}
        detection_context_snippets: Dict[int, str] = {}
        next_status_after_step4 = STATUS_WAITING_FOR_REVIEW # Default, wordt niet gewijzigd in deze flow
        print(f"--- PRINT DEBUG (pipeline_part1): Reached beginning of Step 4 (Name Detection) for job {job_id} ---", flush=True)

        if name_detection_enabled and NAME_DETECTOR_AVAILABLE:
            log(f"Step 4: Attempting speaker name detection (LLM)...", "INFO", job_id=job_id)
            job_manager.update_status(job_id, STATUS_DETECTING_NAMES)
            start_time_detect = time.time()
            try:
                if intermediate_segments is None:
                     raise RuntimeError("Cannot run name detection: intermediate_segments is None (should not happen).")

                # detect_speaker_names signature: Tuple[Dict[str, Any], Dict[int, str]]
                # waar de eerste Dict is { "SPEAKER_XX": {"name": "John", "reasoning_indices": [1,2]} }
                proposed_map_from_detector, context_snippets_result = detect_speaker_names(
                    transcript_segments=intermediate_segments,
                    config=job_config # Geef de volledige job_config mee
                )
                elapsed_detect = round(time.time() - start_time_detect, 2)

                if proposed_map_from_detector is None:
                    log("Speaker name detection function returned None (LLM error likely). Using empty map.", "WARNING", job_id=job_id)
                    proposed_map_to_save = {}
                else:
                    proposed_map_to_save = proposed_map_from_detector

                detection_context_snippets = context_snippets_result or {}
                job_manager.add_log(job_id, f"Speaker name detection finished in {elapsed_detect}s. Proposed map keys: {list(proposed_map_to_save.keys())}", "SUCCESS")

                try:
                    if proposed_map_path_abs is None: raise ValueError("proposed_map_path_abs is None before saving map")
                    with open(proposed_map_path_abs, "w", encoding='utf-8') as f:
                        json.dump(proposed_map_to_save, f, indent=2, ensure_ascii=False)
                    job_manager.add_log(job_id, f"Proposed speaker map saved: {proposed_map_path_rel}", "INFO")

                    if detection_context_snippets: # Alleen opslaan als er snippets zijn
                        if context_snippets_path_abs is None: raise ValueError("context_snippets_path_abs is None before saving snippets")
                        with open(context_snippets_path_abs, "w", encoding='utf-8') as f:
                            json.dump(detection_context_snippets, f, indent=2, ensure_ascii=False)
                        job_manager.add_log(job_id, f"Context snippets saved: {context_snippets_path_rel}", "INFO")
                    elif context_snippets_path_abs and context_snippets_path_abs.exists(): # Verwijder als leeg en bestand bestaat
                        context_snippets_path_abs.unlink(missing_ok=True)
                        job_manager.add_log(job_id, f"No context snippets, removed existing file: {context_snippets_path_rel}", "DEBUG")

                except Exception as e_save_detect:
                    # Log als waarschuwing, pipeline gaat door zonder deze bestanden
                    job_manager.add_log(job_id, f"Warning: Failed to save name detection results: {e_save_detect}", "WARNING")
            except Exception as e_detect:
                log(f"Speaker name detection step encountered an error: {e_detect}. Proceeding without proposed names.", "ERROR", job_id=job_id)
                log(traceback.format_exc(), "DEBUG", job_id=job_id)
                job_manager.add_log(job_id, "Speaker name detection failed, proceeding without proposed names.", "WARNING")
                if proposed_map_path_abs and proposed_map_path_abs.exists(): proposed_map_path_abs.unlink(missing_ok=True)
                if context_snippets_path_abs and context_snippets_path_abs.exists(): context_snippets_path_abs.unlink(missing_ok=True)
                proposed_map_to_save = {} # Reset naar lege map

            job_manager.update_progress(job_id, PROGRESS_AFTER_NAME_DETECT)
            # check_stop(job_id, "speaker name detection") # Optioneel, was niet in "werkende" versie
        elif not NAME_DETECTOR_AVAILABLE:
            job_manager.add_log(job_id, "Speaker name detector module not found, skipping.", "WARNING")
        else: # name_detection_enabled is False
            job_manager.add_log(job_id, "Automatic speaker name detection disabled in config.", "INFO")
        print(f"--- PRINT DEBUG (pipeline_part1): Finished Step 4 (Name Detection) for job {job_id} ---", flush=True)

        # --- Step 5: Finalize Part 1 and Set State for Review ---
        print(f"--- PRINT DEBUG (pipeline_part1): Reached Step 5 (Finalize Part 1) for job {job_id} ---", flush=True)
        log(f"Step 5: Finalizing Part 1. Next status: '{next_status_after_step4}'", "DEBUG", job_id=job_id) # next_status_after_step4 is STATUS_WAITING_FOR_REVIEW
        job_manager.add_log(job_id, "Part 1 processing complete. Preparing for review.", "INFO")

        review_info = {}
        try:
            log(f"Step 5 Checkpoint 2a: Creating review_info dict...", "DEBUG", job_id=job_id)
            # Zorg ervoor dat paden relatief zijn en alleen worden toegevoegd als het bestand daadwerkelijk bestaat
            # Dit is belangrijk voor de frontend die get_review_data aanroept.
            transcript_exists = intermediate_transcript_path_abs is not None and intermediate_transcript_path_abs.exists()
            map_exists = proposed_map_path_abs is not None and proposed_map_path_abs.exists()
            snippets_exist = context_snippets_path_abs is not None and context_snippets_path_abs.exists()

            review_info = {
                "intermediate_transcript_path": str(intermediate_transcript_path_rel) if transcript_exists else None,
                "proposed_map_path": str(proposed_map_path_rel) if map_exists else None,
                "context_snippets_path": str(context_snippets_path_rel) if snippets_exist else None,
            }
            if review_info["intermediate_transcript_path"] is None:
                 # Dit zou niet mogen gebeuren als de eerdere opslag succesvol was.
                 raise RuntimeError("Intermediate transcript file missing or path is None before finalization of Part 1.")
            log(f"Step 5 Checkpoint 3: Successfully created review_info: {review_info}", "DEBUG", job_id=job_id)
        except Exception as e_info:
             log(f"CRITICAL ERROR creating review_info dictionary: {e_info}", "CRITICAL", job_id=job_id)
             raise RuntimeError(f"Failed to create review_info dictionary: {e_info}") from e_info # Propagate error

        try:
            log(f"Step 5 Checkpoint 3a: Running check_stop (before final state update)...", "DEBUG", job_id=job_id)
            check_stop(job_id, "before final state update in Part 1")
            log(f"Step 5 Checkpoint 4: Passed check_stop.", "DEBUG", job_id=job_id)
        except InterruptedError as ie_final: # Vang specifiek InterruptedError
            raise ie_final # Gooi opnieuw zodat de outer try block het correct afhandelt
        except Exception as e_stop: # Vang andere errors van check_stop
            log(f"CRITICAL ERROR during check_stop call: {e_stop}", "CRITICAL", job_id=job_id)
            raise RuntimeError(f"Failed during stop check: {e_stop}") from e_stop

        log(f"Step 5 Checkpoint 5: Attempting final state update call to JobManager for job {job_id}...", "DEBUG", job_id=job_id)
        update_successful = False
        final_status_to_set = next_status_after_step4 # Moet STATUS_WAITING_FOR_REVIEW zijn
        try:
            update_payload = {
                "status": final_status_to_set,
                "progress": PROGRESS_WAITING_REVIEW,
                "review_data_paths": review_info # Dit wordt in job_data opgeslagen
            }
            # Gebruik update_job_state voor meerdere velden, of set_status als het alleen de status is.
            # _update_job_state is "protected", beter om publieke methodes te gebruiken indien mogelijk.
            # Laten we aannemen dat _update_job_state de bedoelde methode is om meerdere velden tegelijk te zetten.
            update_successful = job_manager._update_job_state(job_id, update_payload) # Geeft True/False terug?
            # Als het geen boolean teruggeeft, verwijder `update_successful =` en neem aan dat het een exception gooit bij falen.
            # Voor nu, houd de logica van de "werkende" versie aan.
        except Exception as e_update:
            log(f"CRITICAL ERROR during final _update_job_state call for job {job_id}: {e_update}", "CRITICAL", job_id=job_id)
            log(traceback.format_exc(), "ERROR", job_id=job_id) # Log volledige traceback
            raise RuntimeError(f"Failed during final job state update: {e_update}") from e_update

        log(f"Step 5 Checkpoint 6: Result of final state update call was: {update_successful} for job {job_id}", "DEBUG", job_id=job_id)
        # De "werkende" versie checkte update_successful niet. Als _update_job_state geen boolean teruggeeft,
        # of als het altijd True is tenzij er een exception is, is deze check overbodig.
        # We nemen aan dat als er geen exception was, het goed is gegaan.

        log(f"Step 5 Checkpoint 7: Final state for Part 1 set successfully to '{final_status_to_set}'. Job: {job_id}", "DEBUG", job_id=job_id)

        # DEBUGGING: Wacht heel even en check de status opnieuw.
        time.sleep(0.1) # Korte pauze van 100ms
        try:
            current_status_after_short_delay = job_manager.get_status(job_id).get('status')
            log(f"DEBUG_PIPELINE_PART1: Status 0.1s after setting '{final_status_to_set}' is now: '{current_status_after_short_delay}'. Job: {job_id}", "CRITICAL", job_id=job_id)
            if current_status_after_short_delay != final_status_to_set:
                log(f"DEBUG_PIPELINE_PART1_ALARM: Status changed from '{final_status_to_set}' to '{current_status_after_short_delay}' " \
                    f"within 0.1s *inside* run_part1 thread just before exiting! Job: {job_id}", "CRITICAL", job_id=job_id)
        except Exception as e_debug_status:
            log(f"DEBUG_PIPELINE_PART1_ERROR: Could not re-fetch status for debug check after Part 1 completion: {e_debug_status}", "ERROR", job_id=job_id)

        print(f"--- PRINT DEBUG (pipeline_part1): Part 1 COMPLETED and thread about to exit for job {job_id} ---", flush=True)

    except (FileNotFoundError, ValueError, RuntimeError, InterruptedError) as e:
        status_to_set = STATUS_STOPPED if isinstance(e, InterruptedError) else STATUS_FAILED
        log_level = "WARNING" if status_to_set == STATUS_STOPPED else "ERROR"
        error_msg_detail = str(e)

        if isinstance(e, FileNotFoundError): error_msg_prefix = "Required file not found"
        elif isinstance(e, ValueError): error_msg_prefix = "Invalid configuration or value"
        elif isinstance(e, RuntimeError): error_msg_prefix = "Processing step runtime error"
        elif isinstance(e, InterruptedError): error_msg_prefix = f"Stopped by user request"
        else: error_msg_prefix = "Pipeline error" # Zou niet moeten gebeuren met huidige excepts

        # Maak het volledige error bericht
        full_error_msg = f"Pipeline Part 1 {status_to_set.lower()}: {error_msg_prefix}"
        if not isinstance(e, InterruptedError): # Voeg detail toe als het geen normale stop is
             full_error_msg += f" - Detail: {error_msg_detail}"

        log(full_error_msg, log_level, job_id=job_id)
        if not isinstance(e, InterruptedError): # Log traceback alleen voor daadwerkelijke errors
            log(traceback.format_exc(), "DEBUG", job_id=job_id)

        try:
            if status_to_set == STATUS_STOPPED:
                 current_data = job_manager.get_status(job_id)
                 # Voorkom onnodige status update of het overschrijven van een latere status
                 if current_data and current_data.get("status") != STATUS_STOPPED :
                      job_manager.update_status(job_id, STATUS_STOPPED) # Geen error message hier
                      job_manager.add_log(job_id, "Job flagged as STOPPED due to interruption in Part 1.", "INFO")
            else: # STATUS_FAILED
                 job_manager.set_error(job_id, full_error_msg) # set_error zal status op FAILED zetten
        except Exception as set_err_ex:
            log(f"CRITICAL: Failed to set final error/stopped status in JobManager for job {job_id} after error: {set_err_ex}", "CRITICAL", job_id=job_id)

    except Exception as e_unhandled: # Vang alle andere onverwachte exceptions
        # Dit is voor programmeerfouten of onverwachte systeemfouten
        unhandled_error_msg = f"Unexpected critical error in Pipeline Part 1: {e_unhandled.__class__.__name__} - {e_unhandled}"
        log(unhandled_error_msg, "CRITICAL", job_id=job_id)
        log(traceback.format_exc(), "ERROR", job_id=job_id) # Altijd volledige traceback voor CRITICAL
        try:
            job_manager.set_error(job_id, unhandled_error_msg) # Probeer de error op te slaan
        except Exception as set_final_err_ex:
             log(f"CRITICAL: Failed to set final CRITICAL error status in JobManager for job {job_id}: {set_final_err_ex}", "CRITICAL", job_id=job_id)
    finally:
        log(f"--- Exiting run_part1 function (finally block) for Job ID: {job_id} ---", "DEBUG", job_id=job_id)

# --- End of pipeline_part1.py ---