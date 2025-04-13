# src/speaker_name_detector.py
import json
import traceback
from pathlib import Path
# Ensure Union is imported from typing
from typing import List, Dict, Optional, Tuple, Union, Any

# Import utilities
from src.utils.log import log
# Use the centralized LLM runner which handles model selection and fallback
from src.utils.llm import run_llm

# Constants
CONTEXT_WINDOW = 2 # Number of segments before/after a potential ID line to include in prompt

# --- Helper Functions ---

def build_name_detection_prompt(
    transcript_segments: List[Dict[str, Any]],
    relevant_indices: List[int]
    ) -> Tuple[str, Dict[int, str]]:
    """
    Builds the LLM prompt for speaker name detection, including context
    around potentially relevant lines identified earlier.

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
    prompt_lines.append("For each speaker ID where a name is confidently identified from the provided context, state the speaker ID and the detected name.")
    prompt_lines.append("If no clear name identification is found for a specific speaker ID *within these excerpts*, map the ID to null.")
    prompt_lines.append("\nFormat the output STRICTLY as a single JSON object mapping speaker IDs found in the excerpts to detected names (string) or null.")
    prompt_lines.append("Example Output: {\"SPEAKER_00\": \"Alice B.\", \"SPEAKER_01\": \"Bob\", \"SPEAKER_02\": null}")
    prompt_lines.append("\n--- Transcript Excerpts ---") # Start of context section

    # --- Process Relevant Indices and Add Context ---
    processed_indices = set() # Track indices already added to avoid redundant blocks
    for i in sorted(list(set(relevant_indices))): # Ensure uniqueness and process chronologically
        if i in processed_indices: continue # Skip if already included

        start_idx = max(0, i - CONTEXT_WINDOW)
        end_idx = min(len(transcript_segments), i + CONTEXT_WINDOW + 1)

        current_snippet_lines = []
        # Add header for this context block
        trigger_segment = transcript_segments[i]
        prompt_lines.append(f"\nContext around Line Index {i} (Speaker {trigger_segment.get('speaker', 'N/A')}):")

        for j in range(start_idx, end_idx):
             if j >= len(transcript_segments): continue # Boundary check
             segment = transcript_segments[j]
             speaker_id = segment.get('speaker', 'N/A')
             text = segment.get('text', '')

             line_prefix = ">> " if j == i else "   " # Highlight the trigger line
             line_text = f"{line_prefix}[Index:{j}, Speaker:{speaker_id}] {text}"
             prompt_lines.append(line_text)
             current_snippet_lines.append(line_text)
             processed_indices.add(j) # Mark index as processed

        # Store the generated snippet, keyed by the index 'i' that triggered it
        context_snippets[i] = "\n".join(current_snippet_lines)

    prompt_lines.append("\n--- End Excerpts ---")
    prompt_lines.append("\nRespond ONLY with the JSON object containing the Speaker ID to Name mapping (or null). Do not include any explanations or markdown formatting outside the JSON object.")

    return "\n".join(prompt_lines), context_snippets


def find_potential_identification_lines(transcript_segments: List[Dict[str, Any]]) -> List[int]:
    """
    Scans transcript segments for keywords that might indicate speaker introductions
    or direct address, returning indices of potentially relevant lines and their neighbors.
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
def detect_speaker_names(
    transcript_segments: List[Dict[str, Any]],
    config: dict,
    model_list_override: Optional[Union[str, List[str]]] = None,
    timeout_override: Optional[int] = None
    ) -> Tuple[Optional[Dict[str, Optional[str]]], Optional[Dict[int, str]]]:
    """
    Attempts to detect speaker names from transcript segments using an LLM.

    Args:
        transcript_segments: List of transcript segment dictionaries.
        config: The job configuration dictionary.
        model_list_override: Optional override for the list/name of models to try.
        timeout_override: Optional timeout override for the LLM call.

    Returns:
        A tuple containing:
        1. Mapping dictionary (speaker_id -> name/None) or None on critical failure.
           Returns {} if process skipped or no names found.
        2. Context snippets dictionary or None if prompt building failed.
           Returns {} if process skipped before prompt building.
    """
    final_mapping: Optional[Dict[str, Optional[str]]] = {}
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
    log(f"Sending name detection prompt to LLM(s): {models_to_use}...", "INFO")
    effective_timeout = timeout_override if timeout_override is not None else config.get("llm_default_timeout")
    llm_response_raw = run_llm(prompt, models_to_use, config, timeout=effective_timeout)

    # --- Step 5: Parse and Validate Response ---
    if llm_response_raw is None:
        log("LLM call for name detection failed/timed out.", "ERROR")
        # Return None for map, but keep context snippets as they were generated
        return None, context_snippets

    log(f"Received raw response from LLM for name detection.", "DEBUG")
    # Optional: log raw response only if parsing fails or at higher debug level
    # log(f"Raw LLM response:\n{llm_response_raw}", "TRACE") # Example using hypothetical TRACE level

    try:
        # --- Robust JSON Parsing ---
        json_response_str = llm_response_raw.strip()
        # Remove potential markdown fences
        if json_response_str.startswith("```json"): json_response_str = json_response_str[len("```json"):].strip()
        elif json_response_str.startswith("```"): json_response_str = json_response_str[len("```"):].strip()
        if json_response_str.endswith("```"): json_response_str = json_response_str[:-len("```")].strip()

        parsed_mapping = None
        try: # Try parsing the cleaned string directly
            parsed_mapping = json.loads(json_response_str)
        except json.JSONDecodeError as e1:
            log(f"Direct JSON parsing failed ({e1}), attempting to extract JSON object.", "DEBUG")
            # If direct parse fails, try finding first '{' and last '}'
            first_brace = json_response_str.find('{')
            last_brace = json_response_str.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                json_substring = json_response_str[first_brace:last_brace+1]
                try:
                     parsed_mapping = json.loads(json_substring)
                     log("Successfully parsed extracted JSON substring.", "DEBUG")
                except json.JSONDecodeError as e2:
                     log(f"Failed to parse extracted JSON substring: {e2}", "ERROR")
                     # Re-raise original error for clarity if substring parse also fails
                     raise json.JSONDecodeError(f"Could not parse JSON object from LLM response. Direct/Substring errors: {e1} / {e2}", json_response_str, 0) from e1
            else:
                 log("Could not find JSON object markers '{{...}}' in the response.", "ERROR")
                 raise json.JSONDecodeError("Could not find valid JSON object in LLM response.", json_response_str, 0) from e1

        # --- Validation ---
        if not isinstance(parsed_mapping, dict):
            log(f"LLM response parsed, but it's not a dictionary (type: {type(parsed_mapping)}).", "ERROR")
            return None, context_snippets # Return None for map if structure wrong

        validated_mapping: Dict[str, Optional[str]] = {}
        all_speakers_in_transcript = {seg.get('speaker') for seg in transcript_segments if seg.get('speaker')}

        for speaker_id, detected_name in parsed_mapping.items():
            # Validate speaker ID against transcript speakers
            if speaker_id not in all_speakers_in_transcript:
                log(f"LLM returned mapping for unknown/unused speaker ID '{speaker_id}'. Ignoring.", "WARNING")
                continue
            # Validate and sanitize the detected name
            if detected_name is None:
                validated_mapping[speaker_id] = None # Null is valid
            elif isinstance(detected_name, str):
                stripped_name = detected_name.strip()
                # Treat empty string after stripping as None
                validated_mapping[speaker_id] = stripped_name if stripped_name else None
            else: # Treat non-string, non-null as invalid (None)
                log(f"LLM returned non-string/non-null name for speaker '{speaker_id}' (type: {type(detected_name)}). Treating as None.", "WARNING")
                validated_mapping[speaker_id] = None

        final_mapping = validated_mapping
        log(f"Successfully parsed and validated speaker name mapping: {final_mapping}", "SUCCESS")

    except json.JSONDecodeError as e:
        log(f"Failed to decode JSON from LLM response: {e}", "ERROR")
        log(f"Problematic Response Snippet (start): {llm_response_raw[:150]}...", "INFO")
        final_mapping = None # Indicate parsing failure
    except Exception as e:
        log(f"Unexpected error parsing/validating LLM response: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        final_mapping = None # Indicate general failure

    # Return the final mapping (dict or None) and the context snippets (dict)
    return final_mapping, context_snippets


# Example usage block (no changes needed)
if __name__ == "__main__":
     # ... Test code ...
     pass