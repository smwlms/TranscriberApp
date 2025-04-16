# File: src/speaker_name_detector.py

import json
import traceback
from pathlib import Path
# Updated type hints for new structure
from typing import List, Dict, Optional, Tuple, Union, Any

# Import utilities
from src.utils.log import log
# Use the centralized LLM runner which handles model selection and fallback
from src.utils.llm import run_llm

# Constants
CONTEXT_WINDOW = 2 # Number of segments before/after a potential ID line to include in prompt

# --- Helper Functions ---

# *** MODIFICATION 1: Update prompt instructions and example output format ***
def build_name_detection_prompt(
    transcript_segments: List[Dict[str, Any]],
    relevant_indices: List[int]
    ) -> Tuple[str, Dict[int, str]]:
    """
    Builds the LLM prompt for speaker name detection, including context
    around potentially relevant lines identified earlier.
    Now asks for reasoning indices.

    Args:
        transcript_segments: The list of all transcript segments.
        relevant_indices: A list of indices identified as potentially containing
                          name introductions or mentions.

    Returns:
        A tuple containing:
        - The formatted prompt string for the LLM.
        - A dictionary mapping the 'triggering' line index to the text snippet
          provided as context around that line.
    """
    prompt_lines = []
    context_snippets: Dict[int, str] = {} # Store context keyed by triggering index

    # --- Prompt Instructions ---
    prompt_lines.append("Analyze the following conversation transcript excerpts to identify speaker names introduced during the conversation.")
    prompt_lines.append("Focus ONLY on explicit introductions (e.g., 'My name is...', 'I am...', 'Call me...') or direct address (e.g., 'Hello [Name], this is...').")
    prompt_lines.append("Look for patterns where a speaker ID (e.g., SPEAKER_01) states their name or is addressed by name near one of their segments.")
    prompt_lines.append("For each speaker ID where a name is confidently identified from the provided context, state the speaker ID, the detected name, and a list of the numeric line indices (from the 'Context around Line Index...' blocks below) that provide the primary evidence for that name.")
    prompt_lines.append("If no clear name identification is found for a specific speaker ID *within these excerpts*, the name should be null and the reasoning_indices list empty.")
    prompt_lines.append("\nFormat the output STRICTLY as a single JSON object mapping speaker IDs found in the excerpts to an object containing the detected 'name' (string or null) and 'reasoning_indices' (a list of integers).")
    prompt_lines.append("Example Output: {\"SPEAKER_00\": {\"name\": \"Alice B.\", \"reasoning_indices\": [5, 8]}, \"SPEAKER_01\": {\"name\": null, \"reasoning_indices\": []}}") # Updated Example
    prompt_lines.append("\n--- Transcript Excerpts ---") # Start of context section

    # --- Process Relevant Indices and Add Context ---
    processed_indices = set() # Track indices already added to avoid redundant blocks
    for i in sorted(list(set(relevant_indices))): # Ensure uniqueness and process chronologically
        if i in processed_indices: continue # Skip if already included

        start_idx = max(0, i - CONTEXT_WINDOW)
        end_idx = min(len(transcript_segments), i + CONTEXT_WINDOW + 1)

        current_snippet_lines = []
        # Add header for this context block, emphasizing the index number
        trigger_segment = transcript_segments[i]
        prompt_lines.append(f"\nContext around Line Index {i} (Speaker {trigger_segment.get('speaker', 'N/A')}):")

        for j in range(start_idx, end_idx):
             if j >= len(transcript_segments): continue # Boundary check
             segment = transcript_segments[j]
             speaker_id = segment.get('speaker', 'N/A')
             text = segment.get('text', '')

             line_prefix = ">> " if j == i else "   " # Highlight the trigger line
             # Clearly label the line index for the LLM to reference
             line_text = f"{line_prefix}[Index:{j}, Speaker:{speaker_id}] {text}"
             prompt_lines.append(line_text)
             current_snippet_lines.append(line_text)
             processed_indices.add(j) # Mark index as processed

        # Store the generated snippet, keyed by the index 'i' that triggered it
        context_snippets[i] = "\n".join(current_snippet_lines)

    prompt_lines.append("\n--- End Excerpts ---")
    prompt_lines.append("\nRespond ONLY with the JSON object containing the Speaker ID mapping as described. Do not include explanations outside the JSON object.")

    return "\n".join(prompt_lines), context_snippets


