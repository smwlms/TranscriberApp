# File: src/transcriber.py (Refactored Orchestrator - Compleet met extra finally log)

import os
import uuid # Import uuid for unique temp filename generation
import traceback
import torch # Import torch
import time # Import time
import json # Import json for testing block below
import logging # Import logging for testing block below
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple # Ensure Tuple is imported

# --- Local Imports ---
# Utilities
# Use specific log function for consistency
from src.utils.log import log, setup_logging # Import setup_logging for test block
from src.utils.audio_utils import convert_to_wav
# Core processing modules
from src.core.model_loader import get_compute_device, load_models, DEFAULT_PYANNOTE_PIPELINE # Import DEFAULT_PYANNOTE_PIPELINE
from src.core.whisper_transcribe import run_transcription
from src.core.pyannote_diarize import run_diarization
from src.core.merge import merge_results

# --- Constants ---
# Defaults specific to the main orchestration logic
DEFAULT_WHISPER_MODEL = "small" # Default model size if not specified
DEFAULT_COMPUTE_TYPE = "int8" # Default compute type if not specified
# HF Token is better handled by fetching from env here if not provided as arg
DEFAULT_HF_TOKEN = os.environ.get("HUGGING_FACE_TOKEN")

# --- Internal Helper Function ---

def _cleanup_temp_file(temp_file_path: Optional[Path], original_input_path: Path):
    """Removes the temporary WAV file if it exists and is different from the original input."""
    log(f"[Cleanup] Helper function started.", "DEBUG")
    # Check if a temp path was actually created and exists
    if temp_file_path and temp_file_path.is_file():
        log(f"[Cleanup] Temp file path exists: {temp_file_path}", "DEBUG")
        # Ensure we don't delete the original if it was already a WAV
        if temp_file_path.resolve() != original_input_path.resolve():
            log(f"[Cleanup] Temp file is different from original. Attempting to remove temporary file: {temp_file_path.name}", "DEBUG")
            try:
                temp_file_path.unlink()
                # This INFO log was the last one seen previously
                log(f"Temporary WAV file removed successfully.", "INFO")
                log(f"[Cleanup] unlink() successful for {temp_file_path.name}", "DEBUG")
            except OSError as e:
                # Log failure to remove, but don't treat as a critical error
                log(f"Failed to remove temporary WAV file '{temp_file_path.name}': {e}", "WARNING")
                log(f"[Cleanup] unlink() failed for {temp_file_path.name}: {e}", "DEBUG")
        else:
            log(f"Skipping removal of temporary file as it's the same as the input: {temp_file_path.name}", "DEBUG")
            log(f"[Cleanup] Temp file is same as input, skipping removal.", "DEBUG")
    elif temp_file_path:
        log(f"Temporary file path '{temp_file_path}' provided but file does not exist. No cleanup needed.", "DEBUG")
        log(f"[Cleanup] Temp file path provided but file not found.", "DEBUG")
    else:
        log("[Cleanup] No temporary file path provided for cleanup.", "DEBUG")

    log(f"[Cleanup] Helper function finished.", "DEBUG")


# --- Main Public Function ---

