# src/utils/llm.py

import subprocess
import yaml # Keep yaml for update_config_with_available_models
import json
from pathlib import Path
# Ensure Union is imported from typing
from typing import List, Dict, Optional, Union, Any # Added Any

# Assuming log utility is adapted for English messages
from src.utils.log import log
# Get project root for default config path
try:
    from src.utils.config_schema import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent # Fallback
    log("WARNING: Could not import PROJECT_ROOT from config_schema in llm.py, using fallback.", "WARNING")


# Define the default path for the main configuration file
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# --- Ollama Communication Helpers ---
def _run_ollama_command(command: List[str], input_data: Optional[str] = None, timeout: Optional[int] = None) -> Optional[str]:
    """
    Runs an Ollama CLI command using subprocess, capturing output.

    Args:
        command: The command and arguments as a list of strings.
        input_data: Optional string data to pass as stdin to the command.
        timeout: Optional timeout in seconds.

    Returns:
        The stdout content as a string if successful, None otherwise.
    """
    try:
        # Log command for debugging, avoid logging potentially large input_data
        log(f"Running Ollama command: {' '.join(command)}", "DEBUG")
        process = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            text=True,
            check=False, # Don't raise exception on non-zero exit code
            timeout=timeout,
            encoding='utf-8' # Explicitly set encoding
        )
        # Check return code after execution
        if process.returncode != 0:
            stderr_output = process.stderr.strip() if process.stderr else "No stderr."
            log(f"Ollama command failed (Code {process.returncode}): {' '.join(command)}", "ERROR")
            log(f"Ollama Stderr: {stderr_output}", "ERROR") # Log stderr for details
            return None
        # Return stripped stdout on success
        return process.stdout.strip()
    except FileNotFoundError:
        # Specific error if 'ollama' command isn't found
        log(f"Error: 'ollama' command not found. Please ensure Ollama is installed and in the system's PATH.", "CRITICAL")
        return None
    except subprocess.TimeoutExpired:
        log(f"Ollama command timed out after {timeout} seconds: {' '.join(command)}", "ERROR")
        return None
    except Exception as e:
        # Catch any other unexpected errors during subprocess execution
        log(f"Unexpected error running Ollama command: {' '.join(command)}\nError: {e}", "ERROR")
        return None

def get_local_models() -> List[str]:
    """Retrieves a list of locally available Ollama models via 'ollama list'."""
    log("Fetching list of local Ollama models...", "INFO")
    output = _run_ollama_command(["ollama", "list"])
    if output is None:
        log("Failed to retrieve local models from Ollama.", "ERROR")
        return [] # Return empty list on failure

    models = []
    lines = output.strip().splitlines()
    # Expecting header line, skip it (lines[1:])
    if len(lines) > 1:
        for line in lines[1:]: # Start from the second line
            # Split by whitespace and take the first part (should be model_name:tag)
            parts = line.split()
            if parts:
                models.append(parts[0])

    if not models:
        log("No local Ollama models found. Ensure Ollama service is running and models are pulled ('ollama pull ...').", "WARNING")
    else:
        # Log found models at DEBUG level to avoid cluttering INFO logs
        log(f"Found local models: {models}", "DEBUG")

    return models

def is_model_available(model_name: str, local_models: Optional[List[str]] = None) -> bool:
    """
    Checks if a specific Ollama model (e.g., 'llama3:8b') is available locally.

    Args:
        model_name: The name of the model to check.
        local_models: An optional pre-fetched list of local models to avoid repeated calls.

    Returns:
        True if the model is available, False otherwise.
    """
    if not model_name: return False # Handle empty or None model name
    # Fetch list if not provided
    current_local_models = local_models if local_models is not None else get_local_models()
    return model_name in current_local_models

