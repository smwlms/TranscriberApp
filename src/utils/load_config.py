# src/utils/load_config.py

import yaml
import traceback # Keep for logging unexpected errors
from pathlib import Path
from typing import Dict, Any, Optional

# Import logging utility first
# Assuming basic console logging might be available even if config loading fails partially
from src.utils.log import log, setup_logging # Import setup_logging for test block

# Import other utilities
from src.utils.generate_config_from_schema import generate_default_config
from src.utils.config_schema import PROJECT_ROOT, DEFAULT_SCHEMA_PATH
from src.utils.auto_update_config import auto_update_config

# Define the default path for the main configuration file
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """
    Loads the main configuration from the specified YAML file.

    If the file doesn't exist, it attempts to generate a default config file.
    If the file exists, it automatically adds any missing fields based on the
    schema defaults before returning the config. This might involve writing
    updates back to the config file.

    Args:
        config_path: The path to the configuration YAML file.
                     Defaults to config.yaml in the project root.

    Returns:
        A dictionary containing the configuration, potentially updated with
        defaults, or an empty dictionary if loading/generation fails.
    """
    log(f"Initiating configuration load from: {config_path}", "DEBUG")
    config_existed_initially = config_path.is_file()

    # Step 1: Ensure config file exists (generate if not)
    if not config_existed_initially:
        log(f"Configuration file not found at '{config_path}'. Attempting to generate default config...", "WARNING")
        generated = generate_default_config(schema_path=DEFAULT_SCHEMA_PATH, output_path=config_path, overwrite=False)
        # Check again if file exists after attempting generation
        if not config_path.is_file():
             log(f"Failed to generate or find config file at '{config_path}'. Cannot load configuration.", "ERROR")
             return {} # Return empty dict if file is definitely missing
        log(f"Default config generated successfully at '{config_path}'.", "INFO")

    # Step 2: Try loading the configuration file
    config: Dict[str, Any] = {}
    try:
        log(f"Loading configuration content from '{config_path}'...", "DEBUG")
        with open(config_path, "r", encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Handle empty or invalid file content after loading
        if config is None:
            log(f"Configuration file found but is empty: '{config_path}'. Treating as empty dictionary.", "WARNING")
            config = {} # Ensure config is a dict for subsequent steps
        if not isinstance(config, dict):
             log(f"Configuration file does not contain a valid dictionary (root is {type(config)}): '{config_path}'. Cannot load.", "ERROR")
             return {} # Critical error if structure is wrong

        log(f"Raw configuration loaded successfully from '{config_path}'.", "DEBUG")

        # Step 3: Automatically update the loaded config with missing schema defaults
        # This function logs its actions and might write changes back to config_path.
        log(f"Checking configuration against schema and updating with defaults (if necessary)...", "INFO")
        was_updated = auto_update_config(config_path=config_path, schema_path=DEFAULT_SCHEMA_PATH)
        # auto_update_config returns True if it saved changes to the file

        # Step 4: Reload the config *if* auto_update potentially modified it
        # Ensures that the returned config object reflects any defaults that were just added.
        if was_updated:
            log(f"Reloading configuration from '{config_path}' after defaults were added...", "INFO")
            with open(config_path, "r", encoding='utf-8') as f:
                 config = yaml.safe_load(f) or {} # Reload and ensure it's a dict

            if not isinstance(config, dict):
                 # This would indicate a problem during the auto-update save/reload process
                 log(f"Configuration file became invalid after auto-update attempt: '{config_path}'. Cannot proceed.", "ERROR")
                 return {}
            log("Configuration reload successful after update.", "DEBUG")

        log(f"Configuration loading and preparation complete for '{config_path}'.", "SUCCESS")
        return config

    except yaml.YAMLError as e:
        log(f"Error parsing YAML in configuration file: '{config_path}'. Check YAML syntax.\nError: {e}", "ERROR")
        return {}
    except IOError as e:
         log(f"Error reading configuration file: '{config_path}'. Check file permissions.\nError: {e}", "ERROR")
         return {}
    except Exception as e:
        # Catch-all for unexpected errors during load/update/reload
        log(f"Unexpected error during configuration processing for '{config_path}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log full traceback for detailed debugging
        return {}

# Example usage block (no changes needed, but added logging setup)
if __name__ == "__main__":
    print("-" * 40)
    print(f"Attempting to load configuration from: {DEFAULT_CONFIG_PATH}")
    # Setup basic logging for the test run, otherwise log() calls will fail
    setup_logging()
    loaded_config = load_config()
    if loaded_config:
        print("\nConfiguration loaded successfully via load_config():")
        print(f"  Keys found: {list(loaded_config.keys())}")
        # Use logging to display results now, as print is removed from load_config
        log(f"Value for 'logging_enabled': {loaded_config.get('logging_enabled')}", "INFO")
        log(f"Type for 'llm_models': {type(loaded_config.get('llm_models'))}", "INFO")
        print("-" * 40)
    else:
        print("\nFailed to load configuration or configuration is empty.")
        print("-" * 40)