# src/speaker_mapping.py
# Removed unused json import
from typing import List, Dict, Any, Optional

# Assuming log utility is set up and functional
from src.utils.log import log

def apply_speaker_mapping(
    transcript_segments: List[Dict[str, Any]],
    final_speaker_mapping: Dict[str, Optional[str]]
    ) -> List[Dict[str, Any]]:
    """
    Applies final speaker names to transcript segments based on a provided mapping.

    Iterates through each segment, looks up the original speaker ID (e.g., "SPEAKER_00")
    in the `final_speaker_mapping`, and adds a 'speaker_name' key to the segment.
    If a valid name (non-empty string) is found in the map, it's used. Otherwise,
    the original speaker ID is used as a fallback value for 'speaker_name'.
    Handles segments missing the original 'speaker' key by assigning a placeholder name.

    Args:
        transcript_segments: A list of transcript segment dictionaries, each expected
                             to have at least a 'speaker' key.
        final_speaker_mapping: A dictionary mapping original speaker IDs to their
                               final assigned names (str) or None/empty string if no
                               name should be assigned.

    Returns:
        A new list of transcript segment dictionaries, each with the added 'speaker_name'
        key. Returns an empty list if the input `transcript_segments` is empty.
    """
    # Handle empty input list immediately and gracefully
    if not transcript_segments:
        log("Cannot apply speaker mapping: Input transcript segments list is empty.", "WARNING")
        return [] # Return an empty list

    log(f"Applying speaker mapping to {len(transcript_segments)} segments...", "INFO")
    # Log the provided mapping at DEBUG level for troubleshooting if needed
    log(f"Using mapping: {final_speaker_mapping}", "DEBUG")

    updated_segments = []
    missing_id_count = 0 # Count segments where original 'speaker' key was missing
    unmapped_count = 0   # Count segments where ID was present but no valid name was mapped
    mapped_count = 0     # Count segments where a name was successfully assigned from the map

    for segment in transcript_segments:
        # Work on a copy to avoid modifying the original input dictionaries in place
        updated_segment = segment.copy()
        original_speaker_id = updated_segment.get("speaker") # Get original ID (e.g., "SPEAKER_01")

        if not original_speaker_id:
            # Case 1: Original segment data is missing the 'speaker' key
            updated_segment["speaker_name"] = "SPEAKER_MISSING_ID" # Assign a fixed placeholder
            missing_id_count += 1
            # Improve warning log with segment context (start time)
            start_time = updated_segment.get('start', '?') # Get start time if available
            log(f"Segment starting around {start_time}s is missing the 'speaker' key. Assigning '{updated_segment['speaker_name']}'.", "WARNING")
        else:
            # Case 2: Original speaker ID exists, look it up in the final map provided
            # Use .get() to safely handle cases where an ID might not be in the map (defaults to None)
            assigned_name = final_speaker_mapping.get(original_speaker_id)

            # Check if a valid, non-empty string name was provided in the map for this ID
            if assigned_name and isinstance(assigned_name, str) and assigned_name.strip():
                # Case 2a: Valid name found - assign it (strip leading/trailing whitespace)
                updated_segment["speaker_name"] = assigned_name.strip()
                mapped_count += 1
            else:
                # Case 2b: No name in map OR name is None/empty/invalid - use original ID as fallback name
                updated_segment["speaker_name"] = original_speaker_id
                unmapped_count += 1
                # Log specifically if the ID *was* present in the map but the value was unusable
                if original_speaker_id in final_speaker_mapping:
                     log(f"No valid name assigned for '{original_speaker_id}', using ID as fallback name.", "DEBUG")
                # If ID wasn't in map, using fallback is expected, no specific log needed here.

        # Add the processed segment (always containing 'speaker_name') to the new list
        updated_segments.append(updated_segment)

    # Log a summary of the mapping process results for confirmation
    log(f"Speaker mapping complete. Results - Assigned names: {mapped_count}, Used original ID (unmapped/invalid): {unmapped_count}, Segments missing original ID: {missing_id_count}.", "SUCCESS")

    # Return the new list of segments with speaker names added
    return updated_segments


# Example usage block for testing the function directly (no changes needed)
if __name__ == "__main__":
    print("-" * 40)
    print("--- Testing Speaker Mapping Application ---")
    print("-" * 40)
    # Setup basic logging for the test run to see log messages
    try:
        # Dynamically import logger setup if possible
        from src.utils.log import setup_logging
        import logging
        setup_logging(level=logging.DEBUG) # Use DEBUG to see all logs from the function
    except ImportError:
        print("Could not import logger setup, test logs might be missing.")

    # Mock transcript data (simulating output from transcribe_and_diarize)
    mock_transcript = [
        {"start": 0.5, "end": 2.1, "speaker": "SPEAKER_00", "text": "Hello there."},
        {"start": 2.5, "end": 4.8, "speaker": "SPEAKER_01", "text": "General Kenobi!"},
        {"start": 5.1, "end": 7.2, "speaker": "SPEAKER_00", "text": "You are a bold one."},
        {"start": 7.5, "end": 9.9, "speaker": "SPEAKER_UNKNOWN", "text": "(Sound of lightsaber)"},
        {"start": 10.1, "end": 11.5, "speaker": "SPEAKER_01", "text": "Kill him!"},
        {"start": 11.7, "end": 12.5, "text": "Another segment."}, # Segment missing speaker ID
    ]

    # Mock final mapping (simulating input from user review via API)
    mock_mapping = {
        "SPEAKER_00": "Obi-Wan Kenobi",
        "SPEAKER_01": " General Grievous ", # Test stripping whitespace
        "SPEAKER_UNKNOWN": None, # Explicitly no name for this ID
        "SPEAKER_EXTRA": "This ID is not in transcript" # Extra mapping, should be ignored
    }

    print("\nInput Transcript Segments:")
    for seg in mock_transcript: print(seg)
    print(f"\nInput Speaker Mapping: {mock_mapping}")

    # Apply the mapping
    print("\nApplying mapping...")
    result_segments = apply_speaker_mapping(mock_transcript, mock_mapping)

    print("\nOutput Transcript Segments with 'speaker_name':")
    if result_segments:
        for seg in result_segments: print(seg)
    else:
        # Should not happen with non-empty input unless there's an unexpected error
        print("Function returned empty list or None.")

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)