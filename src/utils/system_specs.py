import platform
import subprocess
from typing import Dict, Optional

from src.utils.log import log
from src.core.model_loader import get_compute_device


def _get_total_memory_bytes_psutil() -> Optional[int]:
    try:
        import psutil  # type: ignore
        return int(psutil.virtual_memory().total)
    except Exception as e:
        log(f"psutil not available for memory detection: {e}", "DEBUG")
        return None


def _get_total_memory_bytes_platform() -> Optional[int]:
    try:
        system = platform.system()
        if system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
            return int(out)
        elif system == "Linux":
            import os
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages) * int(page_size)
        else:
            return None
    except Exception as e:
        log(f"Fallback memory detection failed: {e}", "DEBUG")
        return None


def get_system_specs() -> Dict:
    """Collect lightweight system specs to help choose models."""
    cpu_count = None
    try:
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
    except Exception:
        cpu_count = None

    total_mem = _get_total_memory_bytes_psutil() or _get_total_memory_bytes_platform()
    mem_gb = round(total_mem / (1024 ** 3), 1) if total_mem else None

    device = get_compute_device()

    return {
        "os": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": cpu_count,
        "memory_gb": mem_gb,
        "device": device,
    }

