# src/transcriber.py

import os
import time
import json
import traceback
import platform
import uuid # Import uuid for unique temp filename generation
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple # Added Tuple hint

# --- Third-party library imports ---
try:
    from faster_whisper import WhisperModel
except ImportError as e:
    raise ImportError("Error: faster-whisper is not installed. Please run 'pip install faster-whisper'.") from e

try:
    import torch
    from pyannote.audio import Pipeline as PyannotePipeline
    # Import Annotation for type hinting diarization result
    from pyannote.core import Segment, Annotation
except ImportError as e:
    raise ImportError("Error: pyannote.audio or torch is not installed. Please run 'pip install pyannote.audio torch torchaudio'.") from e

# --- Local Imports ---
from src.utils.log import log
# Import the refactored audio conversion utility
from src.utils.audio_utils import convert_to_wav

# --- Constants ---
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_PYANNOTE_PIPELINE = "pyannote/speaker-diarization-3.1"

# --- Global cache for compute device ---
_compute_device_cache: Optional[str] = None

# --- Helper Function for Device Detection (CORRECTED FORMATTING) ---
def _get_compute_device() -> str:
    """Automatically detects and caches the optimal compute device (cuda > mps > cpu)."""
    global _compute_device_cache
    # Return cached value if already detected
    if _compute_device_cache is not None:
        return _compute_device_cache

    device = "cpu" # Default fallback
    try:
        if torch.cuda.is_available():
            device = "cuda"
            log("CUDA (NVIDIA GPU) detected. Using 'cuda'.", "INFO")
        elif platform.system() == "Darwin" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available() and torch.backends.mps.is_built():
            # Check specifically for Apple Silicon MPS support
            device = "mps"
            log("Apple MPS detected and available. Using 'mps'.", "INFO")
        else:
            # If no GPU detected or MPS not available/built
            log("No CUDA or available MPS GPU detected. Using 'cpu'.", "INFO")
            # device remains "cpu"
    except Exception as e:
        # Catch potential errors during detection (e.g., library issues)
        log(f"Error during compute device detection: {e}. Falling back to 'cpu'.", "WARNING")
        device = "cpu" # Ensure fallback on error

    # Cache and return the determined device
    _compute_device_cache = device
    return device

# --- Internal Helper Functions for Transcription and Diarization ---

