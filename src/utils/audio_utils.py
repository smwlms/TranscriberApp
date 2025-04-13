# src/utils/audio_utils.py

import traceback
import shutil
from pathlib import Path

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

def convert_to_wav(input_path: Path, output_path: Path) -> bool:
    """
    Converts an audio file to WAV format, saving it to the output path.
    Uses pydub if available. Handles existing files and copying WAV inputs.

    Args:
        input_path: Path to the input audio file.
        output_path: Path where the converted WAV file should be saved.

    Returns:
        True if the WAV file is ready at output_path (either converted, copied,
        or already existed), False if conversion/copying failed or is not possible.
    """
    input_suffix = input_path.suffix.lower()
    output_parent = output_path.parent

    # Ensure the target directory exists before proceeding
    try:
        output_parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
         log(f"Failed to create output directory '{output_parent}' for WAV conversion: {e}", "ERROR")
         return False # Cannot proceed if directory can't be created

    # --- Case 1: Input is already WAV ---
    if input_suffix == ".wav":
        # If target path is the same as input, nothing needs to be done
        if input_path.resolve() == output_path.resolve():
             log(f"Input file '{input_path.name}' is already the target WAV path.", "DEBUG")
             return True
        else:
             # If target path differs, copy the existing WAV file
             log(f"Input '{input_path.name}' is WAV. Copying to target path '{output_path.name}'.", "INFO")
             try:
                  shutil.copy(str(input_path), str(output_path))
                  return True # Copy successful
             except Exception as e:
                  log(f"Failed to copy WAV file '{input_path.name}' to '{output_path.name}': {e}", "ERROR")
                  return False # Copy failed

    # --- Case 2: Input is not WAV, check if conversion is possible (Pydub needed) ---
    if not PYDUB_AVAILABLE:
        log(f"Cannot convert '{input_path.name}': Input is not WAV and pydub library is not installed.", "ERROR")
        return False # Conversion impossible without pydub

    # --- Case 3: Input is not WAV, pydub is available ---
    # Check if the target output file already exists to avoid redundant work
    if output_path.exists():
        log(f"Skipping conversion: Target WAV file already exists at '{output_path.name}'.", "INFO")
        return True # Target already exists, treat as success

    # Perform conversion using pydub
    log(f"Converting '{input_path.name}' to WAV format at '{output_path.name}' using pydub...", "INFO")
    try:
        # Load audio file using pydub
        # Note: pydub often requires ffmpeg or libav backend installed on the system
        # for formats beyond basic WAV/MP3.
        audio = AudioSegment.from_file(str(input_path))

        # Export as WAV format to the specified output path
        audio.export(str(output_path), format="wav")

        log(f"Successfully converted '{input_path.name}' to '{output_path.name}'.", "SUCCESS")
        return True # Conversion successful

    except CouldntDecodeError:
        # Specific error if pydub/ffmpeg cannot understand the input file format
        log(f"Pydub failed to decode '{input_path.name}'. File format might be unsupported by the system's audio backend (ffmpeg/libav) or the file could be corrupted.", "ERROR")
        return False
    except FileNotFoundError:
         # This common error occurs if the ffmpeg/libav backend is missing
         log(f"Error during conversion: Audio backend (ffmpeg/libav) might be missing or not in the system's PATH. Pydub requires it for most formats.", "ERROR")
         return False
    except Exception as e:
        # Catch any other unexpected errors during the conversion process
        log(f"Unexpected error converting '{input_path.name}' to WAV: {e}", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log traceback for detailed debugging
        return False

# --- End of src/utils/audio_utils.py ---