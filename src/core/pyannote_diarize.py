# File: src/core/pyannote_diarize.py

import time
import traceback
from pathlib import Path
from typing import Optional

# --- Third-party library imports ---
try:
    import torch # Needed for device context potentially, though pipeline handles it
    from pyannote.audio import Pipeline as PyannotePipeline
    from pyannote.core import Annotation
except ImportError:
    raise ImportError("Error: pyannote.audio or torch is not installed. Please run 'pip install pyannote.audio torch torchaudio'.")

# --- Local Imports ---
from src.utils.log import log

# --- Public Function ---

def run_diarization(
    diarization_pipeline: PyannotePipeline,
    wav_path: Path,
    num_speakers: Optional[int] = None, # Add option to provide speaker count hint
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None
    ) -> Optional[Annotation]:
    """
    Runs Pyannote speaker diarization on the WAV audio file.

    Args:
        diarization_pipeline: The loaded Pyannote pipeline instance.
        wav_path: Path object pointing to the WAV audio file.
        num_speakers: Optional fixed number of speakers to detect.
        min_speakers: Optional minimum number of speakers.
        max_speakers: Optional maximum number of speakers.

    Returns:
        A pyannote.core.Annotation object containing speaker segments, or None if diarization fails.
    """
    if not isinstance(wav_path, Path) or not wav_path.is_file():
         log(f"Invalid or non-existent WAV path provided for diarization: {wav_path}", "ERROR")
         return None

    log(f"Starting speaker diarization on '{wav_path.name}'...", "INFO")
    if num_speakers or min_speakers or max_speakers:
        log(f"  Hints: num_speakers={num_speakers}, min_speakers={min_speakers}, max_speakers={max_speakers}", "DEBUG")

    try:
        start_time = time.time()
        # Prepare arguments for the pipeline call, only including hints if provided
        diarization_kwargs = {}
        if num_speakers is not None: diarization_kwargs['num_speakers'] = num_speakers
        if min_speakers is not None: diarization_kwargs['min_speakers'] = min_speakers
        if max_speakers is not None: diarization_kwargs['max_speakers'] = max_speakers

        # Apply the diarization pipeline to the audio file path (as string)
        # The pipeline should handle loading the audio internally
        diarization_result: Annotation = diarization_pipeline(str(wav_path), **diarization_kwargs)
        elapsed = round(time.time() - start_time, 2)

        # Log diarization results
        if diarization_result:
             # Use .labels() method to get unique speaker identifiers found
             detected_speakers = diarization_result.labels()
             num_unique_speakers = len(detected_speakers)
             log(f"Diarization completed in {elapsed}s. Detected {num_unique_speakers} unique speakers.", "SUCCESS")
             if num_unique_speakers > 0:
                 log(f"Detected speaker labels: {sorted(list(detected_speakers))}", "DEBUG")
             # You could add more detailed stats here, e.g., total speech time per speaker
        else:
             # This case might happen if the audio is silent or very short
             log("Diarization completed but produced no result (empty annotation). Input might be silent?", "WARNING")

        return diarization_result

    except Exception as e:
        log(f"Speaker diarization step failed for '{wav_path.name}': {e}", "ERROR")
        # Add specific hints based on common pyannote errors if possible
        if "accept the license agreement" in str(e) or "User Access Token" in str(e):
             log("Hint: Ensure you have accepted the model's license on Hugging Face and provided a valid HF Token.", "ERROR")
        else:
            log("Check Hugging Face token validity, model terms acceptance, network connection, and input audio integrity.", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None # Return None on failure