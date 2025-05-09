# src/utils/audio_utils.py

import traceback
import shutil
from pathlib import Path
# GECORRIGEERDE IMPORT: Voeg Tuple toe
from typing import Optional, Tuple

# Import logging utility
from src.utils.log import log

# --- Pydub Import (Optional Dependency) ---
try:
    # Pydub is used for converting various audio formats to WAV
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError
    PYDUB_AVAILABLE = True
    log("Pydub library found. Audio conversion enabled.", "DEBUG")
except ImportError:
    # Inform the user if pydub is missing, but allow the app to function for WAV files
    log("Pydub library not found. Audio conversion will be limited to WAV inputs. Install with 'pip install pydub'.", "WARNING")
    AudioSegment = None # Define as None to allow type checking later
    CouldntDecodeError = None # Define exception type as None if pydub missing
    PYDUB_AVAILABLE = False

# GECORRIGEERDE SIGNATURE: Retourneert nu een tuple
def convert_to_wav(input_path: Path, output_path: Path) -> Tuple[bool, Optional[Path]]:
    """
    Converts an audio file to WAV format, saving it to the output path.
    If input is already WAV, copies it to output_path if different.
    Uses pydub if available for conversion.

    Args:
        input_path: Path to the input audio file.
        output_path: Path where the converted or copied WAV file should be saved.

    Returns:
        A tuple containing:
        - bool: True if conversion was performed (input was not WAV and pydub was used), False otherwise (input was WAV).
        - Optional[Path]: The Path object to the final WAV file (either the original path if already WAV and not copied, or the output_path), or None if conversion/copying failed or is not possible.
    """
    input_suffix = input_path.suffix.lower()
    output_parent = output_path.parent

    # Ensure the target directory exists before proceeding
    try:
        output_parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
         log(f"Failed to create output directory '{output_parent}' for WAV conversion: {e}", "ERROR")
         # GECORRIGEERDE RETURN: Retourneer False en None bij falen
         return False, None # Cannot proceed if directory can't be created

    # --- Case 1: Input is already WAV ---
    if input_suffix == ".wav":
        # If target path is the same as input, no conversion needed, use original path
        if input_path.resolve() == output_path.resolve():
             log(f"Input file '{input_path.name}' is already the target WAV path.", "DEBUG")
             # GECORRIGEERDE RETURN: Retourneer False (geen conversie) en het input pad
             return False, input_path
        else:
             # If target path differs, copy the existing WAV file
             log(f"Input '{input_path.name}' is WAV. Copying to target path '{output_path.name}'.", "INFO")
             try:
                  shutil.copy(str(input_path), str(output_path))
                  # GECORRIGEERDE RETURN: Retourneer False (geen conversie) en het output pad
                  return False, output_path # Copy successful, return target path
             except Exception as e:
                  log(f"Failed to copy WAV file '{input_path.name}' to '{output_path.name}': {e}", "ERROR")
                  # GECORRIGEERDE RETURN: Retourneer False en None bij falen
                  return False, None # Copy failed

    # --- Case 2: Input is not WAV, check if conversion is possible (Pydub needed) ---
    if not PYDUB_AVAILABLE:
        log(f"Cannot convert '{input_path.name}': Input is not WAV and pydub library is not installed.", "ERROR")
        # GECORRIGEERDE RETURN: Retourneer False en None bij falen
        return False, None # Conversion impossible without pydub

    # --- Case 3: Input is not WAV, pydub is available ---
    # Check if the target output file already exists to avoid redundant work
    # If target already exists, treat as if it was successfully converted (no need to re-convert)
    if output_path.exists():
        log(f"Skipping conversion: Target WAV file already exists at '{output_path.name}'.", "INFO")
        # GECORRIGEERDE RETURN: Retourneer True (conversie *was* nodig, maar bestand bestaat) en het output pad
        return True, output_path # Target already exists, treat as success, return target path

    # Perform conversion using pydub
    log(f"Converting '{input_path.name}' to WAV format at '{output_path.name}' using pydub...", "INFO")
    try:
        # Load audio file using pydub
        audio = AudioSegment.from_file(str(input_path))

        # Export as WAV format to the specified output path
        audio.export(str(output_path), format="wav")

        log(f"Successfully converted '{input_path.name}' to '{output_path.name}'.", "SUCCESS")
        # GECORRIGEERDE RETURN: Retourneer True (conversie uitgevoerd) en het output pad
        return True, output_path # Conversion successful

    except CouldntDecodeError:
        # Specific error if pydub/ffmpeg cannot understand the input file format
        log(f"Pydub failed to decode '{input_path.name}'. File format might be unsupported by the system's audio backend (ffmpeg/libav) or the file could be corrupted.", "ERROR")
        # GECORRIGEERDE RETURN: Retourneer False en None bij falen
        return False, None
    except FileNotFoundError:
         # This common error occurs if the ffmpeg/libav backend is missing
         log(f"Error during conversion: Audio backend (ffmpeg/libav) might be missing or not in the system's PATH. Pydub requires it for most formats.", "ERROR")
         # GECORRIGEERDE RETURN: Retourneer False en None bij falen
         return False, None
    except Exception as e:
        # Catch any other unexpected errors during the conversion process
        log(f"Unexpected error converting '{input_path.name}' to WAV: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG")
        # GECORRIGEERDE RETURN: Retourneer False en None bij falen
        return False, None

# --- End of src/utils/audio_utils.py ---