# src/utils/generate_config_from_schema.py
import yaml
# Removed unused os, json imports
import traceback # Keep for exception logging
from pathlib import Path
from src.utils.log import log, setup_logging
from datetime import datetime
from typing import Dict, Any, Optional, List # Added List hint

# Assuming log and schema loader are adapted for English
from src.utils.log import log
from src.utils.config_schema import load_schema, DEFAULT_SCHEMA_PATH

# Assuming PROJECT_ROOT is defined consistently
try:
    from src.utils.config_schema import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    log("WARNING: Could not import PROJECT_ROOT from config_schema in generate_config, using fallback.", "WARNING")

DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "config.yaml"


def format_yaml_value(value: Any) -> str:
    """
    Formats a Python SCALAR value into a YAML-compatible string representation.
    Handles None, bool, str (with quoting), int, float.
    Lists and Dicts are handled by the main generation logic.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        # Represent Python None as YAML null
        return "null"
    if isinstance(value, str):
        # Add single quotes if string is empty, contains special chars, or internal quotes
        # Escape internal single quotes by doubling them (' becomes '')
        escaped_value = value.replace("'", "''")
        # Characters that might require quoting in YAML (conservative list)
        special_chars = ':{}[] ,&*#?|-<>=!%@`'
        needs_quoting = not value or "'" in value or any(c in special_chars for c in value)
        if needs_quoting:
             return f"'{escaped_value}'"
        else:
             # No quoting needed for simple strings
             return escaped_value
    # For numbers (int, float) and other types, convert directly to string
    return str(value)

def generate_default_config(
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    overwrite: bool = False
) -> bool:
    """
    Generates a default config.yaml file based on the provided schema file.
    The output includes comments from the schema's 'description' and 'options' fields
    and preserves the order of keys from the schema.

    Args:
        schema_path: Path to the schema YAML file.
        output_path: Path where the generated config.yaml should be saved.
        overwrite: If True, overwrite the output file if it already exists.
                   If False (default), skip generation if the file exists.

    Returns:
        True if the configuration file was successfully generated (or skipped because
        overwrite=False and file existed), False if an error occurred.
    """
    # Check overwrite condition first
    if output_path.exists() and not overwrite:
        log(f"Config file already exists at '{output_path}'. Generation skipped (use overwrite=True to replace).", "INFO")
        # Return True because the desired state (file exists) is met without error
        return True

    # Load the schema dictionary
    schema = load_schema(schema_path)
    if not schema:
        # load_schema logs the error
        log(f"Cannot generate config: Failed to load schema from '{schema_path}'.", "ERROR")
        return False

    config_lines: List[str] = [] # Use type hint for clarity
    # Add header comments
    config_lines.append(f"# Default configuration generated from schema: {schema_path.name}")
    config_lines.append(f"# Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    config_lines.append("# Modify values below as needed for your setup.")
    config_lines.append("") # Add blank line after header

    # Iterate through the schema keys and specifications
    for key, field_spec in schema.items():
        if not isinstance(field_spec, dict):
            log(f"Skipping invalid schema entry for key '{key}': Expected a dictionary.", "WARNING")
            continue

        # Extract relevant info from the schema spec
        description = field_spec.get("description", "")
        options = field_spec.get("options")
        default_value = field_spec.get("default") # Defaults to None if not present
        field_type = field_spec.get("type")

        # --- Add Comments (Description, Options) ---
        if description:
            # Add description as a comment, handle potential multi-line descriptions if needed
            comment_lines = [f"# {line.strip()}" for line in description.strip().split('\n')]
            config_lines.extend(comment_lines)
        if options and isinstance(options, list):
            # Add options as a comment for enum types
            config_lines.append(f"# Options: {' | '.join(map(str, options))}")
        elif options:
            # Log if options are defined but not a list
            log(f"Invalid 'options' format for key '{key}'. Expected list.", "WARNING")

        # --- Format Key-Value based on Type ---
        if field_type == "list":
            config_lines.append(f"{key}:") # Key followed by colon
            if default_value and isinstance(default_value, list):
                if not default_value: # Handle empty list default
                     config_lines.append(f"  [] # Empty list")
                else:
                     for item in default_value:
                          # Indent list items with '- ' and format the value
                          config_lines.append(f"  - {format_yaml_value(item)}")
            elif default_value is not None:
                 # Default value was defined but isn't a list - this is likely a schema error
                 log(f"Default value for list key '{key}' is not a list (type: {type(default_value)}). Outputting empty list.", "WARNING")
                 config_lines.append(f"  [] # WARNING: Default was not a list in schema")
            else:
                # No default value specified for list, output empty list representation
                 config_lines.append(f"  [] # Empty list")

        elif field_type == "object" and "properties" in field_spec:
            properties_spec = field_spec.get("properties", {})
            if not isinstance(properties_spec, dict):
                log(f"Invalid 'properties' definition for object key '{key}'. Skipping.", "WARNING")
                config_lines.append(f"{key}: {{}} # WARNING: Invalid properties in schema")
                continue # Skip to next key

            config_lines.append(f"{key}:") # Parent key
            if not properties_spec: # Handle object with no defined properties
                 config_lines.append("  {} # Empty object")
            else:
                 # Iterate through sub-properties
                 for sub_key, sub_field_spec in properties_spec.items():
                     if not isinstance(sub_field_spec, dict):
                         log(f"Skipping invalid sub-property definition for '{key}.{sub_key}'.", "WARNING")
                         continue # Skip invalid sub-property

                     sub_description = sub_field_spec.get("description", "")
                     sub_options = sub_field_spec.get("options")
                     sub_default_value = sub_field_spec.get("default")

                     # Add comments for sub-property (indented)
                     if sub_description:
                          sub_comment_lines = [f"  # {line.strip()}" for line in sub_description.strip().split('\n')]
                          config_lines.extend(sub_comment_lines)
                     if sub_options and isinstance(sub_options, list):
                          config_lines.append(f"  # Options: {' | '.join(map(str, sub_options))}")
                     elif sub_options: log(f"Invalid 'options' for sub-key '{key}.{sub_key}'.", "WARNING")

                     # Format sub-property key-value pair (indented)
                     sub_value_string = format_yaml_value(sub_default_value)
                     config_lines.append(f"  {sub_key}: {sub_value_string}")

        else: # Handle scalar types (string, integer, bool, null, enum treated as scalar default)
            value_string = format_yaml_value(default_value)
            config_lines.append(f"{key}: {value_string}")

        # Add a blank line after each top-level entry for readability
        config_lines.append("")

    # --- Write the generated lines to the output file ---
    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Write the joined lines to the file
        with open(output_path, "w", encoding='utf-8') as f:
            f.write("\n".join(config_lines))
        log(f"Default configuration file generated successfully: '{output_path}'", "SUCCESS")
        return True
    except IOError as e:
        log(f"Error writing configuration file '{output_path}': {e}", "ERROR")
        return False
    except Exception as e:
        log(f"Unexpected error writing configuration file '{output_path}': {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log traceback for unexpected errors
        return False


# Main execution block for running the script directly
if __name__ == "__main__":
    print("-" * 40)
    print(f"--- Generating Default Config ---")
    print(f"Schema Path: {DEFAULT_SCHEMA_PATH}")
    print(f"Output Path: {DEFAULT_OUTPUT_PATH}")
    # Set overwrite=True for testing if you want to regenerate it easily
    force_overwrite = True
    print(f"Overwrite existing file: {force_overwrite}")
    print("-" * 40)

    # Setup basic logging for this script run
    setup_logging()

    # Generate the configuration
    success = generate_default_config(
        schema_path=DEFAULT_SCHEMA_PATH,
        output_path=DEFAULT_OUTPUT_PATH,
        overwrite=force_overwrite
    )

    print("-" * 40)
    if success:
        print("Config generation process completed.")
        if not force_overwrite and not DEFAULT_OUTPUT_PATH.exists():
             print("(File may have already existed and overwrite was False)")
    else:
        print("Config generation failed.")
    print("-" * 40)