def find_potential_identification_lines(transcript_segments: List[Dict[str, Any]]) -> List[int]:
    """
    Scans transcript segments for keywords that might indicate speaker introductions
    or direct address, returning indices of potentially relevant lines and their neighbors.
    (Function body remains the same)
    """
    # Keywords list - adjust based on expected languages and introduction patterns
    keywords = [
        "name is", "i am", "i'm", "this is", "call me", "speaking", # English intros
        "hello", "hi ", "hey ", "good morning", "good afternoon",   # English greetings
        " my name ", # Variations with spaces
        # Dutch examples (expand if needed)
        "dag ", "hallo", "ik ben", "mijn naam is", " met ", # Note spaces
    ]
    potential_indices = set() # Use set for automatic deduplication

    for i, segment in enumerate(transcript_segments):
        text = segment.get("text")
        # Process only if text exists and is a string
        if text and isinstance(text, str):
            text_lower = text.lower()
            if any(keyword in text_lower for keyword in keywords):
                # If keyword found, add current index and immediate neighbors
                potential_indices.add(i)
                if i > 0: potential_indices.add(i-1)
                if i < len(transcript_segments) - 1: potential_indices.add(i+1)

    sorted_indices = sorted(list(potential_indices))
    log(f"Found {len(sorted_indices)} potential name ID line indices: {sorted_indices}", "DEBUG")
    return sorted_indices


# --- Main Detection Function ---

