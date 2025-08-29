"""Core model loading and device detection utilities.

This refactor removes heavy third‑party imports at module import time so that
lightweight routes (like /config_info) can still import this module even when
ML dependencies are not installed. Heavy libraries are imported lazily inside
functions that need them.
"""

import platform
import traceback
from typing import Optional, Tuple, Any

from src.utils.log import log

# Default pipeline name closely related to model loading
DEFAULT_PYANNOTE_PIPELINE = "pyannote/speaker-diarization-3.1"

# Cache for compute device
_compute_device_cache: Optional[str] = None


def _import_torch_safely():
    """Import torch if available; return None if missing."""
    try:
        import torch  # type: ignore
        return torch
    except Exception as e:
        log(f"PyTorch not available for device detection: {e}. Falling back to 'cpu'.", "WARNING")
        return None


def get_compute_device() -> str:
    """Detect the optimal compute device (cuda > mps > cpu) with safe fallbacks."""
    global _compute_device_cache
    if _compute_device_cache is not None:
        return _compute_device_cache

    device = "cpu"
    torch = _import_torch_safely()
    try:
        if torch and hasattr(torch, "cuda") and torch.cuda.is_available():
            device = "cuda"
            log("CUDA (NVIDIA GPU) detected. Using 'cuda'.", "INFO")
        elif (
            torch
            and platform.system() == "Darwin"
            and hasattr(torch, "backends")
            and hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
        ):
            if getattr(torch.backends.mps, "is_built", lambda: True)():
                device = "mps"
                log("Apple MPS detected and available/built. Using 'mps'.", "INFO")
            else:
                log("Apple MPS detected but backend not built. Using 'cpu'.", "INFO")
        else:
            log("No CUDA/MPS detected or torch missing. Using 'cpu'.", "INFO")
    except Exception as e:
        log(f"Error during compute device detection: {e}. Using 'cpu'.", "WARNING")
        device = "cpu"

    _compute_device_cache = device
    return device


def load_models(
    whisper_model_size: str,
    compute_type: str,
    pyannote_pipeline_name: str = DEFAULT_PYANNOTE_PIPELINE,
    hf_token: Optional[str] = None,
    compute_device: Optional[str] = None,
) -> Tuple[Optional[Any], Optional[Any]]:
    """Load Whisper and Pyannote models on the specified or detected device.

    Returns (None, None) on failure with detailed logs.
    """
    whisper_model = None
    diarization_pipeline = None

    # Import heavy deps lazily here
    try:
        import torch  # type: ignore
    except Exception as e:
        log(f"PyTorch import failed: {e}", "CRITICAL")
        log("Install full requirements to run models (see requirements.txt).", "ERROR")
        return None, None

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        log(f"faster-whisper import failed: {e}", "CRITICAL")
        return None, None

    try:
        from pyannote.audio import Pipeline as PyannotePipeline  # type: ignore
    except Exception as e:
        log(f"pyannote.audio import failed: {e}", "CRITICAL")
        return None, None

    # Determine device
    target_device = compute_device or get_compute_device()
    log(
        f"Attempting to load models (Whisper: {whisper_model_size}, Pyannote: {pyannote_pipeline_name}) on device '{target_device}'...",
        "INFO",
    )

    try:
        # Torch device for Pyannote
        try:
            pyannote_torch_device = torch.device(target_device)
        except Exception as torch_err:
            log(
                f"Invalid compute device '{target_device}' for PyTorch: {torch_err}. Falling back to 'cpu'.",
                "WARNING",
            )
            pyannote_torch_device = torch.device("cpu")

        # Load FasterWhisper
        log(
            f"Loading Whisper model '{whisper_model_size}' (Compute: {compute_type})...",
            "DEBUG",
        )
        whisper_device_arg = "auto" if target_device == "mps" else target_device
        whisper_model = WhisperModel(
            whisper_model_size, device=whisper_device_arg, compute_type=compute_type
        )
        log("Whisper model loaded successfully.", "SUCCESS")

        # Load Pyannote pipeline
        log(f"Loading Pyannote pipeline '{pyannote_pipeline_name}'...", "DEBUG")
        auth_token_arg = {"use_auth_token": hf_token} if hf_token else {}
        if not hf_token:
            log(
                "Hugging Face token not provided. Pyannote model loading might fail if authentication is required.",
                "WARNING",
            )
        diarization_pipeline = PyannotePipeline.from_pretrained(
            pyannote_pipeline_name, **auth_token_arg
        )
        diarization_pipeline.to(pyannote_torch_device)
        log(
            f"Pyannote pipeline loaded and moved onto device '{pyannote_torch_device}'.",
            "SUCCESS",
        )
        return whisper_model, diarization_pipeline

    except Exception as e:
        failed_model = "Whisper" if whisper_model is None else "Pyannote"
        log(
            f"Error loading AI model '{failed_model}' ({whisper_model_size if failed_model == 'Whisper' else pyannote_pipeline_name}): {e}",
            "CRITICAL",
        )
        log(
            "Check model names, Hugging Face token/terms, network connection, and system requirements (RAM/VRAM).",
            "ERROR",
        )
        log(traceback.format_exc(), "DEBUG")
        try:
            del whisper_model
            del diarization_pipeline
        except Exception:
            pass
        return None, None
