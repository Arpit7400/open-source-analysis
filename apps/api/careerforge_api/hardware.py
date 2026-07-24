"""Cross-platform hardware detection and profiling.

Detects CPU and RAM via :mod:`psutil`, makes a best-effort attempt to detect
GPU VRAM (without requiring any GPU library to be installed), and classifies
the machine into a :class:`HardwareProfile` used to size local model execution.

Design goals:

* **Cross-platform** — runs on Windows, macOS, and Linux with no shell-only
  assumptions. All optional GPU probes are wrapped so a missing tool, missing
  driver, or missing library degrades gracefully to a CPU-only classification.
* **No hard dependencies** — ``pynvml`` / ``torch`` are *optional*. We never
  import them at module load; probing is attempted lazily and failures are
  swallowed.
* **Deterministic output** — the classification maps directly onto the
  ``hardware_profile`` enum in ``docs/API_CONTRACT.md``:
  ``CPU_LOW | VRAM_8_12 | VRAM_16_24 | WORKSTATION``.
"""

from __future__ import annotations

import contextlib
import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum

import psutil

# --- Classification thresholds ---------------------------------------------
# VRAM thresholds (in mebibytes) that separate the profile bands.
_VRAM_8_MB = 8 * 1024  # 8 GiB — lower bound for the VRAM_8_12 band
_VRAM_13_MB = 13 * 1024  # >12 GiB moves into the VRAM_16_24 band
_VRAM_25_MB = 25 * 1024  # >24 GiB is a workstation-class GPU

# When there is no usable GPU, a high-RAM / high-core machine can still be
# treated as a workstation for CPU-bound local inference.
_WORKSTATION_RAM_MB = 64 * 1024  # 64 GiB
_WORKSTATION_CORES = 16


class HardwareProfile(str, Enum):
    """Coarse hardware class used to pick local model sizes / concurrency.

    Values match the ``hardware_profile`` field in the health endpoint exactly.
    """

    CPU_LOW = "CPU_LOW"
    VRAM_8_12 = "VRAM_8_12"
    VRAM_16_24 = "VRAM_16_24"
    WORKSTATION = "WORKSTATION"


@dataclass(frozen=True, slots=True)
class HardwareInfo:
    """Structured snapshot of the host's hardware."""

    profile: HardwareProfile
    os_name: str
    cpu_physical_cores: int
    cpu_logical_cores: int
    ram_total_mb: int
    ram_available_mb: int
    gpu_name: str | None
    gpu_vram_total_mb: int | None
    gpu_detected: bool


def _mb(num_bytes: float) -> int:
    """Convert a byte count to whole mebibytes (rounded)."""
    return round(num_bytes / (1024 * 1024))


