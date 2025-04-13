# src/utils/pipeline_helpers.py

from typing import Dict, Any

# --- Import dependencies directly ---
# Removed fallback imports; rely on correct module structure.
from src.job_manager import job_manager
from src.utils.log import log


def check_stop(job_id: str, current_step: str = "process"):
    """
    Checks if a stop has been requested for the job via the JobManager.
    If a stop is requested, raises an InterruptedError to halt execution.

    Args:
        job_id: The ID of the job to check.
        current_step: A string indicating which part of the process is being checked
                      (used in the error message).

    Raises:
        InterruptedError: If a stop has been requested for the specified job ID.
    """
    if job_manager.is_stop_requested(job_id):
        # Logging is removed here; the exception handler in the calling
        # pipeline step is responsible for logging the interruption.
        raise InterruptedError(f"Stop requested during {current_step} for job {job_id}.")


def merge_configs(base: dict, overrides: dict) -> dict:
    """
    Recursively merges the 'overrides' dictionary into the 'base' dictionary.

    - Creates a new dictionary (copy of base) for the result.
    - Nested dictionaries are merged recursively.
    - Other value types (scalars, lists) in 'overrides' replace the
      corresponding values in 'base'.
    - Handles type mismatches (e.g., dict vs. non-dict) by letting
      the 'overrides' value take precedence.

    Args:
        base: The base configuration dictionary.
        overrides: The dictionary with values to override the base config.

    Returns:
        A new dictionary representing the merged configuration.
    """
    # Start with a shallow copy of the base dictionary
    merged = base.copy()

    # Iterate through the keys and values in the overrides dictionary
    for key, value_override in overrides.items():
        value_base = merged.get(key) # Get corresponding value from base/merged copy

        # Check if the key exists in base and both values are dictionaries -> recurse
        if isinstance(value_base, dict) and isinstance(value_override, dict):
            merged[key] = merge_configs(value_base, value_override) # Recursive call
        else:
            # Otherwise, the override value replaces the base value entirely
            # This covers cases where key is new, or types differ, or values are not dicts.
            merged[key] = value_override

    return merged

# --- End of src/utils/pipeline_helpers.py ---