def _load_models(
    whisper_model_size: str,
    compute_type: str,
    pyannote_pipeline_name: str,
    hf_token: Optional[str],
    compute_device: str
    ) -> Tuple[Optional[WhisperModel], Optional[PyannotePipeline]]:
    """Loads Whisper and Pyannote models onto the specified device."""
    whisper_model = None
    diarization_pipeline = None
    log(f"Attempting to load models (Whisper: {whisper_model_size}, Pyannote: {pyannote_pipeline_name}) on device '{compute_device}'...", "INFO")

    try:
        # Determine torch device object for Pyannote
        pyannote_torch_device = torch.device(compute_device) # Use the determined device string

        # Load FasterWhisper model
        log(f"Loading Whisper model '{whisper_model_size}' (Compute: {compute_type})...", "DEBUG")
        # Use 'auto' device argument for Whisper when MPS is detected for best compatibility
        whisper_device_arg = "auto" if compute_device == "mps" else compute_device
        whisper_model = WhisperModel(whisper_model_size, device=whisper_device_arg, compute_type=compute_type)
        log("Whisper model loaded successfully.", "SUCCESS")

        # Load Pyannote pipeline
        log(f"Loading Pyannote pipeline '{pyannote_pipeline_name}'...", "DEBUG")
        auth_token_arg = {"use_auth_token": hf_token} if hf_token else {}
        if not hf_token: log("Hugging Face token not provided. Pyannote model loading might fail if authentication is required.", "WARNING")
        diarization_pipeline = PyannotePipeline.from_pretrained(pyannote_pipeline_name, **auth_token_arg)
        diarization_pipeline.to(pyannote_torch_device) # Move pipeline to target device
        log(f"Pyannote pipeline loaded successfully onto device '{pyannote_torch_device}'.", "SUCCESS")

        return whisper_model, diarization_pipeline

    except Exception as e:
        # Log loading errors clearly
        failed_model = whisper_model_size if whisper_model is None else pyannote_pipeline_name
        log(f"Error loading AI model '{failed_model}': {e}", "CRITICAL")
        log("Check model names, Hugging Face token/terms, network connection, and system requirements (RAM/VRAM).", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log full traceback for detailed debugging
        return None, None # Return None tuple on failure


def _run_transcription(
    whisper_model: WhisperModel,
    wav_path: Path,
    language: Optional[str]
    ) -> Optional[List[Any]]:
    """Runs Whisper transcription on the provided WAV audio file."""
    log(f"Starting transcription on '{wav_path.name}'...", "INFO")
    try:
        start_time = time.time()
        # Transcribe the audio file
        segments_generator, info = whisper_model.transcribe(
            str(wav_path),
            beam_size=5,            # Standard beam size for decoding
            language=language,      # None for auto-detect, or specify e.g., "en"
            word_timestamps=False   # Set True for word-level detail (slower)
        )
        # Collect all segments from the generator into a list
        whisper_results = list(segments_generator)
        elapsed = round(time.time() - start_time, 2)

        # Log transcription results
        log(f"Transcription completed in {elapsed}s. Found {len(whisper_results)} segments.", "SUCCESS")
        log(f"Detected language: {info.language} (Confidence: {info.language_probability:.2f})", "INFO")
        return whisper_results

    except Exception as e:
        log(f"Transcription step failed: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None # Return None on failure


def _run_diarization(
    diarization_pipeline: PyannotePipeline,
    wav_path: Path
    ) -> Optional[Annotation]:
    """Runs Pyannote speaker diarization on the WAV audio file."""
    log(f"Starting speaker diarization on '{wav_path.name}'...", "INFO")
    try:
        start_time = time.time()
        # Apply the diarization pipeline to the audio file
        diarization_result: Annotation = diarization_pipeline(str(wav_path))
        elapsed = round(time.time() - start_time, 2)

        # Log diarization results
        if diarization_result:
             num_speakers = len(diarization_result.labels())
             log(f"Diarization completed in {elapsed}s. Detected {num_speakers} speakers.", "SUCCESS")
             if num_speakers > 0: log(f"Detected speaker labels: {diarization_result.labels()}", "DEBUG")
        else:
             log("Diarization completed but produced no result (empty annotation).", "WARNING")

        return diarization_result

    except Exception as e:
        log(f"Speaker diarization step failed: {e}", "ERROR")
        log("Check Hugging Face token validity, model terms acceptance, and input audio integrity.", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None # Return None on failure


def _merge_results(
    whisper_segments: List[Any], # Type from faster_whisper segment objects
    diarization_result: Optional[Annotation] # Result from Pyannote pipeline
    ) -> Optional[List[Dict[str, Any]]]:
    """
    Merges Whisper transcription segments with Pyannote diarization results
    by assigning a speaker label to each text segment.
    """
    final_merged_segments: List[Dict[str, Any]] = []
    log("Merging transcription and diarization results...", "INFO")

    if not diarization_result:
        log("Diarization result is missing. Assigning 'SPEAKER_UNKNOWN' to all segments.", "WARNING")
        # Fallback: If diarization failed or returned None, create segments with UNKNOWN speaker
        for segment_info in whisper_segments:
            final_merged_segments.append({
                "text": getattr(segment_info, 'text', '').strip(),
                "start": getattr(segment_info, 'start', 0.0),
                "end": getattr(segment_info, 'end', 0.0),
                "speaker": "SPEAKER_UNKNOWN" # Assign fallback speaker ID
            })
        return final_merged_segments

    try:
        # Iterate through each text segment identified by Whisper
        for i, segment_info in enumerate(whisper_segments):
            # Extract time and text from Whisper segment object safely
            segment_start = getattr(segment_info, 'start', 0.0)
            segment_end = getattr(segment_info, 'end', 0.0)
            segment_text = getattr(segment_info, 'text', '').strip()

            # Create a Pyannote Segment object representing the Whisper segment's time span
            whisper_segment_time = Segment(segment_start, segment_end)
            speaker_label = "SPEAKER_ERROR" # Default label if merging logic fails for a segment

            try:
                # Crop the diarization timeline to this specific segment's time range
                cropped_annotation: Annotation = diarization_result.crop(whisper_segment_time)

                # Check if any speaker was active during this segment according to Pyannote
                if not cropped_annotation or not cropped_annotation.labels():
                    speaker_label = "SPEAKER_UNKNOWN" # Assign if no speaker activity found
                    log(f"Segment {i+1} [{segment_start:.2f}-{segment_end:.2f}]: No speaker activity detected by Pyannote.", "DEBUG")
                else:
                    # Find the speaker label with the maximum duration within this segment
                    speaker_label = cropped_annotation.argmax()
                    log(f"Segment {i+1} [{segment_start:.2f}-{segment_end:.2f}] -> Assigned Speaker '{speaker_label}'.", "DEBUG")

            except Exception as merge_err:
                # Log errors during the crop/argmax process for a specific segment
                log(f"Error merging speaker for segment {i+1} [{segment_start:.2f}-{segment_end:.2f}]: {merge_err}", "WARNING")
                # Keep the 'SPEAKER_ERROR' label assigned above

            # Append the merged segment information (text, times, speaker) to the final list
            final_merged_segments.append({
                "text": segment_text,
                "start": segment_start,
                "end": segment_end,
                "speaker": speaker_label # Assigned speaker ID (e.g., "SPEAKER_00", "SPEAKER_UNKNOWN", "SPEAKER_ERROR")
            })

        log("Merge of transcription and diarization results completed successfully.", "SUCCESS")
        return final_merged_segments

    except Exception as e:
        # Catch unexpected errors during the overall merging loop
        log(f"Merging results failed overall: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None # Return None if the merge process fails


def _cleanup_temp_file(temp_file_path: Optional[Path], original_input_path: Path):
    """Removes the temporary WAV file if it exists and is different from the original input."""
    if temp_file_path and temp_file_path.exists() and temp_file_path.resolve() != original_input_path.resolve():
        log(f"Attempting to remove temporary file: {temp_file_path.name}", "DEBUG")
        try:
            temp_file_path.unlink()
            log(f"Temporary WAV file removed successfully.", "INFO")
        except OSError as e:
            # Log failure to remove, but don't treat as a critical error preventing results
            log(f"Failed to remove temporary WAV file '{temp_file_path.name}': {e}", "WARNING")


# --- Main Public Function ---

def transcribe_and_diarize(
    input_audio_path: Path,
    whisper_model_size: str = DEFAULT_WHISPER_MODEL,
    compute_type: str = DEFAULT_COMPUTE_TYPE,
    language: Optional[str] = None,
    hf_token: Optional[str] = os.environ.get("HUGGING_FACE_TOKEN"), # Default to env var
    pyannote_pipeline_name: str = DEFAULT_PYANNOTE_PIPELINE,
) -> Optional[List[Dict[str, Any]]]:
    """
    Performs transcription and diarization using a structured workflow with helper functions.

    Args:
        input_audio_path: Path to the input audio file.
        whisper_model_size: Size of the FasterWhisper model.
        compute_type: Compute type for Whisper.
        language: Optional language code for transcription (None for auto-detect).
        hf_token: Hugging Face API token for Pyannote model access.
        pyannote_pipeline_name: Name of the Pyannote pipeline model.

    Returns:
        A list of merged segment dictionaries (with 'text', 'start', 'end', 'speaker'),
        or None if a critical error occurs.
    """
    log(f"Starting transcription & diarization process for: {input_audio_path.name}", "INFO")
    if not input_audio_path.is_file():
        log(f"Input audio file not found: {input_audio_path}", "ERROR")
        return None

    # Initialize variables
    temp_wav_path: Optional[Path] = None
    whisper_model: Optional[WhisperModel] = None
    diarization_pipeline: Optional[PyannotePipeline] = None
    final_result: Optional[List[Dict[str, Any]]] = None

    try:
        # Step 1: Determine Compute Device
        compute_device = _get_compute_device()
        if not compute_device: # Should not happen based on _get_compute_device logic
             raise RuntimeError("Could not determine compute device.")

        # Step 2: Prepare WAV Audio File
        temp_wav_path = input_audio_path.parent / f"{input_audio_path.stem}__{uuid.uuid4().hex[:8]}_temp.wav"
        log(f"Using temporary WAV path: {temp_wav_path}", "DEBUG")
        if not convert_to_wav(input_audio_path, temp_wav_path):
            raise RuntimeError("Failed to prepare WAV audio file for processing.")
        wav_path_to_process = temp_wav_path if input_audio_path.suffix.lower() != ".wav" else input_audio_path
        log(f"Processing audio from: {wav_path_to_process.name}", "DEBUG")

        # Step 3: Load AI Models
        whisper_model, diarization_pipeline = _load_models(
            whisper_model_size, compute_type, pyannote_pipeline_name, hf_token, compute_device
        )
        if not whisper_model or not diarization_pipeline:
            raise RuntimeError("Failed to load necessary AI models.")

        # Step 4: Run Transcription
        transcript_segments = _run_transcription(whisper_model, wav_path_to_process, language)
        if transcript_segments is None:
            raise RuntimeError("Transcription step failed.")

        # Step 5: Run Diarization
        diarization_result = _run_diarization(diarization_pipeline, wav_path_to_process)
        # Diarization failure (result=None) is handled within the merge step

        # Step 6: Merge Results
        final_result = _merge_results(transcript_segments, diarization_result)
        if final_result is None:
            raise RuntimeError("Merging transcription and diarization results failed.")

        log(f"Transcription and diarization process completed successfully for {input_audio_path.name}.", "SUCCESS")

    except Exception as e:
         # Log the overarching error encountered during the main workflow
         log(f"Critical error during transcription/diarization for '{input_audio_path.name}': {e}", "ERROR")
         # Detailed traceback should have been logged by the failing helper function
         final_result = None # Ensure failure state

    finally:
        # Step 7: Cleanup Temporary File (always attempt)
        _cleanup_temp_file(temp_wav_path, input_audio_path)

    return final_result


# Example usage block (remains the same for testing the public function)
if __name__ == "__main__":
    from src.utils.log import setup_logging # Need setup for the test
    import logging
    print("-" * 40)
    print("--- Testing Transcriber with Diarization (Refactored) ---")
    print("-" * 40)
    try:
        from src.utils.config_schema import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = Path(__file__).resolve().parent.parent
    # --- Test Configuration ---
    test_audio = PROJECT_ROOT / "audio" / "sample.mp3" # !! ADJUST IF YOUR SAMPLE IS ELSEWHERE !!
    test_model = "small" # Use a smaller model for faster testing if needed
    test_compute = "int8"
    test_lang = None # Auto-detect language
    test_hf_token = os.environ.get("HUGGING_FACE_TOKEN")
    # --- Pre-Checks ---
    if not test_audio.is_file(): print(f"❌ Test audio file not found at '{test_audio}'. Adjust path in script.")
    else:
        if not test_hf_token: print("⚠️ WARNING: HUGGING_FACE_TOKEN env var not set. Diarization might fail.")
        # --- Setup & Run ---
        setup_logging(level=logging.DEBUG) # Show detailed logs for testing
        print("\n--- Running Test ---"); print(f"Input: {test_audio.name}"); print(f"Model: {test_model}/{test_compute}"); print(f"Lang: {test_lang or 'Auto'}"); print(f"Pipeline: {DEFAULT_PYANNOTE_PIPELINE}"); print(f"HF Token: {'Yes' if test_hf_token else 'No'}"); print("-" * 20)
        start_run_time = time.time()
        results = transcribe_and_diarize(input_audio_path=test_audio, whisper_model_size=test_model, compute_type=test_compute, language=test_lang, hf_token=test_hf_token)
        end_run_time = time.time(); print("-" * 20); print(f"Processing finished in {end_run_time - start_run_time:.2f} seconds.")
        # --- Display & Save Results ---
        if results:
            print("\n--- Results (First 10 Segments) ---")
            for i, seg in enumerate(results[:10]): start_ts = f"[{int(seg['start'] // 60):02d}:{int(seg['start'] % 60):02d}]"; end_ts = f"[{int(seg['end'] // 60):02d}:{int(seg['end'] % 60):02d}]"; print(f"{start_ts}-{end_ts} {seg['speaker']}: {seg['text']}")
            if len(results) > 10: print("...")
            print(f"\nTotal segments generated: {len(results)}")
            try:
                output_json_path = PROJECT_ROOT / "transcriber_test_output_refactored.json"
                with open(output_json_path, "w", encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print(f"\n✅ Results successfully saved to: {output_json_path}")
            except Exception as e:
                print(f"\n❌ Error saving results to JSON: {e}")
            except Exception as e: print(f"\n❌ Error saving results to JSON: {e}")
        else: print("\n--- Processing failed. Check logs above for errors. ---")
    print("-" * 40); print("--- Testing Complete ---"); print("-" * 40)