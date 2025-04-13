# src/utils/route_helpers.py
from typing import Dict, Any
from src.utils.log import log

def parse_config_overrides_from_form(form_data, schema_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses Flask form data into configuration overrides based on schema info.
    Handles basic type conversions and specific mappings.

    Args:
        form_data: The request.form dictionary.
        schema_info: The parsed schema dictionary (pre-loaded).

    Returns:
        A dictionary containing the parsed overrides.
    """
    overrides = {}
    # Define simple types that can be reasonably parsed from form data
    simple_types = ["string", "integer", "float", "bool", "enum"]

    if not schema_info:
         log("Cannot parse form overrides: Schema info is missing.", "ERROR")
         return {} # Return empty if schema couldn't be loaded

    for key, field_spec in schema_info.items():
        field_type = field_spec.get("type")
        # Skip complex types or types not meant for form override
        if field_type not in simple_types:
            continue

        # Determine the key name expected in the form data (allow mapping)
        form_key = key
        if key == "extra_context_prompt": form_key = "custom_prompt"
        # Add other mappings if needed

        if form_key in form_data:
            raw_value = form_data.get(form_key)
            parsed_value = None
            conversion_ok = False

            # --- Type Conversion based on schema ---
            try:
                # Handle empty strings or None values explicitly
                if raw_value is None or raw_value == '':
                    if key == "language":
                        parsed_value = None # Empty language string means None (auto-detect)
                        conversion_ok = True
                    # For other types, an empty string means skip override
                elif field_type == "string":
                    parsed_value = str(raw_value)
                    conversion_ok = True
                elif field_type == "integer":
                     parsed_value = int(raw_value)
                     conversion_ok = True
                elif field_type == "float":
                     parsed_value = float(raw_value)
                     conversion_ok = True
                elif field_type == "bool":
                     # Handles common boolean string values from HTML forms
                     parsed_value = str(raw_value).lower() in ['true', 'on', 'yes', '1']
                     conversion_ok = True
                elif field_type == "enum":
                     options = field_spec.get("options", [])
                     # Validate against defined options if they exist
                     if options and raw_value in options:
                         parsed_value = raw_value
                         conversion_ok = True
                     elif not options: # Allow if enum has no options (unlikely)
                          parsed_value = raw_value
                          conversion_ok = True
                     else:
                          log(f"Invalid enum value '{raw_value}' received for '{key}'. Expected one of {options}. Ignoring override.", "WARNING")
                          # conversion_ok remains False

                # If conversion was successful, add the parsed value to overrides
                if conversion_ok:
                    overrides[key] = parsed_value

            except (ValueError, TypeError) as e:
                 # Log errors during type conversion but don't crash the request
                 log(f"Failed to parse form value for '{key}' (value: '{raw_value}', expected type: {field_type}): {e}. Ignoring override.", "WARNING")

    return overrides

# --- End of src/utils/route_helpers.py ---