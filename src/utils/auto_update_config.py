# src/utils/auto_update_config.py

import yaml
import os
from pathlib import Path
# Assuming log and load_schema are adapted for English
from src.utils.log import log
from src.utils.config_schema import load_schema, DEFAULT_SCHEMA_PATH # Assuming DEFAULT_SCHEMA_PATH is defined there

def auto_update_config(config_path: Path, schema_path: Path = DEFAULT_SCHEMA_PATH) -> bool:
    """
    Ensures the config file at config_path contains all fields defined in the schema.
    If a field (including nested ones) is missing, it's automatically added
    using the default value from the schema. Existing values are NOT overwritten,
    unless an expected dictionary field is found with a non-dictionary type.

    Args:
        config_path: Path to the configuration file (e.g., config.yaml).
        schema_path: Path to the schema definition file.

    Returns:
        True if the configuration file was updated and saved, False otherwise.
    """
    saved_changes = False # Track if we saved the file

    if not config_path.is_file():
        # This function only updates existing files, generation is separate.
        log(f"INFO: Config file not found at '{config_path}'. Auto-update skipped (use generate_config_from_schema to create).", "INFO")
        return False # Nothing to update

    current_config = {}
    try:
        with open(config_path, "r", encoding='utf-8') as f:
            # Load config, handle empty file by defaulting to {}
            current_config = yaml.safe_load(f) or {}
        if not isinstance(current_config, dict):
             log(f"ERROR: Config file content at '{config_path}' is not a valid dictionary. Auto-update aborted.", "ERROR")
             return False
    except yaml.YAMLError as e:
        log(f"ERROR: YAML parsing error in '{config_path}': {e}. Auto-update aborted.", "ERROR")
        return False
    except IOError as e:
        log(f"ERROR: Could not read config file '{config_path}': {e}. Auto-update aborted.", "ERROR")
        return False

    schema = load_schema(schema_path)
    if not schema:
        # load_schema already logs errors if it fails
        log("WARNING: Schema is empty or not found. Skipping auto-update.", "WARNING")
        return False

    # Recursively merge defaults into the loaded config dictionary
    # The function modifies current_config in-place and returns if changes were made.
    was_updated = _merge_defaults_recursive(current_config, schema)

    # If the merge function indicated changes were made, save the updated config
    if was_updated:
        log(f"INFO: Configuration requires update with missing default values.", "INFO")
        try:
            # Ensure the directory exists (though it should if we read the file)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding='utf-8') as f:
                # Use sort_keys=False to maintain order from schema as much as possible
                yaml.safe_dump(current_config, f, allow_unicode=True, sort_keys=False, indent=2)
            log(f"SUCCESS: Config file '{config_path.name}' automatically updated with missing fields.", "SUCCESS")
            saved_changes = True
        except Exception as e:
            log(f"ERROR: Failed to write updated config file '{config_path.name}': {e}", "ERROR")
            # Changes were made in memory but couldn't be saved
            saved_changes = False
    else:
        log(f"INFO: Configuration file '{config_path.name}' is already up-to-date with schema defaults.", "INFO")

    return saved_changes


def _merge_defaults_recursive(config_dict: dict, schema_node: dict) -> bool:
    """
    Recursively iterates through the schema node and adds missing keys with their
    default values to the config_dict. Handles nested objects.

    Args:
        config_dict: The configuration dictionary to potentially update (modified in-place).
        schema_node: The current node (dictionary) in the schema definition.

    Returns:
        True if any key was added or modified in config_dict, False otherwise.
    """
    updated_this_level = False

    for key, spec in schema_node.items():
        # Ensure spec is a dictionary before proceeding
        if not isinstance(spec, dict):
            log(f"WARNING: Invalid schema specification for key '{key}'. Expected dict, got {type(spec)}. Skipping.", "WARNING")
            continue

        node_type = spec.get("type")
        default_value = spec.get("default") # Default is None if not specified
        properties = spec.get("properties") if node_type == "object" else None

        # --- Case 1: Key is missing in the current config ---
        if key not in config_dict:
            if node_type == "object" and isinstance(properties, dict):
                # Add nested object structure
                config_dict[key] = {}
                # Recursively fill the new dictionary, update status
                updated_sub = _merge_defaults_recursive(config_dict[key], properties)
                updated_this_level = True # Key itself was added
                # Note: updated_sub indicates if sub-keys were added, which is always true if properties exist
            else:
                # Add scalar/list/enum etc. with its default value
                config_dict[key] = default_value
                updated_this_level = True
            log(f"DEBUG: Added missing key '{key}' with default value.", "DEBUG")

        # --- Case 2: Key exists, but might need recursive check for objects ---
        else:
            if node_type == "object" and isinstance(properties, dict):
                # Key exists, and schema expects an object. Check current type.
                if not isinstance(config_dict.get(key), dict):
                    # User had something else (e.g., null, string) where a dict was expected.
                    # Overwrite with an empty dict and fill defaults recursively.
                    log(f"WARNING: Config key '{key}' should be an object (dict), but found type {type(config_dict.get(key))}. Resetting to default structure.", "WARNING")
                    config_dict[key] = {}
                    updated_sub = _merge_defaults_recursive(config_dict[key], properties)
                    updated_this_level = True # Overwriting counts as an update
                else:
                    # Key exists and is already a dict. Recursively check its children.
                    updated_sub = _merge_defaults_recursive(config_dict[key], properties)
                    # Only propagate update status if sub-levels were actually changed
                    if updated_sub:
                        updated_this_level = True

    return updated_this_level

# Example usage block - No changes needed here if it works
if __name__ == "__main__":
     # Example: Create a dummy schema and config to test
     # ... (test code can remain the same) ...
     pass # Keep it simple for now