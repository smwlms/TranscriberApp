# File: src/core/merge.py

import traceback
from typing import List, Dict, Optional, Any

# --- Third-party library imports ---
try:
    # Import the specific types needed for clarity
    from pyannote.core import Segment as PyannoteSegment, Annotation
    from faster_whisper.transcribe import Segment as WhisperSegmentObject, Word as WhisperWordObject
except ImportError as e:
    raise ImportError(
        "Error: pyannote.core or faster_whisper types not found. "
        f"Ensure pyannote.audio and faster-whisper are installed. Original error: {e}"
    ) from e

# --- Local Imports ---
from src.utils.log import log

# --- Public Function ---

def merge_results(
    whisper_segments: List[WhisperSegmentObject], # Input is list of Whisper objects
    diarization_result: Optional[Annotation] # Input is Pyannote Annotation object
    ) -> Optional[List[Dict[str, Any]]]:
    """
    Merges Whisper transcription segments with Pyannote diarization results
    by assigning a speaker label to each text segment. Includes word-level
    timestamp data if available in the Whisper segments.

    Args:
        whisper_segments: A list of Segment objects from faster-whisper transcription.
        diarization_result: An Annotation object from pyannote.audio diarization, or None.

    Returns:
        A list of dictionaries, where each dictionary represents a merged segment
        containing 'text', 'start', 'end', 'speaker', and 'words' keys.
        Returns None if a critical error occurs during merging.
    """
    final_merged_segments: List[Dict[str, Any]] = []
    log("Merging transcription and diarization results...", "INFO")

    # --- Handle case where diarization failed or is missing ---
    if not diarization_result:
        log("Diarization result is missing or empty. Assigning 'SPEAKER_UNKNOWN' to all segments.", "WARNING")
        try:
            for i, segment_info in enumerate(whisper_segments):
                segment_data = {
                    # Use getattr for safety, though attributes should exist on WhisperSegmentObject
                    "text": getattr(segment_info, 'text', '').strip(),
                    "start": getattr(segment_info, 'start', 0.0),
                    "end": getattr(segment_info, 'end', 0.0),
                    "speaker": "SPEAKER_UNKNOWN" # Assign fallback speaker ID
                }
                # Add word data handling even in fallback
                words_list = []
                if hasattr(segment_info, 'words') and segment_info.words:
                    words_list = [
                        {"word": word.word.strip(), "start": word.start, "end": word.end, "score": getattr(word, 'probability', 0.0)} # Add score if available
                        for word in segment_info.words
                    ]
                segment_data["words"] = words_list
                final_merged_segments.append(segment_data)
            log("Fallback merge completed (using SPEAKER_UNKNOWN).", "SUCCESS")
            return final_merged_segments
        except Exception as fallback_err:
             log(f"Error during fallback merge (no diarization): {fallback_err}", "ERROR")
             log(traceback.format_exc(), "DEBUG")
             return None # Fail if even fallback merge has issues

    # --- Main merge logic when diarization result is available ---
    try:
        segment_count = len(whisper_segments)
        log(f"Processing {segment_count} Whisper segments against diarization results.", "DEBUG")
        # Iterate through each text segment identified by Whisper
        for i, segment_info in enumerate(whisper_segments):
            # Extract time and text from Whisper segment object safely
            segment_start = getattr(segment_info, 'start', 0.0)
            segment_end = getattr(segment_info, 'end', 0.0)
            segment_text = getattr(segment_info, 'text', '').strip()

            # Skip empty segments from Whisper if they occur
            if not segment_text:
                log(f"Skipping empty Whisper segment {i+1} [{segment_start:.2f}-{segment_end:.2f}].", "DEBUG")
                continue

            # Create a Pyannote Segment object representing the Whisper segment's time span
            whisper_segment_time = PyannoteSegment(segment_start, segment_end)

            # Use 'SPEAKER_?' as initial default, change based on findings
            speaker_label = "SPEAKER_MERGE_FAILED"

            try:
                # --- Find overlapping speaker turns ---
                # Get speaker turns from the annotation that overlap with the whisper segment time
                overlapping_turns = diarization_result.crop(whisper_segment_time, mode='intersection')

                if not overlapping_turns or overlapping_turns.is_empty():
                    # If no speaker turn overlaps significantly, label as Unknown
                    speaker_label = "SPEAKER_UNKNOWN"
                    log(f"Segment {i+1}/{segment_count} [{segment_start:.2f}-{segment_end:.2f}]: No overlapping speaker turn found by Pyannote.", "DEBUG")
                else:
                    # --- Determine dominant speaker ---
                    # Find the speaker label with the maximum duration within this cropped annotation
                    # `argmax()` returns the label associated with the longest duration segment/track
                    # within the provided annotation (which is already cropped).
                    dominant_speaker = overlapping_turns.argmax()
                    speaker_label = dominant_speaker
                    log(f"Segment {i+1}/{segment_count} [{segment_start:.2f}-{segment_end:.2f}] -> Assigned Speaker '{speaker_label}'.", "DEBUG")

            except Exception as merge_err:
                # Log errors during the crop/argmax process for a specific segment
                log(f"Error merging speaker for segment {i+1}/{segment_count} [{segment_start:.2f}-{segment_end:.2f}]: {merge_err}", "WARNING")
                # Keep the 'SPEAKER_MERGE_FAILED' label assigned above

            # --- Create base segment data dictionary ---
            segment_data = {
                "text": segment_text,
                "start": segment_start,
                "end": segment_end,
                "speaker": speaker_label
            }

            # --- Add word data if available ---
            words_list = []
            # Check if the segment object has a 'words' attribute and if it's not None/empty
            if hasattr(segment_info, 'words') and segment_info.words:
                # Format the word data into the structure expected by the frontend/downstream
                words_list = [
                    {"word": word.word.strip(), "start": word.start, "end": word.end, "score": getattr(word, 'probability', 0.0)}
                    for word in segment_info.words if word.word is not None # Basic sanity check
                ]
            # If no words attribute or it's empty, words_list remains empty []
            segment_data["words"] = words_list
            # ------------------------------------

            # Append the structured segment information to the final list
            final_merged_segments.append(segment_data)

        log(f"Merge of {len(final_merged_segments)} segments completed successfully.", "SUCCESS")
        return final_merged_segments

    except Exception as e:
        # Catch unexpected errors during the overall merging loop
        log(f"Merging results failed overall: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        return None # Return None if the merge process fails critically