def transcribe_and_diarize(
    input_audio_path: Path,
    whisper_model_size: str = DEFAULT_WHISPER_MODEL,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
    language: Optional[str] = None,
    hf_token: Optional[str] = DEFAULT_HF_TOKEN, # Use default from constant/env
    pyannote_pipeline_name: Optional[str] = None, # Allow override, defaults handled in loader
    word_timestamps_enabled: bool = False,
    # Diarization hints
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    # Allow device override
    compute_device_override: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Orchestrates transcription and diarization using refactored core modules.

    Args:
        input_audio_path: Path object pointing to the input audio file.
        whisper_model_size: Size of the FasterWhisper model (e.g., "tiny", "base", "small").
        compute_type: Compute type for Whisper (e.g., "int8", "float16").
        language: Optional language code (e.g., "en", "nl"). None for auto-detect.
        hf_token: Optional Hugging Face API token for Pyannote model access.
        pyannote_pipeline_name: Optional name of the Pyannote pipeline model override.
        word_timestamps_enabled: Whether to compute word-level timestamps.
        num_speakers: Optional fixed number of speakers hint for diarization.
        min_speakers: Optional minimum number of speakers hint.
        max_speakers: Optional maximum number of speakers hint.
        compute_device_override: Optional target device ("cuda", "mps", "cpu").

    Returns:
        A list of dictionaries, where each dictionary represents a merged segment
        containing 'text', 'start', 'end', 'speaker', and 'words' keys, or None if
        a critical error occurs during processing.
    """
    # Add unique ID for easier debugging of parallel runs if needed
    run_id = uuid.uuid4().hex[:6]
    log(f"[T&D-{run_id}] Starting transcription & diarization process for: {input_audio_path.name}", "INFO")
    log(f"[T&D-{run_id}] Function called with params: model={whisper_model_size}, compute={compute_type}, lang={language}, words={word_timestamps_enabled}, device_override={compute_device_override}", "DEBUG")
    start_process_time = time.time() # For overall timing

    if not isinstance(input_audio_path, Path):
         log(f"[T&D-{run_id}] Input audio path is not a Path object: {type(input_audio_path)}", "CRITICAL")
         return None
    if not input_audio_path.is_file():
        log(f"[T&D-{run_id}] Input audio file not found or invalid path: {input_audio_path}", "CRITICAL")
        return None
    log(f"[T&D-{run_id}] Input path validated: {input_audio_path}", "DEBUG")

    # Initialize variables
    temp_wav_path: Optional[Path] = None
    whisper_model = None # Explicitly define to ensure cleanup scope
    diarization_pipeline = None # Explicitly define
    final_result: Optional[List[Dict[str, Any]]] = None
    conversion_needed = False # Track if conversion happened for cleanup logic
    compute_device = "unknown" # Initialize for finally block safety

    try:
        # --- Step 1: Determine Compute Device ---
        log(f"[T&D-{run_id}] Step 1: Determining compute device...", "DEBUG")
        # Use override if provided, otherwise auto-detect
        compute_device = compute_device_override or get_compute_device()
        log(f"Using compute device: '{compute_device}'", "INFO")
        log(f"[T&D-{run_id}] Determined compute device: {compute_device}", "DEBUG")

        # --- Step 2: Prepare WAV Audio File (if necessary) ---
        log(f"[T&D-{run_id}] Step 2: Preparing audio file...", "DEBUG")
        # Generate a unique temp name based on original stem + UUID
        temp_wav_path = input_audio_path.parent / f"{input_audio_path.stem}__{run_id}_temp.wav"
        log(f"Potential temporary WAV path: {temp_wav_path}", "DEBUG")

        log(f"[T&D-{run_id}] Calling convert_to_wav utility...", "DEBUG")
        conversion_needed, wav_path_to_process = convert_to_wav(input_audio_path, temp_wav_path)
        if wav_path_to_process is None: # Check if conversion failed
             log(f"[T&D-{run_id}] convert_to_wav returned None, raising error.", "ERROR")
             raise RuntimeError(f"Failed to prepare/convert audio file: {input_audio_path.name}")
        log(f"[T&D-{run_id}] convert_to_wav finished. Path to process: {wav_path_to_process}, Conversion needed: {conversion_needed}", "DEBUG")
        log(f"Audio ready for processing at: {wav_path_to_process.name} (Conversion performed: {conversion_needed})", "INFO")


        # --- Step 3: Load AI Models ---
        log(f"[T&D-{run_id}] Step 3: Loading AI models...", "DEBUG")
        # Use default pipeline from model_loader if not overridden
        effective_pyannote_pipeline = pyannote_pipeline_name or DEFAULT_PYANNOTE_PIPELINE
        log(f"[T&D-{run_id}] Calling load_models with: model={whisper_model_size}, compute={compute_type}, pipeline={effective_pyannote_pipeline}, device={compute_device}", "DEBUG")
        whisper_model, diarization_pipeline = load_models(
            whisper_model_size=whisper_model_size,
            compute_type=compute_type,
            pyannote_pipeline_name=effective_pyannote_pipeline, # Pass effective name
            hf_token=hf_token,
            compute_device=compute_device # Pass the determined/overridden device
        )
        log(f"[T&D-{run_id}] load_models finished. Whisper loaded: {whisper_model is not None}, Pyannote loaded: {diarization_pipeline is not None}", "DEBUG")
        if not whisper_model or not diarization_pipeline:
            # Errors logged within load_models
            log(f"[T&D-{run_id}] Failed to load one or both models.", "ERROR")
            raise RuntimeError("Failed to load necessary AI models.")

        # --- Step 4: Run Transcription ---
        log(f"[T&D-{run_id}] Step 4: Running transcription...", "DEBUG")
        log(f"[T&D-{run_id}] Calling run_transcription with: lang={language}, words={word_timestamps_enabled}", "DEBUG")
        transcription_output = run_transcription(
            whisper_model=whisper_model,
            wav_path=wav_path_to_process,
            language=language,
            word_timestamps_enabled=word_timestamps_enabled
        )
        log(f"[T&D-{run_id}] run_transcription finished. Output is None: {transcription_output is None}", "DEBUG")
        if transcription_output is None:
            log(f"[T&D-{run_id}] Transcription step failed (returned None).", "ERROR")
            raise RuntimeError("Transcription step failed.")
        # Unpack the results
        transcript_segments, transcript_info = transcription_output
        log(f"[T&D-{run_id}] Transcription successful. Segments found: {len(transcript_segments) if transcript_segments else 0}. Info: {transcript_info}", "DEBUG")


        # --- Step 5: Run Diarization ---
        log(f"[T&D-{run_id}] Step 5: Running diarization...", "DEBUG")
        log(f"[T&D-{run_id}] Calling run_diarization with hints: num={num_speakers}, min={min_speakers}, max={max_speakers}", "DEBUG")
        diarization_result = run_diarization(
            diarization_pipeline=diarization_pipeline,
            wav_path=wav_path_to_process,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers
        )
        log(f"[T&D-{run_id}] run_diarization finished. Result is None: {diarization_result is None}", "DEBUG")
        if diarization_result is not None:
            # Get unique speaker labels
            speaker_labels_list = diarization_result.labels()
            log(f"[T&D-{run_id}] Diarization successful. Found {len(speaker_labels_list)} unique speakers: {speaker_labels_list}", "DEBUG")
        else:
             log(f"[T&D-{run_id}] Diarization returned None (may be handled by merge).", "WARNING")


        # --- Step 6: Merge Results ---
        log(f"[T&D-{run_id}] Step 6: Merging results...", "DEBUG")
        log(f"[T&D-{run_id}] Calling merge_results.", "DEBUG")
        final_result = merge_results(
            whisper_segments=transcript_segments,
            diarization_result=diarization_result
        )
        log(f"[T&D-{run_id}] merge_results finished. Result is None: {final_result is None}", "DEBUG")
        if final_result is None:
            # Error should be logged within merge_results
            log(f"[T&D-{run_id}] Merging transcription and diarization results failed (merge_results returned None).", "ERROR")
            raise RuntimeError("Merging transcription and diarization results failed.")
        log(f"[T&D-{run_id}] Merge successful. Final segment count: {len(final_result)}", "DEBUG")

        total_time = round(time.time() - start_process_time, 2)
        log(f"Transcription and diarization process completed successfully for {input_audio_path.name} in {total_time}s.", "SUCCESS")
        log(f"[T&D-{run_id}] End of try block reached successfully.", "DEBUG")

    except Exception as e:
         # Log the overarching error encountered during the main workflow
         log(f"Critical error during transcription/diarization orchestration for '{input_audio_path.name}': {e}", "CRITICAL")
         log(f"[T&D-{run_id}] Exception caught in main try block: {e.__class__.__name__}", "ERROR")
         log(traceback.format_exc(), "DEBUG") # Log detailed traceback for this top-level error
         final_result = None # Ensure failure state

    finally:
        # --- Step 7: Cleanup ---
        log(f"[T&D-{run_id}] Entering finally block...", "DEBUG")

        # --- Cleanup Temporary File ---
        log(f"[T&D-{run_id}] Preparing to call _cleanup_temp_file helper. Conversion needed: {conversion_needed}", "DEBUG")
        path_to_clean = temp_wav_path if conversion_needed else None
        log(f"[T&D-{run_id}] Path passed to cleanup helper: {path_to_clean}", "DEBUG")
        _cleanup_temp_file(path_to_clean, input_audio_path)
        log(f"[T&D-{run_id}] Returned from _cleanup_temp_file helper.", "DEBUG")


        # --- Optional: Explicitly clean up models ---
        log(f"[T&D-{run_id}] Preparing model cleanup (scope exit)...", "DEBUG")
        if whisper_model:
             log(f"[T&D-{run_id}] Deleting whisper_model object...", "DEBUG")
             try:
                 del whisper_model
                 log("Whisper model unloaded (scope exit).", "DEBUG")
             except Exception as del_e:
                 log(f"[T&D-{run_id}] Exception during whisper_model deletion: {del_e}", "WARNING")
        else:
             log(f"[T&D-{run_id}] whisper_model was None, skipping delete.", "DEBUG")

        if diarization_pipeline:
             log(f"[T&D-{run_id}] Deleting diarization_pipeline object...", "DEBUG")
             try:
                 del diarization_pipeline
                 log("Pyannote pipeline unloaded (scope exit).", "DEBUG")
             except Exception as del_e:
                 log(f"[T&D-{run_id}] Exception during diarization_pipeline deletion: {del_e}", "WARNING")
        else:
             log(f"[T&D-{run_id}] diarization_pipeline was None, skipping delete.", "DEBUG")


        # --- Optional: Clear GPU Cache ---
        # Check if compute_device was defined and is cuda/mps before clearing cache
        log(f"[T&D-{run_id}] Checking if GPU cache clear is needed for device: {compute_device}", "DEBUG")
        gpu_clear_needed = compute_device in ['cuda', 'mps']
        if gpu_clear_needed:
             log(f"[T&D-{run_id}] Attempting to clear GPU cache for device {compute_device}...", "DEBUG")
             try:
                if compute_device == 'cuda':
                    torch.cuda.empty_cache()
                    log("Cleared CUDA cache.", "DEBUG")
                elif compute_device == 'mps':
                    log("MPS device detected. Cache clearing relies on object deletion/GC.", "DEBUG")
             except NameError: # Should not happen if import torch is added
                 log("Could not clear GPU cache: 'torch' not imported.", "WARNING")
             except Exception as cache_err:
                 log(f"Could not clear GPU cache for {compute_device}: {cache_err}", "WARNING")
                 log(traceback.format_exc(), "DEBUG") # Add traceback for cache errors too
        else:
             log(f"[T&D-{run_id}] GPU cache clear not needed for device: {compute_device}", "DEBUG")

        log(f"[T&D-{run_id}] Exiting finally block.", "DEBUG")
        # ======== LOG ADDED HERE: ========
        log(f"[T&D-{run_id}] *** FINALLY BLOCK COMPLETED ***", "CRITICAL")
        # ==================================

    # --- Final Return Statement ---
    log(f"[T&D-{run_id}] Preparing to return final_result. Is None: {final_result is None}", "DEBUG")
    if final_result is not None:
         log(f"[T&D-{run_id}] Returning {len(final_result)} segments.", "DEBUG")
    else:
         log(f"[T&D-{run_id}] Returning None due to previous errors.", "DEBUG")

    return final_result # <-- THE ACTUAL RETURN


# --- Example Usage Block ---
if __name__ == "__main__":
    # Imports moved inside block to avoid cluttering global scope if not running as main
    import time
    import json
    import logging
    from pathlib import Path # Ensure Path is available here

    print("-" * 40)
    print("--- Testing Transcriber Orchestrator (Refactored) ---")
    print("-" * 40)

    # --- Determine Project Root (Robust way) ---
    try:
        current_path = Path(__file__).resolve()
        project_root = current_path.parent.parent.parent # Assumes src/core/transcriber.py
        if not (project_root / 'requirements.txt').exists():
             # Fallback if structure is different
             project_root = Path.cwd()
             print(f"⚠️ WARNING: Could not reliably determine project root. Using CWD: {project_root}")
        else:
             PROJECT_ROOT = project_root
             print(f"Project Root detected: {PROJECT_ROOT}")
    except NameError: # __file__ might not be defined
        PROJECT_ROOT = Path.cwd()
        print(f"⚠️ WARNING: Could not use __file__, using CWD as Project Root: {PROJECT_ROOT}")


    # --- Test Configuration ---
    # Define potential locations for test audio
    test_audio_locations = [
        PROJECT_ROOT / "audio" / "sample.mp3", # Check default first
        PROJECT_ROOT / "audio_samples" / "test_audio_stereo.wav",
        PROJECT_ROOT / "audio_samples" / "test_audio_mono.mp3",
    ]
    test_audio = None
    for loc in test_audio_locations:
        if loc.is_file():
            test_audio = loc
            break

    test_model = "tiny"       # Faster testing model
    test_compute = "int8"     # Efficient compute type
    test_lang = None          # Auto-detect language
    test_word_timestamps = True # Test with word timestamps enabled
    test_hf_token = os.environ.get("HUGGING_FACE_TOKEN") # Use the same logic as the main function

    # --- Pre-Checks ---
    if not test_audio:
        print(f"❌ CRITICAL: Test audio file not found in expected locations:")
        for loc in test_audio_locations: print(f"   - {loc}")
        print("   Please adjust the 'test_audio_locations' variable or add a sample file.")
    else:
        print(f"Using test audio: {test_audio}")
        # Check for Hugging Face Token (needed for default Pyannote model)
        if not test_hf_token:
            print("⚠️ WARNING: HUGGING_FACE_TOKEN environment variable not set.")
            print("   Diarization using the default Pyannote model will likely fail.")
            print("   Ensure you have accepted the model terms on Hugging Face.")

        # --- Setup Logging ---
        # Ensure logger is setup for test runs if not already done globally
        try:
            # Minimal setup if global setup didn't happen
            if not logging.getLogger('TranscriberApp').hasHandlers():
                setup_logging(level=logging.DEBUG)
                print("Test-specific logger setup complete (DEBUG level).")
            else:
                 print(f"Logger already configured. Current level: {logging.getLevelName(logging.getLogger('TranscriberApp').level)}")
        except Exception as log_setup_err:
            print(f"Error setting up logging for test: {log_setup_err}")


        # --- Run Test ---
        print("\n--- Running Test ---")
        print(f"Input: {test_audio.name}")
        print(f"Model: {test_model}/{test_compute}")
        print(f"Lang: {test_lang or 'Auto'}")
        print(f"Word Timestamps: {test_word_timestamps}")
        print(f"HF Token Provided: {'Yes' if test_hf_token else 'No'}")
        print("-" * 20)

        start_run_time = time.time()
        results = transcribe_and_diarize(
            input_audio_path=test_audio,
            whisper_model_size=test_model,
            compute_type=test_compute,
            language=test_lang,
            hf_token=test_hf_token, # Pass token found via os.environ
            word_timestamps_enabled=test_word_timestamps
        )
        end_run_time = time.time()
        print("-" * 20)
        print(f"Processing finished in {end_run_time - start_run_time:.2f} seconds.")

        # --- Display & Save Results ---
        if results is not None: # Check if result is not None
            print("\n--- Results (First 5 Segments with Word Data if generated) ---")
            if not results: # Check if the list is empty
                 print("[No segments generated by transcription/merge]")
            else:
                for i, seg in enumerate(results[:5]):
                    # Basic timestamp formatting
                    start_min, start_sec = divmod(int(seg.get('start', 0)), 60)
                    end_min, end_sec = divmod(int(seg.get('end', 0)), 60)
                    start_ts = f"{start_min:02d}:{start_sec:02d}"
                    end_ts = f"{end_min:02d}:{end_sec:02d}"
                    print(f"[{start_ts}-{end_ts}] {seg.get('speaker', 'N/A')}: {seg.get('text', '')}")

                    # Print word data if available and not empty
                    words_data = seg.get('words', [])
                    if words_data:
                         word_preview = " ".join([
                             f"{w.get('word', '?')}({w.get('start', 0):.1f}-{w.get('end', 0):.1f})"
                             for w in words_data[:10]
                         ])
                         print(f"    Words: {word_preview}{'...' if len(words_data) > 10 else ''}")

                if len(results) > 5: print("...")
                print(f"\nTotal segments generated: {len(results)}")

                # --- Save results to JSON ---
                try:
                    output_dir = PROJECT_ROOT / "test_results"
                    output_dir.mkdir(exist_ok=True)
                    output_json_path = output_dir / f"{test_audio.stem}_transcript_{test_model}_refactored.json"

                    with open(output_json_path, "w", encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    print(f"\n✅ Results successfully saved to: {output_json_path}")
                except Exception as e:
                    # Use log function here too if setup correctly
                    log(f"Error saving results to JSON: {e}", "ERROR")
                    log(traceback.format_exc(), "DEBUG")
                    print(f"\n❌ Error saving results to JSON: {e}")
        else: # results is None
            print("\n--- Processing failed (transcribe_and_diarize returned None). Check logs above for errors. ---")

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)