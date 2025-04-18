# File: src/core/model_loader.py

import os
import platform
import traceback
from pathlib import Path
from typing import Optional, Tuple

# --- Third-party library imports ---
try:
    import torch
    from faster_whisper import WhisperModel
    from pyannote.audio import Pipeline as PyannotePipeline
except ImportError as e:
    # Provide specific instructions based on potential missing packages
    missing_pkg = ""
    if "torch" in str(e):
        missing_pkg = "torch/pytorch"
    elif "faster_whisper" in str(e):
        missing_pkg = "faster-whisper"
    elif "pyannote" in str(e):
        missing_pkg = "pyannote.audio"
    else:
        missing_pkg = "required AI libraries"

    raise ImportError(
        f"Error: {missing_pkg} seems to be missing or could not be imported. "
        f"Ensure PyTorch, faster-whisper, and pyannote.audio are correctly installed. Original error: {e}"
    ) from e

# --- Local Imports ---
# Assuming log is initialized elsewhere and accessible (e.g., via setup_logging)
from src.utils.log import log

# --- Constants ---
# Default pipeline name moved here as it's closely related to model loading
DEFAULT_PYANNOTE_PIPELINE = "pyannote/speaker-diarization-3.1"

# --- Global cache for compute device ---
# Kept internal to this module
_compute_device_cache: Optional[str] = None

# --- Public Functions ---

def get_compute_device() -> str:
    """
    Automatically detects and caches the optimal compute device (cuda > mps > cpu).
    Designed to be called once and reuse the cached result.
    """
    global _compute_device_cache
    # Return cached value if already detected
    if _compute_device_cache is not None:
        return _compute_device_cache

    device = "cpu" # Default fallback
    try:
        if torch.cuda.is_available():
            device = "cuda"
            log("CUDA (NVIDIA GPU) detected. Using 'cuda'.", "INFO")
        # Check for MPS (Apple Silicon) availability and compatibility
        elif platform.system() == "Darwin" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
             # Further check if MPS is built/usable (useful for older PyTorch versions or setups)
            if torch.backends.mps.is_built():
                device = "mps"
                log("Apple MPS detected and available/built. Using 'mps'.", "INFO")
            else:
                 log("Apple MPS detected but not built/usable in this PyTorch version. Using 'cpu'.", "INFO")
                 # device remains "cpu"
        else:
            # If no GPU detected or on non-Apple Silicon Mac/other OS
            log("No CUDA or available MPS GPU detected. Using 'cpu'.", "INFO")
            # device remains "cpu"
    except Exception as e:
        # Catch potential errors during detection (e.g., unexpected library issues)
        log(f"Error during compute device detection: {e}. Falling back to 'cpu'.", "WARNING")
        device = "cpu" # Ensure fallback on error

    # Cache and return the determined device
    _compute_device_cache = device
    return device


def load_models(
    whisper_model_size: str,
    compute_type: str,
    pyannote_pipeline_name: str = DEFAULT_PYANNOTE_PIPELINE, # Use default defined above
    hf_token: Optional[str] = None, # Made optional here, fetch from env in orchestrator if needed
    compute_device: Optional[str] = None # Allow overriding detected device
    ) -> Tuple[Optional[WhisperModel], Optional[PyannotePipeline]]:
    """
    Loads Whisper and Pyannote models onto the specified or auto-detected device.

    Args:
        whisper_model_size: Size of the FasterWhisper model (e.g., "tiny", "base", "small").
        compute_type: Compute type for Whisper (e.g., "int8", "float16").
        pyannote_pipeline_name: Name of the Pyannote pipeline model.
        hf_token: Optional Hugging Face API token for Pyannote model access.
        compute_device: Optional target device ("cuda", "mps", "cpu"). Auto-detects if None.

    Returns:
        A tuple containing the loaded (WhisperModel, PyannotePipeline), or (None, None) if loading fails.
    """
    whisper_model = None
    diarization_pipeline = None

    # Determine target device if not provided
    target_device = compute_device or get_compute_device()
    log(f"Attempting to load models (Whisper: {whisper_model_size}, Pyannote: {pyannote_pipeline_name}) on device '{target_device}'...", "INFO")

    try:
        # Determine torch device object for Pyannote
        try:
            pyannote_torch_device = torch.device(target_device)
        except Exception as torch_err:
             log(f"Invalid compute device '{target_device}' specified for PyTorch: {torch_err}. Attempting fallback.", "WARNING")
             # Fallback logic could be added here if needed, e.g., force CPU
             pyannote_torch_device = torch.device("cpu") # Simple fallback for now

        # Load FasterWhisper model
        log(f"Loading Whisper model '{whisper_model_size}' (Compute: {compute_type})...", "DEBUG")
        # Use 'auto' device argument for Whisper when MPS is detected for potentially better compatibility
        whisper_device_arg = "auto" if target_device == "mps" else target_device
        whisper_model = WhisperModel(whisper_model_size, device=whisper_device_arg, compute_type=compute_type)
        log("Whisper model loaded successfully.", "SUCCESS")

        # Load Pyannote pipeline
        log(f"Loading Pyannote pipeline '{pyannote_pipeline_name}'...", "DEBUG")
        auth_token_arg = {"use_auth_token": hf_token} if hf_token else {}
        if not hf_token:
            log("Hugging Face token not provided. Pyannote model loading might fail if authentication is required.", "WARNING")
        # Download/load the pipeline
        diarization_pipeline = PyannotePipeline.from_pretrained(pyannote_pipeline_name, **auth_token_arg)
        # Move the loaded pipeline to the target torch device
        diarization_pipeline.to(pyannote_torch_device)
        log(f"Pyannote pipeline loaded and moved successfully onto device '{pyannote_torch_device}'.", "SUCCESS")

        return whisper_model, diarization_pipeline

    except Exception as e:
        # Log loading errors clearly
        failed_model = "Whisper" if whisper_model is None else "Pyannote"
        log(f"Error loading AI model '{failed_model}' ({whisper_model_size if failed_model == 'Whisper' else pyannote_pipeline_name}): {e}", "CRITICAL")
        log("Check model names, Hugging Face token/terms, network connection, and system requirements (RAM/VRAM).", "ERROR")
        log(traceback.format_exc(), "DEBUG") # Log full traceback for detailed debugging
        # Attempt to clean up partially loaded models if possible (optional)
        del whisper_model
        del diarization_pipeline
        return None, None # Return None tuple on failure