# *** MODIFICATION 2: Update return type hint for the mapping dictionary ***
def detect_speaker_names(
    transcript_segments: List[Dict[str, Any]],
    config: dict,
    model_list_override: Optional[Union[str, List[str]]] = None,
    timeout_override: Optional[int] = None
    ) -> Tuple[Optional[Dict[str, Dict[str, Any]]], Optional[Dict[int, str]]]:
    """
    Attempts to detect speaker names from transcript segments using an LLM,
    now including reasoning indices.

    Args:
        transcript_segments: List of transcript segment dictionaries.
        config: The job configuration dictionary.
        model_list_override: Optional override for the list/name of models to try.
        timeout_override: Optional timeout override for the LLM call.

    Returns:
        A tuple containing:
        1. Mapping dictionary (speaker_id -> {"name": str|None, "reasoning_indices": List[int]})
           or None on critical failure. Returns {} if process skipped or no names found.
        2. Context snippets dictionary (index -> snippet_text) or None if prompt building failed.
           Returns {} if process skipped before prompt building.
    """
    # Change type hint for the final map
    final_mapping_with_context: Optional[Dict[str, Dict[str, Any]]] = {}
    context_snippets: Optional[Dict[int, str]] = {}

    if not transcript_segments:
        log("Cannot detect names: Input transcript is empty.", "WARNING")
        return {}, {} # Return empty dicts for valid empty input

    log("Starting speaker name detection process...", "INFO")

    # --- Step 1: Find Potential Lines ---
    potential_indices = find_potential_identification_lines(transcript_segments)
    if not potential_indices:
        log("No potential name identification keywords found. Skipping LLM detection.", "INFO")
        return {}, {} # Return empty dicts if no relevant lines

    # --- Step 2: Build Prompt ---
    try:
        prompt, context_snippets = build_name_detection_prompt(transcript_segments, potential_indices)
        log(f"Built name detection prompt ({len(prompt)} chars). Context snippets generated: {len(context_snippets)}", "DEBUG")
    except Exception as e:
         log(f"Critical error building name detection prompt: {e}", "ERROR")
         log(traceback.format_exc(), "DEBUG")
         return None, None # Indicate critical failure if prompt cannot be built

    # --- Step 3: Determine LLM Model(s) ---
    # (This part remains the same)
    models_to_use: Union[str, List[str]]
    if model_list_override:
        models_to_use = model_list_override
        log(f"Using overridden model list for name detection: {models_to_use}", "INFO")
    else:
        task_name = "name_detection" # Key in config['llm_models']
        llm_models_config = config.get("llm_models", {})
        if not isinstance(llm_models_config, dict):
            log(f"Invalid 'llm_models' in config. Using default for '{task_name}'.", "WARNING")
            models_to_use = ["llama3:8b"] # Default fallback model
        else:
            models_to_use = llm_models_config.get(task_name, [])
            if not models_to_use:
                log(f"No models configured for task '{task_name}'. Using default 'llama3:8b'.", "WARNING")
                models_to_use = ["llama3:8b"] # Default fallback model
        log(f"Using configured models for task '{task_name}': {models_to_use}", "INFO")

    # --- Step 4: Run LLM ---
    # (This part remains the same)
    log(f"Sending name detection prompt to LLM(s): {models_to_use}...", "INFO")
    effective_timeout = timeout_override if timeout_override is not None else config.get("llm_default_timeout")
    llm_response_raw = run_llm(prompt, models_to_use, config, timeout=effective_timeout)

    # --- Step 5: Parse and Validate Response ---
    # *** MODIFICATION 3: Update parsing and validation logic for new structure ***
    if llm_response_raw is None:
        log("LLM call for name detection failed/timed out.", "ERROR")
        # Return None for map, but keep context snippets as they were generated
        return None, context_snippets

    log(f"Received raw response from LLM for name detection.", "DEBUG")

    try:
        # --- Robust JSON Parsing (remains similar) ---
        json_response_str = llm_response_raw.strip()
        if json_response_str.startswith("```json"): json_response_str = json_response_str[len("```json"):].strip()
        elif json_response_str.startswith("```"): json_response_str = json_response_str[len("```"):].strip()
        if json_response_str.endswith("```"): json_response_str = json_response_str[:-len("```")].strip()

        parsed_llm_output = None
        try:
            parsed_llm_output = json.loads(json_response_str)
        except json.JSONDecodeError as e1:
            log(f"Direct JSON parsing failed ({e1}), attempting to extract JSON object.", "DEBUG")
            first_brace = json_response_str.find('{')
            last_brace = json_response_str.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                json_substring = json_response_str[first_brace:last_brace+1]
                try:
                     parsed_llm_output = json.loads(json_substring)
                     log("Successfully parsed extracted JSON substring.", "DEBUG")
                except json.JSONDecodeError as e2:
                     log(f"Failed to parse extracted JSON substring: {e2}", "ERROR")
                     raise json.JSONDecodeError(f"Could not parse JSON object from LLM response. Direct/Substring errors: {e1} / {e2}", json_response_str, 0) from e1
            else:
                 log("Could not find JSON object markers '{{...}}' in the response.", "ERROR")
                 raise json.JSONDecodeError("Could not find valid JSON object in LLM response.", json_response_str, 0) from e1

        # --- Validation of the NEW structure ---
        if not isinstance(parsed_llm_output, dict):
            log(f"LLM response parsed, but it's not a dictionary (type: {type(parsed_llm_output)}).", "ERROR")
            return None, context_snippets # Return None for map if structure wrong

        validated_mapping: Dict[str, Dict[str, Any]] = {} # Stores the validated result
        all_speakers_in_transcript = {seg.get('speaker') for seg in transcript_segments if seg.get('speaker')}
        all_context_indices = set(context_snippets.keys()) if context_snippets else set()

        for speaker_id, name_obj in parsed_llm_output.items():
            # Validate speaker ID against transcript speakers
            if speaker_id not in all_speakers_in_transcript:
                log(f"LLM returned mapping for unknown/unused speaker ID '{speaker_id}'. Ignoring.", "WARNING")
                continue

            # Validate the structure of the value (must be a dict with 'name' and 'reasoning_indices')
            if not isinstance(name_obj, dict) or "name" not in name_obj or "reasoning_indices" not in name_obj:
                log(f"LLM response for speaker '{speaker_id}' has invalid format. Expected object with 'name' and 'reasoning_indices'. Got: {name_obj}. Treating as unmapped.", "WARNING")
                validated_mapping[speaker_id] = {"name": None, "reasoning_indices": []}
                continue

            # Validate and sanitize the detected name
            detected_name = name_obj.get("name")
            final_name: Optional[str] = None
            if detected_name is None:
                final_name = None # Null is valid
            elif isinstance(detected_name, str):
                stripped_name = detected_name.strip()
                final_name = stripped_name if stripped_name else None # Treat empty string as None
            else:
                log(f"LLM returned non-string/non-null name for speaker '{speaker_id}' (type: {type(detected_name)}). Treating as None.", "WARNING")
                final_name = None

            # Validate reasoning_indices (must be a list of integers corresponding to context snippet keys)
            raw_indices = name_obj.get("reasoning_indices")
            final_indices: List[int] = []
            if isinstance(raw_indices, list):
                for index in raw_indices:
                    if isinstance(index, int) and index in all_context_indices:
                        final_indices.append(index)
                    elif isinstance(index, int):
                        log(f"LLM returned reasoning index {index} for speaker '{speaker_id}', but this index was not provided in context. Ignoring index.", "WARNING")
                    else:
                         log(f"LLM returned invalid reasoning index type ({type(index)}) for speaker '{speaker_id}'. Ignoring index.", "WARNING")
            else:
                 log(f"LLM returned invalid 'reasoning_indices' type ({type(raw_indices)}) for speaker '{speaker_id}'. Expected list. Using empty list.", "WARNING")

            # Store the validated result
            validated_mapping[speaker_id] = {"name": final_name, "reasoning_indices": sorted(list(set(final_indices)))} # Store unique, sorted indices

        final_mapping_with_context = validated_mapping
        log(f"Successfully parsed and validated speaker name mapping (with context indices): {final_mapping_with_context}", "SUCCESS")

    except json.JSONDecodeError as e:
        log(f"Failed to decode JSON from LLM response: {e}", "ERROR")
        log(f"Problematic Response Snippet (start): {llm_response_raw[:150]}...", "INFO")
        final_mapping_with_context = None # Indicate parsing failure
    except Exception as e:
        log(f"Unexpected error parsing/validating LLM response: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        final_mapping_with_context = None # Indicate general failure

    # Return the final mapping (dict or None) and the context snippets (dict)
    return final_mapping_with_context, context_snippets


# Example usage block
# *** MODIFICATION 4: Update test block for new structure ***
if __name__ == "__main__":
    print("-" * 40)
    print("--- Testing Speaker Name Detector (with Context Indices) ---") # Updated print
    print("-" * 40)
    try:
        from src.utils.log import setup_logging; import logging
        setup_logging(level=logging.DEBUG)
    except ImportError: print("Skipping logger setup.")
    try:
        from src.utils.config_schema import PROJECT_ROOT
    except ImportError: PROJECT_ROOT = Path(__file__).resolve().parent.parent

    # Mock transcript segments (more realistic indices)
    mock_transcript = [
        {"start": 0.5, "end": 2.1, "speaker": "SPEAKER_00", "text": "Hello, my name is Alice."}, # Index 0
        {"start": 2.5, "end": 4.8, "speaker": "SPEAKER_01", "text": "Hi Alice, I'm Bob."},        # Index 1
        {"start": 5.1, "end": 7.2, "speaker": "SPEAKER_00", "text": "Nice to meet you, Bob."},   # Index 2
        {"start": 7.5, "end": 9.9, "speaker": "SPEAKER_02", "text": "(Background noise)"},      # Index 3
        {"start": 10.1, "end": 11.5, "speaker": "SPEAKER_01", "text": "We should discuss the report."},# Index 4
        {"start": 11.7, "end": 12.5, "speaker": "SPEAKER_00", "text": "Okay."},                  # Index 5
    ]
    # Mock config (needed for run_llm inside detect_speaker_names)
    # In a real run, this comes from load_config()
    mock_config = {
        "llm_models": {
             "name_detection": ["mock-model-for-test"] # Use a placeholder
        },
        "llm_default_timeout": 60
    }

    print("\nInput Transcript Segments:")
    for i, seg in enumerate(mock_transcript): print(f"Index {i}: {seg}")

    # --- Simulate calling detect_speaker_names ---
    # In a real test, you'd mock run_llm to return a simulated JSON response
    # For this example, we'll just show the expected structure
    print("\n--- Simulating detect_speaker_names call ---")
    # Assuming find_potential_identification_lines identifies indices like [0, 1, 2, 4]
    # And build_name_detection_prompt creates context snippets for these
    # Expected structure of the returned map:
    expected_map_structure = {
        "SPEAKER_00": {"name": "Alice", "reasoning_indices": [0]},
        "SPEAKER_01": {"name": "Bob", "reasoning_indices": [1, 2]}, # Bob introduced himself (1) and Alice addressed him (2)
        "SPEAKER_02": {"name": None, "reasoning_indices": []} # No name identified
    }
    # Expected context snippets structure (example subset):
    expected_context_snippets_structure = {
        0: "[Index:0, Speaker:SPEAKER_00] Hello, my name is Alice.\n[Index:1, Speaker:SPEAKER_01] Hi Alice, I'm Bob.",
        1: "[Index:0, Speaker:SPEAKER_00] Hello, my name is Alice.\n[Index:1, Speaker:SPEAKER_01] Hi Alice, I'm Bob.\n[Index:2, Speaker:SPEAKER_00] Nice to meet you, Bob."
        # ... other snippets
    }

    print("\nExpected Output Map Structure:")
    print(json.dumps(expected_map_structure, indent=2))
    print("\nExpected Context Snippets Structure (Example):")
    print(json.dumps(expected_context_snippets_structure, indent=2))

    # NOTE: To *actually* test this, you would need to mock the `run_llm` function
    # within this script to return a JSON string matching the new expected format
    # when `detect_speaker_names` calls it.

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)