# File: src/transcriber.py (Refactored Orchestrator)

import os
import uuid # Import uuid for unique temp filename generation
import traceback
import torch # <-- IMPORT TOEGEVOEGD
import time # Import time for timing block below
import json # Import json for testing block below
import logging # Import logging for testing block below
from pathlib import Path
from typing import List, Dict, Optional, Any

# --- Local Imports ---
# Utilities
from src.utils.log import log, setup_logging # Make setup_logging available for testing block
from src.utils.audio_utils import convert_to_wav
# Core processing modules
from src.core.model_loader import get_compute_device, load_models
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
    # Check if a temp path was actually created and exists
    if temp_file_path and temp_file_path.is_file():
        # Ensure we don't delete the original if it was already a WAV
        if temp_file_path.resolve() != original_input_path.resolve():
            log(f"Attempting to remove temporary file: {temp_file_path.name}", "DEBUG")
            try:
                temp_file_path.unlink()
                log(f"Temporary WAV file removed successfully.", "INFO")
            except OSError as e:
                # Log failure to remove, but don't treat as a critical error
                log(f"Failed to remove temporary WAV file '{temp_file_path.name}': {e}", "WARNING")
        else:
            log(f"Skipping removal of temporary file as it's the same as the input: {temp_file_path.name}", "DEBUG")
    elif temp_file_path:
        log(f"Temporary file path '{temp_file_path}' provided but file does not exist. No cleanup needed.", "DEBUG")


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
        input_audio_path: Path to the input audio file.
        whisper_model_size: Size of the FasterWhisper model (e.g., "tiny").
        compute_type: Compute type for Whisper (e.g., "int8").
        language: Optional language code for transcription (None for auto-detect).
        hf_token: Optional Hugging Face API token (defaults to env var).
        pyannote_pipeline_name: Optional Pyannote pipeline name (defaults handled in loader).
        word_timestamps_enabled: Set to True to generate word-level timestamps.
        num_speakers: Optional fixed number of speakers hint for diarization.
        min_speakers: Optional minimum number of speakers hint.
        max_speakers: Optional maximum number of speakers hint.
        compute_device_override: Optionally force "cuda", "mps", or "cpu".

    Returns:
        A list of merged segment dictionaries (with 'text', 'start', 'end', 'speaker', 'words'),
        or None if a critical error occurs during the process.
    """
    log(f"Starting transcription & diarization process for: {input_audio_path.name}", "INFO")
    start_process_time = time.time() # For overall timing

    if not isinstance(input_audio_path, Path) or not input_audio_path.is_file():
        log(f"Input audio file not found or invalid path: {input_audio_path}", "CRITICAL")
        return None

    # Initialize variables
    temp_wav_path: Optional[Path] = None
    whisper_model = None # Explicitly define to ensure cleanup scope
    diarization_pipeline = None # Explicitly define
    final_result: Optional[List[Dict[str, Any]]] = None
    conversion_needed = False # Track if conversion happened for cleanup logic

    try:
        # Step 1: Determine Compute Device
        # Use override if provided, otherwise auto-detect
        compute_device = compute_device_override or get_compute_device()
        log(f"Using compute device: '{compute_device}'", "INFO")

        # Step 2: Prepare WAV Audio File (if necessary)
        # Generate a unique temp name based on original stem + UUID
        temp_wav_path = input_audio_path.parent / f"{input_audio_path.stem}__{uuid.uuid4().hex[:8]}_temp.wav"
        log(f"Potential temporary WAV path: {temp_wav_path}", "DEBUG")

        # Use the conversion utility - it handles if conversion is needed
        conversion_needed, wav_path_to_process = convert_to_wav(input_audio_path, temp_wav_path)
        if wav_path_to_process is None: # Check if conversion failed
             raise RuntimeError(f"Failed to prepare/convert audio file: {input_audio_path.name}")

        log(f"Audio ready for processing at: {wav_path_to_process.name} (Conversion performed: {conversion_needed})", "INFO")


        # Step 3: Load AI Models using the specific loader function
        # Pass the determined compute device
        whisper_model, diarization_pipeline = load_models(
            whisper_model_size=whisper_model_size,
            compute_type=compute_type,
            pyannote_pipeline_name=pyannote_pipeline_name, # Pass along override or None
            hf_token=hf_token,
            compute_device=compute_device # Pass the determined/overridden device
        )
        if not whisper_model or not diarization_pipeline:
            # Errors logged within load_models
            raise RuntimeError("Failed to load necessary AI models.")

        # Step 4: Run Transcription using the specific transcription function
        transcription_output = run_transcription(
            whisper_model=whisper_model,
            wav_path=wav_path_to_process,
            language=language,
            word_timestamps_enabled=word_timestamps_enabled
        )
        if transcription_output is None:
            raise RuntimeError("Transcription step failed.")
        # Unpack the results
        transcript_segments, transcript_info = transcription_output
        # Optionally use transcript_info downstream if needed (e.g., detected language)


        # Step 5: Run Diarization using the specific diarization function
        diarization_result = run_diarization(
            diarization_pipeline=diarization_pipeline,
            wav_path=wav_path_to_process,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers
        )
        # Diarization failure (result=None) is handled gracefully within the merge step

        # Step 6: Merge Results using the specific merge function
        final_result = merge_results(
            whisper_segments=transcript_segments,
            diarization_result=diarization_result
        )
        if final_result is None:
            raise RuntimeError("Merging transcription and diarization results failed.")

        total_time = round(time.time() - start_process_time, 2)
        log(f"Transcription and diarization process completed successfully for {input_audio_path.name} in {total_time}s.", "SUCCESS")

    except Exception as e:
         # Log the overarching error encountered during the main workflow
         log(f"Critical error during transcription/diarization orchestration for '{input_audio_path.name}': {e}", "CRITICAL")
         log(traceback.format_exc(), "DEBUG") # Log detailed traceback for this top-level error
         final_result = None # Ensure failure state

    finally:
        # Step 7: Cleanup Temporary File (always attempt using the internal helper)
        # Only pass the temp path if conversion was actually performed
        _cleanup_temp_file(temp_wav_path if conversion_needed else None, input_audio_path)

        # Optional: Explicitly clean up models to release GPU memory if needed,
        # though Python's garbage collection usually handles this when objects go out of scope.
        # Explicit cleanup can be useful in long-running services.
        if whisper_model:
             del whisper_model
             log("Whisper model unloaded (scope exit).", "DEBUG")
        if diarization_pipeline:
             del diarization_pipeline
             log("Pyannote pipeline unloaded (scope exit).", "DEBUG")
        # Check if compute_device was defined and is cuda before clearing cache
        if 'compute_device' in locals() and compute_device == 'cuda':
             try:
                 torch.cuda.empty_cache() # Requires 'import torch' at top level
                 log("Cleared CUDA cache.", "DEBUG")
             except NameError: # Should not happen if import torch is added
                 log("Could not clear CUDA cache: 'torch' not imported.", "WARNING")
             except Exception as cache_err:
                 log(f"Could not clear CUDA cache: {cache_err}", "WARNING")


    return final_result


# --- Example Usage Block (Adapted for Refactored Structure) ---
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
        project_root = current_path.parent # Start assuming src/
        # Look for a known marker file/directory up to 3 levels up
        for _ in range(3):
            if (project_root / 'requirements.txt').exists() or \
               (project_root / '.git').exists() or \
               (project_root / 'pyproject.toml').exists():
                break
            project_root = project_root.parent
        else: # If loop finished without break
             print("⚠️ WARNING: Could not reliably determine project root. Using script parent's parent.")
             PROJECT_ROOT = Path(__file__).resolve().parent.parent # Fallback
        # Final check
        if not project_root.exists():
             PROJECT_ROOT = Path.cwd()
             print(f"⚠️ WARNING: Determined project root '{project_root}' does not exist. Using CWD: {PROJECT_ROOT}")
        else:
             PROJECT_ROOT = project_root
             print(f"Project Root detected: {PROJECT_ROOT}")
    except NameError: # __file__ might not be defined (e.g. interactive)
        PROJECT_ROOT = Path.cwd()
        print(f"⚠️ WARNING: Could not use __file__, using current working directory as Project Root: {PROJECT_ROOT}")


    # --- Test Configuration ---
    # Define potential locations for test audio
    test_audio_locations = [
        PROJECT_ROOT / "audio_samples" / "test_audio_stereo.wav",
        PROJECT_ROOT / "audio_samples" / "test_audio_mono.mp3",
        PROJECT_ROOT / "audio" / "sample.mp3" # Original fallback
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
        # Configure logging level (e.g., DEBUG for detailed output, INFO for standard)
        setup_logging(level=logging.DEBUG)

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
            # Add diarization hints here if needed for testing:
            # num_speakers=2
        )
        end_run_time = time.time()
        print("-" * 20)
        print(f"Processing finished in {end_run_time - start_run_time:.2f} seconds.")

        # --- Display & Save Results ---
        if results:
            print("\n--- Results (First 5 Segments with Word Data if generated) ---")
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
                     # Format: word(start-end)
                     word_preview = " ".join([
                         f"{w.get('word', '?')}({w.get('start', 0):.1f}-{w.get('end', 0):.1f})"
                         for w in words_data[:10] # Limit preview length
                     ])
                     print(f"    Words: {word_preview}{'...' if len(words_data) > 10 else ''}")

            if len(results) > 5: print("...")
            print(f"\nTotal segments generated: {len(results)}")

            # --- Save results to JSON ---
            try:
                # Save in project root or a dedicated 'results' directory
                output_dir = PROJECT_ROOT / "test_results"
                output_dir.mkdir(exist_ok=True)
                # Include model name in output filename for clarity
                output_json_path = output_dir / f"{test_audio.stem}_transcript_{test_model}_refactored.json"

                with open(output_json_path, "w", encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print(f"\n✅ Results successfully saved to: {output_json_path}")
            except Exception as e:
                log(f"Error saving results to JSON: {e}", "ERROR")
                # Log traceback for saving error as well
                log(traceback.format_exc(), "DEBUG")
                print(f"\n❌ Error saving results to JSON: {e}")
        else:
            print("\n--- Processing failed. Check logs above for errors. ---")

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)