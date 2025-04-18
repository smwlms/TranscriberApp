# File: src/core/whisper_transcribe.py

import time
import traceback
from pathlib import Path
from typing import Optional, List, Tuple

# --- Third-party library imports ---
try:
    from faster_whisper import WhisperModel
    # Import Segment and Word objects for type hinting
    from faster_whisper.transcribe import Segment as WhisperSegmentObject, Word as WhisperWordObject
except ImportError:
    raise ImportError("Error: faster-whisper is not installed. Please run 'pip install faster-whisper'.")

# --- Local Imports ---
from src.utils.log import log

# --- Public Function ---

def run_transcription(
    whisper_model: WhisperModel,
    wav_path: Path,
    language: Optional[str],
    word_timestamps_enabled: bool
    ) -> Optional[Tuple[List[WhisperSegmentObject], dict]]: # Return segments and info dict
    """
    Runs Whisper transcription on the provided WAV audio file.

    Args:
        whisper_model: The loaded FasterWhisper model instance.
        wav_path: Path object pointing to the WAV audio file.
        language: Optional language code (e.g., "en", "nl"). None for auto-detect.
        word_timestamps_enabled: Whether to compute word-level timestamps.

    Returns:
        A tuple containing:
        - A list of faster_whisper Segment objects if successful.
        - The info dictionary returned by whisper.
        Returns None if transcription fails.
    """
    if not isinstance(wav_path, Path) or not wav_path.is_file():
         log(f"Invalid or non-existent WAV path provided for transcription: {wav_path}", "ERROR")
         return None

    log(f"Starting transcription on '{wav_path.name}' (Lang: {language or 'Auto'}, Words: {word_timestamps_enabled})...", "INFO")
    try:
        start_time = time.time()
        # Transcribe the audio file using the provided model and settings
        # Ensure audio path is passed as a string
        segments_generator, info = whisper_model.transcribe(
            audio=str(wav_path),
            beam_size=5,                 # Standard beam size
            language=language,           # Explicitly pass language or None
            word_timestamps=word_timestamps_enabled # Pass the flag
            # Other potential options:
            # vad_filter=True,           # Enable Voice Activity Detection filtering
            # initial_prompt="...",      # Provide prompt for context/style
            # temperature=0.0,           # Control randomness (0=deterministic)
        )

        # Consume the generator to get the list of segment objects
        whisper_results: List[WhisperSegmentObject] = list(segments_generator)
        elapsed = round(time.time() - start_time, 2)

        # Log transcription results
        log(f"Transcription completed in {elapsed}s. Found {len(whisper_results)} segments.", "SUCCESS")
        # Ensure info object exists before accessing attributes
        if info:
            log(f"Detected language: {info.language} (Confidence: {info.language_probability:.2f})", "INFO")
        else:
            log("Transcription info object not returned by model.", "WARNING")

        # Log word count if timestamps enabled and results exist
        if word_timestamps_enabled and whisper_results:
            # Safely count words using getattr
            total_words = sum(len(getattr(s, 'words', [])) for s in whisper_results)
            log(f"Generated timestamps for {total_words} words.", "DEBUG")

        # Return both the list of segments and the info dictionary
        return whisper_results, info if info else {} # Return empty dict if info is None

    except Exception as e:
        log(f"Transcription step failed for '{wav_path.name}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None # Return None on failure