def _run_command(args: list[str], timeout: float = 3.0) -> str | None:
    """Run a command and return stripped stdout, or ``None`` on any failure.

    Fully defensive: a missing executable, non-zero exit, timeout, or OS error
    all resolve to ``None`` so callers never have to handle exceptions. The
    executable is resolved via :func:`shutil.which` first so we never rely on a
    shell.
    """
    executable = shutil.which(args[0])
    if executable is None:
        return None
    resolved = [executable, *args[1:]]
    try:
        completed = subprocess.run(
            resolved,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    return output or None


def _detect_gpu_via_pynvml() -> tuple[str | None, int | None]:
    """Best-effort NVIDIA detection via the optional ``pynvml`` library.

    Returns ``(name, vram_total_mb)`` for the largest GPU, or ``(None, None)``
    if ``pynvml`` is unavailable or no device is found. Never raises.
    """
    try:
        import pynvml  # type: ignore[import-not-found]
    except Exception:
        # Optional dependency; any import error means "no NVIDIA probe".
        return None, None

    try:
        pynvml.nvmlInit()
    except Exception:
        # Driver may be absent even when the library is installed.
        return None, None

    best_name: str | None = None
    best_vram_mb: int | None = None
    try:
        device_count = pynvml.nvmlDeviceGetCount()
        for index in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_mb = _mb(float(mem.total))
            if best_vram_mb is None or vram_mb > best_vram_mb:
                best_vram_mb = vram_mb
                raw_name = pynvml.nvmlDeviceGetName(handle)
                best_name = (
                    raw_name.decode("utf-8", "replace")
                    if isinstance(raw_name, bytes)
                    else str(raw_name)
                )
    except Exception:
        # Be defensive about NVML quirks; treat any error as "no data".
        return None, None
    finally:
        with contextlib.suppress(Exception):
            pynvml.nvmlShutdown()

    return best_name, best_vram_mb


def _detect_gpu_via_nvidia_smi() -> tuple[str | None, int | None]:
    """Best-effort NVIDIA detection via the ``nvidia-smi`` CLI.

    Works cross-platform when the NVIDIA driver is installed. Returns
    ``(name, vram_total_mb)`` for the largest GPU, or ``(None, None)``.
    """
    output = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return None, None

    best_name: str | None = None
    best_vram_mb: int | None = None
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        name, mem_raw = parts[0], parts[1]
        try:
            # nvidia-smi reports memory.total in MiB with nounits.
            vram_mb = round(float(mem_raw))
        except ValueError:
            continue
        if best_vram_mb is None or vram_mb > best_vram_mb:
            best_vram_mb = vram_mb
            best_name = name or None
    return best_name, best_vram_mb


def _detect_gpu_via_macos() -> tuple[str | None, int | None]:
    """Best-effort GPU detection on macOS via ``system_profiler``.

    Apple Silicon uses unified memory (no discrete VRAM figure), so this
    reports the chipset name with ``None`` VRAM. That intentionally leaves
    classification to fall back to CPU/RAM heuristics, which is correct for
    unified-memory machines.
    """
    if platform.system() != "Darwin":
        return None, None
    output = _run_command(["system_profiler", "SPDisplaysDataType"])
    if not output:
        return None, None
    name: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Chipset Model:"):
            name = stripped.split(":", 1)[1].strip() or None
            break
    return name, None


def detect_gpu() -> tuple[str | None, int | None]:
    """Detect the primary GPU name and total VRAM (MiB), best-effort.

    Tries, in order: ``pynvml`` (if installed) → ``nvidia-smi`` CLI → macOS
    ``system_profiler``. Any probe may return ``(None, None)``; the first probe
    that yields a name and/or VRAM wins. Never raises.
    """
    name, vram_mb = _detect_gpu_via_pynvml()
    if vram_mb is not None:
        return name, vram_mb

    name, vram_mb = _detect_gpu_via_nvidia_smi()
    if vram_mb is not None:
        return name, vram_mb

    # macOS unified-memory GPUs: report a name but no discrete VRAM.
    mac_name, mac_vram = _detect_gpu_via_macos()
    if mac_name is not None:
        return mac_name, mac_vram

    return name, vram_mb


def _classify(
    ram_total_mb: int,
    physical_cores: int,
    gpu_vram_total_mb: int | None,
) -> HardwareProfile:
    """Map raw hardware facts onto a :class:`HardwareProfile`.

    Priority is given to discrete VRAM when available; otherwise a high-RAM /
    high-core machine is classified as a workstation, and everything else as
    ``CPU_LOW`` (the safe, most-conservative default for local inference).
    """
    if gpu_vram_total_mb is not None and gpu_vram_total_mb > 0:
        if gpu_vram_total_mb >= _VRAM_25_MB:
            return HardwareProfile.WORKSTATION
        if gpu_vram_total_mb >= _VRAM_13_MB:
            return HardwareProfile.VRAM_16_24
        if gpu_vram_total_mb >= _VRAM_8_MB:
            return HardwareProfile.VRAM_8_12
        # A tiny discrete GPU is effectively CPU-class for our model sizes.
        return HardwareProfile.CPU_LOW

    # No usable discrete VRAM (CPU-only or unified-memory machine).
    if ram_total_mb >= _WORKSTATION_RAM_MB and physical_cores >= _WORKSTATION_CORES:
        return HardwareProfile.WORKSTATION
    return HardwareProfile.CPU_LOW


def detect_hardware() -> HardwareInfo:
    """Detect and classify the host hardware.

    Safe to call on any platform with no GPU libraries installed; it degrades
    gracefully to a CPU-based classification.
    """
    virtual_memory = psutil.virtual_memory()
    ram_total_mb = _mb(float(virtual_memory.total))
    ram_available_mb = _mb(float(virtual_memory.available))

    # psutil may return None for physical cores on some platforms.
    physical_cores = psutil.cpu_count(logical=False) or 0
    logical_cores = psutil.cpu_count(logical=True) or physical_cores or 1
    if physical_cores <= 0:
        physical_cores = logical_cores

    gpu_name, gpu_vram_total_mb = detect_gpu()
    gpu_detected = gpu_name is not None or gpu_vram_total_mb is not None

    profile = _classify(
        ram_total_mb=ram_total_mb,
        physical_cores=physical_cores,
        gpu_vram_total_mb=gpu_vram_total_mb,
    )

    return HardwareInfo(
        profile=profile,
        os_name=platform.system() or "Unknown",
        cpu_physical_cores=physical_cores,
        cpu_logical_cores=logical_cores,
        ram_total_mb=ram_total_mb,
        ram_available_mb=ram_available_mb,
        gpu_name=gpu_name,
        gpu_vram_total_mb=gpu_vram_total_mb,
        gpu_detected=gpu_detected,
    )


def detect_hardware_profile() -> HardwareProfile:
    """Convenience wrapper returning only the classified profile."""
    return detect_hardware().profile
