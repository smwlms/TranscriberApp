# src/utils/config_schema.py

import yaml
import os # Keep os for path checks if needed, though pathlib is primary
from pathlib import Path
# Import the configured logger
# Assuming log.py is correctly set up and importable
from src.utils.log import log

# --- Constants ---
# Determine the project root directory dynamically based on this file's location
# Assumes structure: TranscriberApp/src/utils/config_schema.py
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
except NameError:
     # Fallback if __file__ is not defined (e.g., in some interactive environments)
     PROJECT_ROOT = Path.cwd()
     log(f"Could not resolve PROJECT_ROOT from __file__, using current working directory: {PROJECT_ROOT}", "WARNING")


# Define the default path to the schema file, expected in the project root
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "config_schema.yaml"

def load_schema(schema_path: Path = DEFAULT_SCHEMA_PATH) -> dict:
    """
    Loads the YAML configuration schema from the specified path.

    Args:
        schema_path: The path to the schema file. Defaults to DEFAULT_SCHEMA_PATH
                     (config_schema.yaml in the project root).

    Returns:
        A dictionary containing the loaded schema, or an empty dictionary if
        the file is not found, empty, invalid, or not a dictionary.
    """
    if not schema_path.is_file():
        log(f"Configuration schema file not found at: {schema_path}", "ERROR")
        return {}

    try:
        with open(schema_path, "r", encoding='utf-8') as f:
            schema = yaml.safe_load(f) # Use safe_load for security

        # Validate the loaded content
        if schema is None:
            log(f"Configuration schema file is empty: {schema_path}", "WARNING")
            return {} # Return empty dict for empty file
        if not isinstance(schema, dict):
             log(f"Configuration schema content is not a valid dictionary (YAML root is {type(schema)}): {schema_path}", "ERROR")
             return {} # Schema root must be a dictionary

        log(f"Configuration schema loaded successfully from: {schema_path.name}", "DEBUG")
        return schema

    except yaml.YAMLError as e:
        log(f"Error parsing YAML in configuration schema '{schema_path.name}': {e}", "ERROR")
        return {} # Return empty on YAML parsing errors
    except IOError as e:
         log(f"Error reading configuration schema file '{schema_path.name}': {e}", "ERROR")
         return {} # Return empty on file reading errors
    except Exception as e:
        # Catch any other unexpected errors during loading
        log(f"Unexpected error loading configuration schema '{schema_path.name}': {e}", "ERROR")
        return {}

def parse_schema_for_ui(schema_path: Path = DEFAULT_SCHEMA_PATH) -> dict:
    """
    Parses the configuration schema into a simplified structure suitable for
    dynamically building a user interface. Extracts descriptions, types,
    options (for enums), and default values.

    Args:
        schema_path: The path to the schema YAML file.

    Returns:
        A dictionary where keys are configuration item names and values are
        dictionaries containing UI-relevant info ('type', 'description', 'default',
        'options'?, 'properties'?), or an empty dictionary on error.
    """
    # log(f"Parsing schema for UI from: {schema_path}", "DEBUG") # Optional debug log
    schema = load_schema(schema_path)
    if not schema:
        # load_schema already logged the error
        return {}

    parsed_schema = {}
    # Iterate through top-level keys in the schema (e.g., 'mode', 'whisper_model', 'llm_models')
    for key, field_spec in schema.items():
        # Basic validation: Ensure the spec for each key is a dictionary
        if not isinstance(field_spec, dict):
            log(f"Skipping invalid schema entry for key '{key}': Expected a dictionary, found {type(field_spec)}.", "WARNING")
            continue

        field_type = field_spec.get("type")
        # Basic info present for almost all types
        field_info = {
            "type": field_type,
            "description": field_spec.get("description", ""), # Default to empty string
            "default": field_spec.get("default", None)    # Default to None
        }

        # Handle type-specific fields
        if field_type == "enum":
            options = field_spec.get("options")
            if isinstance(options, list):
                field_info["options"] = options
            else:
                # Log warning if options are missing or invalid for enum type
                log(f"Invalid or missing 'options' (must be a list) for enum key '{key}'.", "WARNING")
                field_info["options"] = [] # Provide empty list as fallback

        elif field_type == "object":
            properties_spec = field_spec.get("properties")
            if isinstance(properties_spec, dict):
                # Parse sub-properties recursively (or handle one level as needed)
                field_info["properties"] = {}
                for sub_key, sub_field_spec in properties_spec.items():
                     # Validate sub-property spec
                     if not isinstance(sub_field_spec, dict):
                         log(f"Skipping invalid sub-property definition for '{key}.{sub_key}'. Expected dict.", "WARNING")
                         continue
                     # Extract relevant info for the sub-property
                     field_info["properties"][sub_key] = {
                        "type": sub_field_spec.get("type"),
                        "description": sub_field_spec.get("description", ""),
                        # Include options if sub-property is an enum etc.
                        "options": sub_field_spec.get("options") if isinstance(sub_field_spec.get("options"), list) else [],
                        "default": sub_field_spec.get("default", None)
                    }
            else:
                log(f"Invalid or missing 'properties' (must be a dictionary) for object key '{key}'.", "WARNING")
                # You might want to represent this differently or omit 'properties'

        # Add the processed field information to the final parsed schema
        parsed_schema[key] = field_info

    # log(f"Schema parsed successfully for UI.", "DEBUG") # Optional debug log
    return parsed_schema

# This block is useful for testing this specific file if needed
if __name__ == "__main__":
    import json # Import json only needed for testing output
    print("-" * 40)
    print(f"--- Testing config_schema.py ---")
    print(f"Project root determined as: {PROJECT_ROOT}")
    print(f"Looking for schema at: {DEFAULT_SCHEMA_PATH}")
    print("-" * 40)

    # Test loading the schema
    print("\nAttempting to load schema...")
    loaded_schema = load_schema()
    if loaded_schema:
        print("Schema loaded successfully.")
        # print(f"Keys: {list(loaded_schema.keys())}") # Optional: Print keys
    else:
        print("Failed to load schema or schema is empty.")

    # Test parsing for UI
    print("\nAttempting to parse schema for UI...")
    ui_schema_data = parse_schema_for_ui()
    if ui_schema_data:
        print("\nSchema parsed successfully for UI:")
        # Use json.dumps for pretty-printing the potentially nested dictionary
        print(json.dumps(ui_schema_data, indent=2, ensure_ascii=False))
    else:
        print("\nFailed to parse schema for UI.")

    print("-" * 40)
    print("--- Testing Complete ---")
    print("-" * 40)