# --- Configuration and Model Preference Logic ---
# Added return type hint
def _get_available_preferred_models(
    preferred_models_config: Dict[str, List[str]],
    available_local_models: List[str]
    ) -> Dict[str, List[str]]:
    """
    Filters a dictionary of preferred models per task against a list of available models.
    Returns a new dictionary containing only the locally available preferred models for each task.
    """
    available_preferred: Dict[str, List[str]] = {}
    for task, models in preferred_models_config.items():
        if not isinstance(models, list):
            log(f"Invalid model list format for task '{task}' in config. Expected list, got {type(models)}. Skipping.", "WARNING")
            continue
        # Filter the list, keeping only models present in available_local_models
        filtered_models = [m for m in models if m in available_local_models]
        if not filtered_models:
            # Log only if preferences were set but none are available
            if models:
                 log(f"None of the preferred models for task '{task}' ({models}) were found locally.", "WARNING")
        # Store the filtered list (can be empty if no preferred models are available)
        available_preferred[task] = filtered_models
    return available_preferred

def update_config_with_available_models(config_path: Path = DEFAULT_CONFIG_PATH) -> bool:
    """
    !! DANGEROUS: Modifies Config File !!
    Updates the 'llm_models' section in the specified config file (config.yaml)
    to only list models that are currently available locally according to 'ollama list'.
    This removes preferences for models that are not installed.
    **Use with extreme caution!** This permanently modifies your configuration file.
    It's strongly recommended to trigger this manually rather than automatically.

    Args:
        config_path: Path to the config file to update.

    Returns:
        True if the file was modified and saved successfully, False otherwise.
    """
    log(f"Attempting to update model availability in config file: {config_path}", "INFO")
    log("CRITICAL WARNING: This action will modify the configuration file on disk!", "CRITICAL") # Stronger warning
    if not config_path.is_file():
        log(f"Cannot update config: File not found at '{config_path}'.", "ERROR")
        return False

    try:
        with open(config_path, "r", encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        if not isinstance(config, dict):
            log(f"Config file at '{config_path}' does not contain a valid dictionary. Update aborted.", "ERROR")
            return False
    except Exception as e:
        log(f"Error loading config file '{config_path}' for update: {e}", "ERROR")
        return False

    current_llm_prefs = config.get("llm_models", {})
    if not isinstance(current_llm_prefs, dict):
        log(f"'llm_models' section in config is not a valid dictionary. Cannot update preferences.", "WARNING")
        return False

    available_models = get_local_models()
    if not available_models:
        log(f"No local models detected via 'ollama list'. Cannot reliably update model preferences. Aborting update.", "WARNING")
        return False # Avoid wiping preferences if ollama list fails

    # Get the preferences filtered by availability
    updated_prefs = _get_available_preferred_models(current_llm_prefs, available_models)

    # Check if an update is actually needed by comparing dictionaries
    if config.get("llm_models") == updated_prefs:
        log("Model preferences in config file are already consistent with local availability. No changes needed.", "INFO")
        return False # Return False as no update occurred

    # Update the config dictionary in memory and write back to file
    log(f"Updating 'llm_models' in config file '{config_path.name}'...", "INFO")
    config["llm_models"] = updated_prefs
    try:
        with open(config_path, "w", encoding='utf-8') as f:
            # Use arguments for readable YAML output
            yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
        log(f"Config file '{config_path.name}' updated successfully with available local models.", "SUCCESS")
        return True # Return True as the file was updated
    except Exception as e:
        log(f"Error writing updated config file '{config_path.name}': {e}", "ERROR")
        return False


# --- Core LLM Execution ---
def run_with_fallback(task: str, prompt: str, config: dict, timeout: Optional[int] = None) -> Optional[str]:
    """
    Runs a prompt using Ollama, trying models specified for the task in config,
    checking for local availability and falling back to the next model on failure.

    Args:
        task: The key corresponding to the task in config['llm_models'] (e.g., 'summary').
        prompt: The input prompt for the LLM.
        config: The application configuration dictionary.
        timeout: Optional specific timeout for this call (overrides config defaults).

    Returns:
        The LLM output string on success, None on failure after trying all available models.
    """
    # Safely get the llm_models configuration section from the provided config
    llm_models_config = config.get("llm_models", {}) if isinstance(config, dict) else {}
    if not isinstance(llm_models_config, dict):
         log(f"Configuration section 'llm_models' is missing or invalid type ({type(llm_models_config)}). Cannot run LLM task '{task}'.", "ERROR")
         return None

    # Get the list of models preferred for this specific task
    fallback_models = llm_models_config.get(task, [])

    # Validate the retrieved model list - must be a non-empty list
    if not isinstance(fallback_models, list) or not fallback_models:
        log(f"No models defined or invalid format for task '{task}' in config['llm_models']. Please check config.yaml.", "ERROR")
        return None # Cannot proceed without a valid list of models

    # Get available local models ONCE before the loop for efficiency
    local_models = get_local_models()
    if not local_models:
        log("No local Ollama models detected. Cannot run LLM task '{task}'. Ensure Ollama is running.", "ERROR")
        return None

    # Try each model in the preferred list for the task
    for i, model_name in enumerate(fallback_models):
        # Basic validation of the model name itself
        if not model_name or not isinstance(model_name, str):
             log(f"Skipping invalid model name entry #{i+1} in list for task '{task}': '{model_name}'", "WARNING")
             continue

        # *** Check if this preferred model is actually available locally ***
        if not is_model_available(model_name, local_models):
            log(f"Model '{model_name}' (preference {i+1} for task '{task}') not found locally – skipping.", "WARNING")
            continue # Move to the next preferred model in the list

        # --- Attempt to run the available model ---
        log(f"Attempting task '{task}' with locally available model: {model_name} (Preference {i+1}/{len(fallback_models)})", "INFO")
        command = ["ollama", "run", model_name]

        # Determine effective timeout: argument > task-specific config > default config
        effective_timeout = timeout # Use direct argument first, if provided
        if effective_timeout is None: # If no direct argument, check config
            # Check for specific final analysis timeout first if applicable
            if task == "final" and "llm_final_analysis_timeout" in config:
                effective_timeout = config.get("llm_final_analysis_timeout")
            # Otherwise, use the default timeout
            if effective_timeout is None: # Still None? Use the general default
                effective_timeout = config.get("llm_default_timeout")
        # Log the timeout being used (or None)
        log(f"Using timeout: {effective_timeout if effective_timeout is not None else 'None (default)'}", "DEBUG")

        # Run the Ollama command via the helper function
        output = _run_ollama_command(command, input_data=prompt, timeout=effective_timeout)

        # Check result
        if output is not None: # Command succeeded and returned output
            # Log success, differentiate if it was the primary choice or a fallback
            success_level = "SUCCESS" if i == 0 else "INFO"
            log(f"Model '{model_name}' succeeded for task '{task}'.", success_level)
            return output # Return the successful output

        # If output is None, an error occurred (already logged by _run_ollama_command)
        log(f"Model '{model_name}' failed or timed out for task '{task}'. Trying next available fallback model...", "INFO")
        # Loop continues to the next available model in the fallback_models list

    # If the loop finishes without returning, all specified and available models failed
    log(f"All specified and locally available models failed for task '{task}'.", "ERROR")
    return None


# --- Specific Task Implementations ---
# ** UPDATED summarize_transcript to accept text **
def summarize_transcript(transcript_text: str, config: dict, context: str = "") -> Optional[str]:
    """
    Generates a summary of the provided transcript text using the 'summary' LLM config.

    Args:
        transcript_text: The full transcript text as a single string.
        config: The job configuration dictionary.
        context: Optional user-provided context string.

    Returns:
        The summary string from the LLM, or None on failure.
    """
    # Validate input text
    if not transcript_text or not isinstance(transcript_text, str):
        log(f"Cannot summarize: Invalid or empty transcript text provided.", "ERROR")
        return None

    log(f"Preparing summary for transcript text (Length: {len(transcript_text)} chars)", "INFO")

    # Build the prompt using the provided text
    # Refine prompt as needed
    prompt = f"Please provide a concise bullet-point summary of the key points discussed in the following conversation transcript:\n\n---\n{transcript_text}\n---\n\nSummary:"
    if context:
        prompt = f"Considering the following context: {context.strip()}\n{prompt}"

    # Use run_with_fallback for the 'summary' task key defined in config
    summary = run_with_fallback("summary", prompt.strip(), config)
    # Logging of success/failure is handled within run_with_fallback

    return summary


# --- Generic LLM Runner ---
def run_llm(prompt: str, model_list: Union[str, List[str]], config: dict, timeout: Optional[int] = None) -> Optional[str]:
    """
    Runs a specific prompt with a specified model or list of models, using fallback logic.
    This is a more direct way to call an LLM compared to task-specific functions.
    """
    # Define a temporary task name to use the fallback mechanism
    temp_task_name = "custom_run_llm_task" # Arbitrary name not expected in config
    # Ensure model_list is consistently a list for the temp config
    models_for_task = [model_list] if isinstance(model_list, str) else model_list
    if not models_for_task:
        log("No models provided to run_llm.", "ERROR")
        return None

    # Create a temporary config that defines this specific model list for our temp task
    # Inherit other settings (like timeouts) from the main config dictionary
    temp_config = {**config, "llm_models": {temp_task_name: models_for_task}}

    # Execute using run_with_fallback, specifying the temporary task name
    output = run_with_fallback(temp_task_name, prompt, temp_config, timeout=timeout)
    return output


# Example usage for testing utility functions
if __name__ == "__main__":
    from src.utils.load_config import load_config # Need load_config for testing
    from src.utils.log import setup_logging # Need setup for logging
    import logging

    print("-" * 40); print("--- Testing LLM Utilities ---"); print("-" * 40)
    setup_logging(level=logging.DEBUG) # Enable debug logs for testing

    print("\nFetching available local models...")
    models = get_local_models()
    if models: print(f"Available models: {', '.join(models)}")
    else: print("Could not fetch models or none available. Ensure Ollama is running.")

    # Example: Test checking model availability
    if models:
        model_to_check = models[0]
        print(f"\nChecking availability of '{model_to_check}': {is_model_available(model_to_check, models)}")
        print(f"Checking availability of 'fake-model:latest': {is_model_available('fake-model:latest', models)}")

    # --- Example: Test run_llm (Requires Ollama running and models) ---
    print("\n--- Testing run_llm (Requires loaded config & Ollama) ---")
    try:
        test_config = load_config()
        if models and test_config.get("llm_models"):
            test_prompt = "Briefly explain why the sky appears blue during the day."
            test_model = models[0] # Use first available model
            print(f"\nAttempting run_llm with model '{test_model}':")
            print(f"Prompt: '{test_prompt}'")
            result = run_llm(test_prompt, test_model, test_config, timeout=60)
            print("\nResult from run_llm:")
            print(result or "run_llm failed or returned None (Check Ollama status/model availability).")
        elif not models: print("\nSkipping run_llm test: No local models found.")
        else: print("\nSkipping run_llm test: 'llm_models' not found or invalid in config.")
    except Exception as e: print(f"\nError during run_llm test setup/execution: {e}")

    # --- Example: Test summarize_transcript ---
    print("\n--- Testing summarize_transcript ---")
    mock_text = "This is the first sentence. This is the second sentence discussing an important point. The third sentence provides context. Finally, a concluding remark."
    try:
        test_config = load_config() # Reload config
        if test_config.get("llm_models", {}).get("summary"): # Check if summary models are configured
             print("\nAttempting summarize_transcript:")
             print(f"Input Text: '{mock_text}'")
             summary_result = summarize_transcript(mock_text, test_config)
             print("\nResult from summarize_transcript:")
             print(summary_result or "Summarize task failed (Check Ollama status/models).")
        else:
             print("\nSkipping summarize_transcript test: No models configured for 'summary' task.")
    except Exception as e: print(f"\nError during summarize_transcript test: {e}")


    print("-" * 40); print("--- LLM Utility Testing Complete ---"); print("-" * 40)